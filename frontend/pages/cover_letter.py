"""Cover letter generation, refinement, and history page."""

import time
from datetime import UTC, datetime

import streamlit as st

from api_client import api, detail, safe_json
from components import loading_spinner, show_error, show_success


def _job_url_import_cl(key_prefix: str) -> str:
    fetched_jd = ""
    with st.expander("🔗 Import Job from URL (LinkedIn, Greenhouse, Lever…)"):
        st.caption(
            "Paste any public job posting URL. LinkedIn may require login — "
            "in that case paste the text manually."
        )
        job_url_input = st.text_input(
            "Job Posting URL",
            placeholder="https://www.linkedin.com/jobs/view/...",
            key=f"{key_prefix}_url_input",
        )
        if st.button("🚀 Fetch Job Description", key=f"{key_prefix}_fetch_btn"):
            if not job_url_input.strip():
                show_error("Please enter a URL.")
            else:
                with st.spinner("Fetching job description…"):
                    resp = api("post", "/ai/fetch-job", json={"url": job_url_input.strip()})
                data = safe_json(resp, {})
                if resp.status_code == 200 and data.get("success"):
                    fetched_jd = data.get("job_description", "")
                    st.session_state[f"{key_prefix}_prefilled_jd"] = fetched_jd
                    show_success("Job description fetched! Scroll down — it's pre-filled below.")
                    if data.get("warning"):
                        st.warning(data["warning"])
                else:
                    show_error(detail(resp, "Could not fetch job description."))
    return st.session_state.get(f"{key_prefix}_prefilled_jd", "")


def page_cover_letter() -> None:
    st.title("✉️ AI Cover Letter Generator")
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

    prefilled_jd = _job_url_import_cl("cover_letter")
    jd = st.text_area(
        "Paste the Job Description",
        value=prefilled_jd,
        height=300,
        placeholder="Paste the full job posting here, or import from URL above.",
    )

    if st.button("🚀 Generate Cover Letter", type="primary"):
        if not jd.strip():
            show_error("Please paste the job description.")
            return
        with loading_spinner("Dispatching AI task..."):
            resp = api(
                "post",
                "/cover-letters/generate",
                json={"job_description": jd, "resume_id": selected_id},
            )
        if resp.status_code != 202:
            show_error(
                detail(resp, f"API error (HTTP {resp.status_code}). Is the backend running?")
            )
            return

        cl = safe_json(resp, {})
        task_id = cl.get("task_id")
        cl_id = cl.get("id")
        st.info(f"Task started. ID: `{task_id}`")
        progress = st.progress(0, text="Generating cover letter...")
        status_box = st.empty()
        ticks = 0
        while True:
            time.sleep(2)
            ticks += 1
            poll = safe_json(api("get", f"/cover-letters/task/{task_id}"), {})
            status = poll.get("status", "PENDING")
            progress.progress(min(ticks * 5, 90), text=f"Status: {status}")
            status_box.markdown(f"**Status:** `{status}`")
            if status == "SUCCESS":
                progress.progress(100, text="Done!")
                cl_detail = safe_json(api("get", f"/cover-letters/{cl_id}"), {})
                cover_text = cl_detail.get("generated_text", "")
                show_success("Cover letter generated!")
                st.session_state["active_cl_id"] = cl_id
                st.text_area("📝 Your Cover Letter", cover_text, height=450, key="cl_generated")
                dl1, dl2 = st.columns(2)
                dl1.download_button("⬇ Download TXT", cover_text, file_name="cover_letter.txt", use_container_width=True)
                pdf_resp = api("get", f"/cover-letters/{cl_id}/pdf")
                if pdf_resp.status_code == 200:
                    dl2.download_button("📄 Download PDF", pdf_resp.content, file_name="cover_letter.pdf", mime="application/pdf", use_container_width=True, type="primary")
                break
            elif status == "FAILURE":
                show_error("Task failed. Check the backend worker logs.")
                break
            elif ticks > 60:
                show_error("Timed out after 2 minutes. Check the backend logs.")
                break

    active_cl_id = st.session_state.get("active_cl_id")
    if active_cl_id:
        st.divider()
        st.subheader("✏️ Refine This Cover Letter")
        st.caption("Give a specific edit instruction. The AI applies only the change you request.")
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
                    resp = api("post", f"/cover-letters/{active_cl_id}/refine", json={"command": command.strip()})
                if resp.status_code == 202:
                    show_success("Refinement queued — check the version history below in a few seconds.")
                    st.rerun()
                else:
                    show_error(detail(resp, "Refinement failed."))

        revisions = safe_json(api("get", f"/cover-letters/{active_cl_id}/revisions"), [])
        if isinstance(revisions, list) and revisions:
            st.subheader(f"📋 Version History ({len(revisions)} revision{'s' if len(revisions) != 1 else ''})")
            for rev in revisions:
                v = rev["version_number"]
                cmd_label = rev["user_command"][:60] + ("…" if len(rev["user_command"]) > 60 else "")
                with st.expander(f"v{v} — \"{cmd_label}\"  |  {rev['created_at'][:10]}"):
                    st.text_area("Revised text", rev["generated_text"], height=300, key=f"rev_text_{rev['id']}")
                    rc1, rc2 = st.columns(2)
                    rc1.download_button("⬇ TXT", rev["generated_text"], file_name=f"cover_letter_v{v}.txt", key=f"rev_dl_{rev['id']}", use_container_width=True)
                    if rc2.button("⭐ Activate this version", key=f"activate_rev_{rev['id']}", use_container_width=True, type="primary"):
                        act_resp = api("post", f"/cover-letters/{active_cl_id}/revisions/{v}/activate")
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
                    exp = datetime.fromisoformat(cl["expires_at"].replace("Z", "+00:00"))
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
            with st.expander(f"Cover Letter — {cl['created_at'][:10]}{cl_expiry_tag} | Status: `{status_label}`"):
                if cl.get("generated_text"):
                    st.text_area("", cl["generated_text"], height=250, key=f"hist_{cl['id']}")
                    if st.button("✏️ Refine this letter", key=f"load_refine_{cl['id']}"):
                        st.session_state["active_cl_id"] = cl["id"]
                        st.rerun()
                    hc1, hc2 = st.columns(2)
                    hc1.download_button("⬇ TXT", cl["generated_text"], file_name="cover_letter.txt", key=f"txt_{cl['id']}", use_container_width=True)
                    pdf_resp = api("get", f"/cover-letters/{cl['id']}/pdf")
                    if pdf_resp.status_code == 200:
                        hc2.download_button("📄 PDF", pdf_resp.content, file_name="cover_letter.pdf", mime="application/pdf", key=f"pdf_{cl['id']}", use_container_width=True, type="primary")
    else:
        st.info("No cover letters generated yet.")
