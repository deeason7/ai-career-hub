"""Dashboard page — stats overview and quick actions."""

import streamlit as st

from api_client import api, safe_json


def page_dashboard() -> None:
    st.title("📋 Dashboard")

    resumes = safe_json(api("get", "/resumes/"), []) if st.session_state.token else []
    jobs = safe_json(api("get", "/jobs/stats"), {}) if st.session_state.token else {}
    cover_letters = (
        safe_json(api("get", "/cover-letters/"), []) if st.session_state.token else []
    )

    col1, col2, col3 = st.columns(3)
    col1.metric("📄 Resumes", len(resumes) if isinstance(resumes, list) else 0)
    col2.metric(
        "✉️ Cover Letters", len(cover_letters) if isinstance(cover_letters, list) else 0
    )
    col3.metric(
        "📊 Applications", jobs.get("total", 0) if isinstance(jobs, dict) else 0
    )

    st.divider()
    st.subheader("Application Pipeline")
    if isinstance(jobs, dict) and "by_status" in jobs:
        statuses = jobs["by_status"]
        cols = st.columns(len(statuses))
        status_emojis = {
            "wishlist": "⭐",
            "applied": "📨",
            "phone_screen": "📞",
            "interview": "🎯",
            "offer": "🎉",
            "rejected": "❌",
            "accepted": "✅",
        }
        for col, (s, count) in zip(cols, statuses.items()):
            col.metric(
                f"{status_emojis.get(s, '')} {s.replace('_', ' ').title()}", count
            )

    st.divider()
    st.subheader("🚀 Quick Actions")
    q1, q2, q3 = st.columns(3)
    if q1.button("📄 Upload Resume", use_container_width=True, type="primary"):
        st.session_state["current_page"] = "📄 My Resumes"
        st.rerun()
    if q2.button("✉️ Generate Cover Letter", use_container_width=True, type="primary"):
        st.session_state["current_page"] = "✉️ Cover Letter"
        st.rerun()
    if q3.button("🎯 Score My Resume", use_container_width=True, type="primary"):
        st.session_state["current_page"] = "🎯 Job Match Analysis"
        st.rerun()
