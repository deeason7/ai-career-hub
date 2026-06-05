"""Dashboard page — stats overview and quick actions."""

import requests
import streamlit as st

from api_client import api, safe_json


@st.cache_data(ttl=30, show_spinner=False)
def _load_stats(token: str) -> dict | None:
    """Fetch dashboard counts for `token`; None if the API is unreachable.

    `token` is only the cache key (one entry per user); api() injects the real
    auth header from session state.
    """
    try:
        resumes = api("get", "/resumes/")
        jobs = api("get", "/jobs/stats")
        cover_letters = api("get", "/cover-letters/")
    except requests.exceptions.RequestException:
        return None
    if not (resumes.ok and jobs.ok and cover_letters.ok):
        return None
    return {
        "resumes": safe_json(resumes, []),
        "jobs": safe_json(jobs, {}),
        "cover_letters": safe_json(cover_letters, []),
    }


def page_dashboard() -> None:
    st.title("📋 Dashboard")

    if not st.session_state.token:
        return

    stats = _load_stats(st.session_state.token)
    if stats is None:
        st.warning(
            "⏳ **Couldn't load your stats** — the server may be waking from a "
            "cold start (~90s). Your data is safe; try again in a moment."
        )
        if st.button("🔄 Retry"):
            _load_stats.clear()
            st.rerun()
        return

    resumes = stats["resumes"]
    jobs = stats["jobs"]
    cover_letters = stats["cover_letters"]

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
