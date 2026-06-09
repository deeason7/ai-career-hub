"""Dashboard page — stats overview and quick actions."""

import requests
import streamlit as st

from api_client import api, safe_json
from ui import error_state, page_header


@st.cache_data(ttl=30, show_spinner=False)
def _load_stats(token: str) -> dict:
    """Fetch dashboard counts for `token`; raise on failure.

    Raising (vs returning None) keeps st.cache_data from caching the error, so a
    retry re-fetches; the caller classifies the failure via ui.error_state.
    `token` is only the cache key (one entry per user); api() injects the real
    auth header from session state.
    """
    resumes = api("get", "/resumes/")
    jobs = api("get", "/jobs/stats")
    cover_letters = api("get", "/cover-letters/")
    for r in (resumes, jobs, cover_letters):
        r.raise_for_status()
    return {
        "resumes": safe_json(resumes, []),
        "jobs": safe_json(jobs, {}),
        "cover_letters": safe_json(cover_letters, []),
    }


def _go(key: str) -> None:
    """Switch to a page registered in app.py's nav registry."""
    page = st.session_state.get("_nav", {}).get(key)
    if page is not None:
        st.switch_page(page)


def page_dashboard() -> None:
    page_header("🏠", "Home")

    if not st.session_state.token:
        return

    try:
        stats = _load_stats(st.session_state.token)
    except requests.exceptions.RequestException as exc:
        resp = getattr(exc, "response", None)
        error_state(resp if resp is not None else "network")
        if st.button("🔄 Retry"):
            _load_stats.clear()
            st.rerun()
        return

    resumes = stats["resumes"]
    jobs = stats["jobs"]
    cover_letters = stats["cover_letters"]

    col1, col2, col3 = st.columns(3)
    col1.metric("📄 Resumes", len(resumes) if isinstance(resumes, list) else 0)
    col2.metric("✉️ Cover Letters", len(cover_letters) if isinstance(cover_letters, list) else 0)
    col3.metric("📊 Applications", jobs.get("total", 0) if isinstance(jobs, dict) else 0)

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
        for col, (s, count) in zip(cols, statuses.items(), strict=True):
            col.metric(f"{status_emojis.get(s, '')} {s.replace('_', ' ').title()}", count)

    st.divider()
    st.subheader("🚀 Quick Actions")
    q1, q2, q3 = st.columns(3)
    if q1.button("📄 Upload Resume", use_container_width=True, type="primary"):
        _go("resumes")
    if q2.button("✉️ Generate Cover Letter", use_container_width=True, type="primary"):
        _go("cover_letter")
    if q3.button("🎯 Score My Resume", use_container_width=True, type="primary"):
        _go("job_match")
