"""Resumes page — upload, list, activate, delete."""

import streamlit as st

from api_client import api, detail, safe_json
from ui import (
    chip_row,
    lifecycle_badge,
    loading_spinner,
    page_header,
    show_error,
    show_success,
)


def _render_analysis(parsed: dict) -> None:
    """Readable view of the LLM-parsed resume; the shape varies, so render defensively."""
    if parsed.get("summary"):
        st.markdown(f"_{parsed['summary']}_")
    skills = parsed.get("skills") or []
    if skills:
        st.markdown("**Skills**")
        chip_row([str(s) for s in skills[:40]], tone="brand")
    experience = [j for j in (parsed.get("experience") or []) if isinstance(j, dict)]
    if experience:
        st.markdown("**Experience**")
        for job in experience:
            title = job.get("title") or "Role"
            company = job.get("company") or ""
            header = f"**{title}**" + (f" — {company}" if company else "")
            if job.get("duration"):
                header += f"  \n_{job['duration']}_"
            st.markdown(header)
            if job.get("description"):
                st.caption(job["description"])
    education = [e for e in (parsed.get("education") or []) if isinstance(e, dict)]
    if education:
        st.markdown("**Education**")
        for e in education:
            line = " · ".join(
                str(v) for v in (e.get("degree"), e.get("institution"), e.get("year")) if v
            )
            if line:
                st.markdown(f"- {line}")
    with st.expander("Raw parsed JSON"):
        st.json(parsed)


def page_resumes() -> None:
    page_header("📄", "Resumes")
    st.markdown("Upload up to **10 resumes**. Activate the one to use for AI features.")

    with st.expander("➕ Upload a New Resume", expanded=True):
        with st.form("upload_form"):
            label = st.text_input(
                "Resume Label (e.g. 'ML Engineer Resume')",
                placeholder="ML Engineer 2026",
            )
            file = st.file_uploader("File (PDF, DOCX, TXT)", type=["pdf", "docx", "txt"])
            if st.form_submit_button("Upload & Parse", type="primary"):
                if not label.strip():
                    show_error("Please provide a label.")
                elif not file:
                    show_error("Please select a file.")
                else:
                    with loading_spinner("Extracting text and parsing resume with AI..."):
                        resp = api(
                            "post",
                            "/resumes/upload",
                            data={"name": label},
                            files={"file": (file.name, file.getvalue(), file.type)},
                        )
                    if resp.status_code == 201:
                        show_success(f"Resume '{label}' uploaded and parsed!")
                        st.rerun()
                    else:
                        show_error(detail(resp, "Upload failed."))

    resumes_resp = api("get", "/resumes/")
    if resumes_resp.status_code != 200:
        show_error("Could not fetch resumes.")
        return

    resumes = safe_json(resumes_resp, [])
    if not resumes:
        st.info("No resumes yet. Upload one above!")
        return

    st.subheader(f"Your Resumes ({len(resumes)})")
    for r in resumes:
        active_tag = "🟢 **ACTIVE**" if r["is_active"] else "⚪ inactive"
        lifecycle_tag = lifecycle_badge(r.get("expires_at"), r.get("is_permanent", False))

        with st.expander(
            f"{active_tag}{lifecycle_tag} — {r['name']}  |  `{r['original_filename']}`"
        ):
            col1, col2, col3 = st.columns(3)
            if not r["is_active"]:
                if col1.button("✅ Set as Active", key=f"activate_{r['id']}"):
                    resp = api("put", f"/resumes/{r['id']}/activate")
                    if resp.status_code == 200:
                        show_success(f"'{r['name']}' is now your active resume.")
                        st.rerun()
                    else:
                        show_error(detail(resp, "Could not activate resume."))
            analysis_key = f"show_analysis_{r['id']}"
            if col2.button("🔍 View Analysis", key=f"analysis_{r['id']}"):
                # Toggle a flag and render below from state, so the analysis
                # stays open across reruns instead of vanishing on the next click.
                st.session_state[analysis_key] = not st.session_state.get(analysis_key, False)
            if col3.button("🗑️ Delete", key=f"delete_{r['id']}"):
                resp = api("delete", f"/resumes/{r['id']}")
                if resp.status_code == 204:
                    show_success("Deleted.")
                    st.rerun()
                else:
                    show_error(detail(resp, "Could not delete resume."))

            if st.session_state.get(analysis_key):
                analysis_resp = api("get", f"/resumes/{r['id']}/analysis")
                if analysis_resp.status_code == 200:
                    _render_analysis(safe_json(analysis_resp, {}))
                else:
                    show_error(detail(analysis_resp, "No analysis available."))
