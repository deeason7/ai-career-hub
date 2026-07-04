"""Dashboard page — the home view: counts, pipeline, and journey shortcuts."""

import requests
import streamlit as st

import tour
from api_client import api, safe_json
from ui import (
    card,
    error_state,
    journey,
    metric_tile,
    nav_to,
    onboarding_steps,
    page_header,
    status_icon,
)


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


def page_dashboard() -> None:
    page_header("🏠", "Home")

    if not st.session_state.token:
        return

    # Streamlit allows one open dialog per run — wait until the disclaimer
    # modal (app.py) has been accepted before offering the tour dialog.
    if st.session_state.get("disclaimer_accepted"):
        tour.prompt()
    tour.offer()

    try:
        stats = _load_stats(st.session_state.token)
    except requests.exceptions.RequestException as exc:
        resp = getattr(exc, "response", None)
        error_state(resp if resp is not None else "network")
        if st.button("🔄 Retry"):
            _load_stats.clear()
            st.rerun()
        return

    resumes = stats["resumes"] if isinstance(stats["resumes"], list) else []
    jobs = stats["jobs"] if isinstance(stats["jobs"], dict) else {}
    cover_letters = stats["cover_letters"] if isinstance(stats["cover_letters"], list) else []

    by_status = jobs.get("by_status") or {}
    has_resume, has_letter = bool(resumes), bool(cover_letters)
    has_applied = any(s != "wishlist" and c for s, c in by_status.items())

    # Onboarding stepper: walk a new account resume → draft → apply & track. It
    # disappears once an application moves past "wishlist" — the journey is done
    # and the full dashboard takes over. A brand-new account (no resume) sees the
    # stepper alone, not a wall of zeros.
    if not (has_resume and has_letter and has_applied):
        st.subheader("👋 Get set up")
        st.caption("Three steps from here to your first tracked application.")
        nxt = journey(onboarding_steps(has_resume, has_letter, has_applied))
        if nxt:
            nav_to(nxt)
        if not has_resume:
            return
        st.divider()

    col1, col2, col3 = st.columns(3)
    with col1:
        metric_tile("📄 Resumes", len(resumes))
    with col2:
        metric_tile("✉️ Cover Letters", len(cover_letters))
    with col3:
        metric_tile("📊 Applications", jobs.get("total", 0))

    st.divider()

    # The flagship fast path gets the hero spot.
    active_name = next((r["name"] for r in resumes if r.get("is_active")), None)
    with card("✨ Quick Apply"):
        st.caption(
            f"Paste a job URL and the agent scores **{active_name or 'your resume'}** "
            "against it, researches the company, and drafts the letter — one click."
        )
        if st.button("Run Quick Apply", type="primary"):
            nav_to("agent")

    if by_status:
        st.subheader("Application Pipeline")
        cols = st.columns(len(by_status))
        for col, (s, count) in zip(cols, by_status.items(), strict=True):
            with col:
                metric_tile(f"{status_icon(s)} {s.replace('_', ' ').title()}", count)

    if cover_letters:
        st.subheader("Recent Cover Letters")
        for cl in cover_letters[:3]:
            with card(f"✉️ {cl.get('created_at', '')[:10]} · `{cl.get('status', '')}`"):
                preview = (cl.get("generated_text") or "")[:160]
                st.caption(f"{preview}…" if preview else "Generating…")
                if st.button("Open", key=f"open_cl_{cl['id']}"):
                    st.session_state["active_cl_id"] = cl["id"]
                    nav_to("cover_letter")

    st.divider()
    st.subheader("🚀 Quick Actions")
    q1, q2, q3 = st.columns(3)
    if q1.button("📄 Upload Resume", use_container_width=True):
        nav_to("resumes")
    if q2.button("✉️ Generate Cover Letter", use_container_width=True):
        nav_to("cover_letter")
    if q3.button("🎯 Score My Resume", use_container_width=True):
        nav_to("job_match")
