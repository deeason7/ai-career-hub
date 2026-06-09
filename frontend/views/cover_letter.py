"""Cover letter generation, refinement, and history page."""

import time
from datetime import UTC, datetime

import requests
import streamlit as st

from api_client import api, detail, safe_json
from components import (
    job_description_input,
    loading_spinner,
    show_error,
    show_success,
    toast_success,
)
from ui import page_header

# Generation is usually 20-60s (draft + AI honesty review, with up to two
# regenerations). Past this the task is almost certainly orphaned; the backend
# reaper will fail it eventually, but the UI should stop polling much sooner.
_GENERATE_TIMEOUT_S = 180

_OUTCOME_ERRORS = {
    "failed": "Generation failed on the server. Try again in a minute.",
    "lost": "This task is no longer tracked (it may have expired). Generate again.",
    "auth": "Your session expired while generating. Log in again, then retry.",
    "timeout": (
        "Still not finished after 3 minutes. It may yet complete in the background — "
        "check Past Cover Letters shortly, or generate again."
    ),
}


def _show_rag_context() -> None:
    """Display RAG pipeline stats and recent retrieval in an expander."""
    stats = safe_json(api("get", "/rag/stats"), {})
    total = stats.get("total_chunks", 0)
    by_type = stats.get("chunks_by_type", {})

    with st.expander("🔍 RAG Context (Vector Store)", expanded=False):
        if total == 0:
            st.info(
                "No embeddings stored yet. Upload a resume to start "
                "building your vector store."
            )
            return

        cols = st.columns(len(by_type) + 1)
        cols[0].metric("Total Chunks", total)
        for i, (source_type, count) in enumerate(sorted(by_type.items()), 1):
            label = source_type.replace("_", " ").title()
            cols[i].metric(label, count)

        st.caption(
            "Your documents are chunked and embedded for semantic retrieval. "
            "The AI uses the most relevant chunks when generating cover letters."
        )


def _poll_outcome(http_status: int | None, task_status: str | None, elapsed: float) -> str:
    """Classify one poll tick of the generate task.

    Transient trouble (a network blip, a 5xx) reads as "running" so a hiccup
    doesn't kill the poll; the elapsed cap is the backstop.
    """
    if http_status == 404:
        return "lost"  # unknown or expired task id
    if http_status in (401, 403):
        return "auth"
    if task_status == "SUCCESS":
        return "done"
    if task_status == "FAILURE":
        return "failed"
    if elapsed > _GENERATE_TIMEOUT_S:
        return "timeout"
    return "running"


def _generation_status() -> None:
    """One poll tick — runs inside a fragment so only this block re-renders."""
    task = st.session_state.get("cl_generate")
    if not task:
        return
    elapsed = time.time() - task["started"]
    try:
        resp = api("get", f"/cover-letters/task/{task['task_id']}")
        http_status = resp.status_code
        task_status = safe_json(resp, {}).get("status")
    except requests.RequestException:
        http_status, task_status = None, None

    outcome = _poll_outcome(http_status, task_status, elapsed)
    if outcome == "running":
        st.status(
            f"✍️ Drafting your letter, then running the AI honesty review… {int(elapsed)}s",
            state="running",
        )
        st.caption("This updates by itself — you can keep using the rest of the app.")
        return

    # Terminal state: stop polling and hand control back to a full-page run.
    st.session_state.pop("cl_generate", None)
    if outcome == "done":
        st.session_state["active_cl_id"] = task["cl_id"]
        toast_success("Cover letter ready!")
    else:
        st.session_state["cl_generate_error"] = _OUTCOME_ERRORS[outcome]
    st.rerun(scope="app")


