"""Dashboard page — stats overview and quick actions."""

import requests
import streamlit as st

from api_client import api, safe_json


@st.cache_data(ttl=30, show_spinner=False)
def _load_stats(token: str) -> dict:
    """Fetch dashboard counts for `token`.

    Returns {"ok": True, "data": {...}} on success, else {"ok": False, ...}
    describing the failure (kind / which call / status) so the page can show an
    honest message instead of always blaming a cold start.

    `token` is only the cache key (one entry per user); api() injects the real
    auth header from session state.
    """
    calls = {
        "resumes": ("/resumes/", []),
        "jobs": ("/jobs/stats", {}),
        "cover_letters": ("/cover-letters/", []),
    }
    data = {}
    for key, (path, empty) in calls.items():
        try:
            resp = api("get", path)
        except requests.exceptions.RequestException:
            return {"ok": False, "kind": "network", "where": path, "status": None}
        if not resp.ok:
            kind = "auth" if resp.status_code in (401, 403) else "server"
            return {"ok": False, "kind": kind, "where": path, "status": resp.status_code}
        data[key] = safe_json(resp, empty)
    return {"ok": True, "data": data}


def page_dashboard() -> None:
    st.title("📋 Dashboard")

    if not st.session_state.token:
        return

    result = _load_stats(st.session_state.token)
    if not result["ok"]:
        kind = result["kind"]
        if kind == "auth":
            st.error(
                "🔒 **Your session expired.** Please use **Logout** in the sidebar, "
                "then sign in again."
            )
        elif kind == "network":
            st.warning(
                "⏳ **Couldn't reach the server** — it may be waking from a cold "
                "start (~90s). Your data is safe; try again in a moment."
            )
        else:  # server error — a real 5xx, not a cold start
            st.error(
                f"⚠️ **Server error loading your stats** "
                f"(`{result['where']}` → HTTP {result['status']}). "
                "Your data is safe and this has been logged. Please try again shortly."
            )
        if st.button("🔄 Retry"):
            _load_stats.clear()
            st.rerun()
        return

    stats = result["data"]
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
