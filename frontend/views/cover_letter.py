"""Cover letter generation, refinement, and history page."""

import time
from datetime import UTC, datetime

import streamlit as st

from api_client import api, detail, safe_json
from components import (
    job_description_input,
    loading_spinner,
    render_qa_scores,
    show_error,
    toast_success,
)
from ui import page_header, poll_outcome, poll_task

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
                "No embeddings stored yet. Upload a resume to start building your vector store."
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


def _generation_status() -> None:
    """One poll tick — runs inside a fragment so only this block re-renders."""
    task = st.session_state.get("cl_generate")
    if not task:
        return
    elapsed = time.time() - task["started"]
    http_status, payload = poll_task(f"/cover-letters/task/{task['task_id']}")
    outcome = poll_outcome(http_status, payload.get("status"), elapsed, _GENERATE_TIMEOUT_S)
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
        render_qa_scores(cl.get("qa_score_honesty"), cl.get("qa_score_tone"), cl.get("qa_flags"))
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


_REFINE_PRESETS = {
    "✂️ Shorter": "Make the cover letter more concise without dropping key achievements.",
    "💪 Confident": "Make the tone more confident and assertive.",
    "🎯 Specific": "Add concrete, specific details drawn only from my resume.",
    "📋 Formal": "Make the tone more formal and professional.",
    "🙂 Warmer": "Make the tone warmer and more personable.",
}

# Stop showing a revision as "processing" if its QA score never lands (e.g. the QA
# review step errored) — otherwise the old placeholder text would linger forever.
_REFINE_TIMEOUT_S = 150


def _submit_refine(cl_id: str, command: str) -> None:
    """Queue a refinement, switch on history auto-refresh, and rerun."""
    with loading_spinner("Queuing refinement…"):
        resp = api("post", f"/cover-letters/{cl_id}/refine", json={"command": command})
    if resp.status_code == 202:
        st.session_state["refine_polling"] = True
        toast_success("Refinement queued — the version history updates automatically.")
        st.rerun()
    else:
        show_error(detail(resp, "Refinement failed."))


def _is_processing(rev: dict) -> bool:
    """True while a revision is still being refined.

    A fresh revision carries the *old* text and no QA score until a background task
    overwrites both, so "no honesty score yet" means in-flight. If QA review itself
    errors the score stays None, so cap the wait with _REFINE_TIMEOUT_S.
    """
    if rev.get("qa_score_honesty") is not None:
        return False
    first_seen = st.session_state.setdefault(f"_rev_seen_{rev['id']}", time.time())
    return (time.time() - first_seen) < _REFINE_TIMEOUT_S


def _render_revision_history(cl_id: str) -> None:
    """QA-aware version history; auto-refreshes while a refinement is pending."""
    revisions = safe_json(api("get", f"/cover-letters/{cl_id}/revisions"), [])
    if not isinstance(revisions, list) or not revisions:
        return

    # Once nothing is in flight, drop the auto-refresh on the next full rerun.
    if not any(_is_processing(r) for r in revisions) and st.session_state.get("refine_polling"):
        st.session_state["refine_polling"] = False
        st.rerun(scope="app")

    count = len(revisions)
    st.subheader(f"📋 Version History ({count} revision{'s' if count != 1 else ''})")
    for rev in revisions:
        v = rev["version_number"]
        cmd = rev["user_command"]
        cmd_label = cmd[:60] + ("…" if len(cmd) > 60 else "")

        if _is_processing(rev):
            with st.expander(f'v{v} — "{cmd_label}"  |  ⏳ refining…', expanded=True):
                st.info(
                    "✨ Applying your change and running the honesty check — "
                    "this updates on its own."
                )
            continue

        with st.expander(f'v{v} — "{cmd_label}"  |  {rev["created_at"][:10]}'):
            if rev.get("qa_score_honesty") is None:
                st.caption("⚠️ QA score unavailable for this revision.")
            else:
                render_qa_scores(
                    rev.get("qa_score_honesty"),
                    rev.get("qa_score_tone"),
                    rev.get("qa_flags"),
                )
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
                act_resp = api("post", f"/cover-letters/{cl_id}/revisions/{v}/activate")
                if act_resp.status_code == 200:
                    toast_success(f"v{v} is now the active cover letter.")
                    st.rerun(scope="app")
                else:
                    show_error(detail(act_resp, "Activation failed."))


def page_cover_letter() -> None:
    page_header("✉️", "Cover Letter")
    st.markdown(
        "Drafts a letter from **your resume only** (RAG retrieval), then an AI judge "
        "reviews it for honesty before you see it."
    )

    resumes = safe_json(api("get", "/resumes/"), []) if st.session_state.token else []
    if not isinstance(resumes, list) or not resumes:
        st.warning("⚠️ Upload a resume first in **My Resumes**.")
        return

    resume_options = {r["name"]: r["id"] for r in resumes}
    active = next((r["name"] for r in resumes if r["is_active"]), list(resume_options.keys())[0])
    selected_name = st.selectbox(
        "Choose Resume",
        list(resume_options.keys()),
        index=list(resume_options.keys()).index(active),
    )
    selected_id = resume_options[selected_name]

    jd = job_description_input("cover_letter", height=300, label="Paste the Job Description")

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
            "Pick a quick tweak or describe the change yourself. The AI applies only "
            "what you ask and keeps every version in the history below."
        )

        st.markdown("**Quick tweaks**")
        preset_items = list(_REFINE_PRESETS.items())
        preset_cols = st.columns(len(preset_items))
        for i, (label, preset_command) in enumerate(preset_items):
            if preset_cols[i].button(label, key=f"preset_{label}", use_container_width=True):
                _submit_refine(active_cl_id, preset_command)

        command = st.text_input(
            "Or describe your own change",
            placeholder="e.g. 'Mention my AWS certification in the second paragraph'",
            key="refine_command_input",
        )
        if st.button("🔄 Apply Refinement", type="primary", key="apply_refine_btn"):
            if not command.strip():
                show_error("Enter an instruction or pick a quick tweak above.")
            else:
                _submit_refine(active_cl_id, command.strip())

        # Auto-refresh only the version history while a refinement is in flight.
        run_every = "3s" if st.session_state.get("refine_polling") else None
        st.fragment(_render_revision_history, run_every=run_every)(active_cl_id)

    st.divider()
    st.subheader("📜 Past Cover Letters")
    history = safe_json(api("get", "/cover-letters/"), [])
    if isinstance(history, list) and history:
        for cl in history[:5]:
            cl_expiry_tag = ""
            if cl.get("expires_at"):
                try:
                    exp = datetime.fromisoformat(cl["expires_at"].replace("Z", "+00:00"))
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