def _render_active_letter() -> None:
    """The letter being worked on, rendered from state so it survives reruns."""
    cl_id = st.session_state.get("active_cl_id")
    if not cl_id or st.session_state.get("cl_generate"):
        return
    cl = safe_json(api("get", f"/cover-letters/{cl_id}"), {})
    text = cl.get("generated_text")
    if not text:
        return

    st.divider()
    st.subheader("📝 Your Cover Letter")
    if cl.get("qa_score_honesty") is not None:
        st.caption(
            f"🛡️ AI honesty review: {cl['qa_score_honesty']}/10 honesty · "
            f"{cl.get('qa_score_tone', '—')}/10 tone"
        )
    st.text_area(
        "Generated cover letter",
        text,
        height=450,
        key=f"cl_generated_{cl_id}",
        label_visibility="collapsed",
    )
    dl1, dl2 = st.columns(2)
    dl1.download_button(
        "⬇ Download TXT",
        text,
        file_name="cover_letter.txt",
        key=f"cl_txt_{cl_id}",
        use_container_width=True,
    )
    if dl2.button(
        "📄 Download PDF",
        key=f"cl_pdf_{cl_id}",
        use_container_width=True,
        type="primary",
    ):
        pdf_resp = api("get", f"/cover-letters/{cl_id}/pdf")
        if pdf_resp.status_code == 200:
            dl2.download_button(
                "⬇ Save PDF",
                pdf_resp.content,
                file_name="cover_letter.pdf",
                mime="application/pdf",
                key=f"cl_pdf_save_{cl_id}",
            )
        else:
            show_error("Could not generate PDF.")
    _show_rag_context()


