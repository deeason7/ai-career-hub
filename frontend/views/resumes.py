"""Resumes page — upload, list, activate, delete."""

import streamlit as st

from api_client import api, detail, safe_json
from components import lifecycle_badge, loading_spinner, show_error, show_success
from ui import page_header


def page_resumes() -> None:
    page_header("📄", "Resumes")
    st.markdown("Upload up to **10 resumes**. Activate the one to use for AI features.")

    with st.expander("➕ Upload a New Resume", expanded=True):
        with st.form("upload_form"):
            label = st.text_input(
                "Resume Label (e.g. 'ML Engineer Resume')",
                placeholder="ML Engineer 2026",
            )
            file = st.file_uploader(
                "File (PDF, DOCX, TXT)", type=["pdf", "docx", "txt"]
            )
            if st.form_submit_button("Upload & Parse", type="primary"):
                if not label.strip():
                    show_error("Please provide a label.")
                elif not file:
                    show_error("Please select a file.")
                else:
                    with loading_spinner(
                        "Extracting text and parsing resume with AI..."
                    ):
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
        lifecycle_tag = lifecycle_badge(
            r.get("expires_at"), r.get("is_permanent", False)
        )

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
            if col2.button("🔍 View Analysis", key=f"analysis_{r['id']}"):
                analysis_resp = api("get", f"/resumes/{r['id']}/analysis")
                if analysis_resp.status_code == 200:
                    st.json(analysis_resp.json())
                else:
                    show_error("No analysis available.")
            if col3.button("🗑️ Delete", key=f"delete_{r['id']}"):
                resp = api("delete", f"/resumes/{r['id']}")
                if resp.status_code == 204:
                    show_success("Deleted.")
                    st.rerun()
                else:
                    show_error(detail(resp, "Could not delete resume."))