def page_cover_letter() -> None:
    page_header("✉️", "Cover Letter")
    st.markdown(
        "Generates a **zero-hallucination** cover letter using RAG — "
        "only facts from YOUR resume."
    )

    resumes = safe_json(api("get", "/resumes/"), []) if st.session_state.token else []
    if not isinstance(resumes, list) or not resumes:
        st.warning("⚠️ Upload a resume first in **My Resumes**.")
        return

    resume_options = {r["name"]: r["id"] for r in resumes}
    active = next(
        (r["name"] for r in resumes if r["is_active"]), list(resume_options.keys())[0]
    )
    selected_name = st.selectbox(
        "Choose Resume",
        list(resume_options.keys()),
        index=list(resume_options.keys()).index(active),
    )
    selected_id = resume_options[selected_name]

    jd = job_description_input(
        "cover_letter", height=300, label="Paste the Job Description"
    )

    in_flight = bool(st.session_state.get("cl_generate"))
    if st.button("🚀 Generate Cover Letter", type="primary", disabled=in_flight):
        if not jd.strip():
            show_error("Please paste the job description.")
        else:
            with loading_spinner("Dispatching AI task..."):
                resp = api(
                    "post",
                    "/cover-letters/generate",
                    json={"job_description": jd, "resume_id": selected_id},
                )
            if resp.status_code != 202:
                show_error(
                    detail(
                        resp,
                        f"API error (HTTP {resp.status_code}). Is the backend running?",
                    )
                )
            else:
                cl = safe_json(resp, {})
                st.session_state["cl_generate"] = {
                    "task_id": cl.get("task_id"),
                    "cl_id": cl.get("id"),
                    "started": time.time(),
                }
                st.rerun()

    if in_flight:
        # Poll inside a fragment: only the status block re-runs every 2s, so the
        # page never freezes mid-generation (the old loop blocked the whole app).
        st.fragment(_generation_status, run_every="2s")()

    gen_error = st.session_state.pop("cl_generate_error", None)
    if gen_error:
        show_error(gen_error)

    _render_active_letter()

    active_cl_id = st.session_state.get("active_cl_id")
    if active_cl_id:
        st.divider()
        st.subheader("✏️ Refine This Cover Letter")
        st.caption(
            "Give a specific edit instruction. The AI applies only the change you request."
        )
        command = st.text_input(
            "Refinement command",
            placeholder="e.g. 'Make the opening paragraph more confident'",
            key="refine_command_input",
        )
        if st.button("🔄 Apply Refinement", type="primary", key="apply_refine_btn"):
            if not command.strip():
                show_error("Enter an instruction first.")
            else:
                with st.spinner("Applying refinement…"):
                    resp = api(
                        "post",
                        f"/cover-letters/{active_cl_id}/refine",
                        json={"command": command.strip()},
                    )
                if resp.status_code == 202:
                    show_success(
                        "Refinement queued — check the version history below in a few seconds."
                    )
                    st.rerun()
                else:
                    show_error(detail(resp, "Refinement failed."))

        revisions = safe_json(
            api("get", f"/cover-letters/{active_cl_id}/revisions"), []
        )
        if isinstance(revisions, list) and revisions:
            st.subheader(
                f"📋 Version History ({len(revisions)} revision{'s' if len(revisions) != 1 else ''})"
            )
            for rev in revisions:
                v = rev["version_number"]
                cmd_label = rev["user_command"][:60] + (
                    "…" if len(rev["user_command"]) > 60 else ""
                )
                with st.expander(f'v{v} — "{cmd_label}"  |  {rev["created_at"][:10]}'):
                    st.text_area(
                        "Revised text",
                        rev["generated_text"],
                        height=300,
                        key=f"rev_text_{rev['id']}",
                    )
                    rc1, rc2 = st.columns(2)
                    rc1.download_button(
                        "⬇ TXT",
                        rev["generated_text"],
                        file_name=f"cover_letter_v{v}.txt",
                        key=f"rev_dl_{rev['id']}",
                        use_container_width=True,
                    )
                    if rc2.button(
                        "⭐ Activate this version",
                        key=f"activate_rev_{rev['id']}",
                        use_container_width=True,
                        type="primary",
                    ):
                        act_resp = api(
                            "post",
                            f"/cover-letters/{active_cl_id}/revisions/{v}/activate",
                        )
                        if act_resp.status_code == 200:
                            show_success(f"v{v} is now the active cover letter.")
                            st.rerun()
                        else:
                            show_error(detail(act_resp, "Activation failed."))

    st.divider()
    st.subheader("📜 Past Cover Letters")
    history = safe_json(api("get", "/cover-letters/"), [])
    if isinstance(history, list) and history:
        for cl in history[:5]:
            cl_expiry_tag = ""
            if cl.get("expires_at"):
                try:
                    exp = datetime.fromisoformat(
                        cl["expires_at"].replace("Z", "+00:00")
                    )
                    if exp.tzinfo is None:
                        exp = exp.replace(tzinfo=UTC)
                    days_left = (exp - datetime.now(UTC)).days
                    if days_left < 0:
                        cl_expiry_tag = "  🔴 expired"
                    elif days_left == 0:
                        cl_expiry_tag = "  🔴 expires today"
                    elif days_left <= 3:
                        cl_expiry_tag = f"  🟠 {days_left}d left"
                    else:
                        cl_expiry_tag = f"  🗓️ {days_left}d left"
                except (ValueError, AttributeError):
                    pass
            status_label = cl.get("status", "")
            with st.expander(
                f"Cover Letter — {cl['created_at'][:10]}{cl_expiry_tag} | Status: `{status_label}`"
            ):
                if cl.get("generated_text"):
                    st.text_area(
                        "Past cover letter",
                        cl["generated_text"],
                        height=250,
                        key=f"hist_{cl['id']}",
                        label_visibility="collapsed",
                    )
                    if st.button("✏️ Refine this letter", key=f"load_refine_{cl['id']}"):
                        st.session_state["active_cl_id"] = cl["id"]
                        st.rerun()
                    hc1, hc2 = st.columns(2)
                    hc1.download_button(
                        "⬇ TXT",
                        cl["generated_text"],
                        file_name="cover_letter.txt",
                        key=f"txt_{cl['id']}",
                        use_container_width=True,
                    )
                    if hc2.button(
                        "📄 PDF",
                        key=f"pdf_btn_{cl['id']}",
                        use_container_width=True,
                        type="primary",
                    ):
                        pdf_resp = api("get", f"/cover-letters/{cl['id']}/pdf")
                        if pdf_resp.status_code == 200:
                            st.download_button(
                                "⬇ Save PDF",
                                pdf_resp.content,
                                file_name="cover_letter.pdf",
                                mime="application/pdf",
                                key=f"pdf_save_{cl['id']}",
                            )
                        else:
                            show_error("Could not generate PDF.")
    else:
        st.info("No cover letters generated yet.")
