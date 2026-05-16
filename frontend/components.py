"""Shared UI primitives — notifications, badges, spinners."""

import streamlit as st


def show_error(msg: str) -> None:
    st.error(f"❌ {msg}")


def show_success(msg: str) -> None:
    st.success(f"✅ {msg}")


def toast_error(msg: str) -> None:
    """Toast-style error notification (non-blocking)."""
    st.toast(f"❌ {msg}", icon="🚨")


def toast_success(msg: str) -> None:
    """Toast-style success notification (non-blocking)."""
    st.toast(f"✅ {msg}", icon="🎉")


def lifecycle_badge(expires_at: str | None, is_permanent: bool = False) -> str:
    """Return a lifecycle status badge string for display in expander headers."""
    if is_permanent:
        return "  📌 permanent"
    if not expires_at:
        return ""
    from datetime import UTC, datetime
    try:
        exp = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        days_left = (exp - datetime.now(UTC)).days
        if days_left < 0:
            return "  🔴 expired"
        elif days_left == 0:
            return "  🔴 expires today"
        elif days_left <= 3:
            return f"  🟠 expires in {days_left}d"
        else:
            return f"  🗓️ expires in {days_left}d"
    except (ValueError, AttributeError):
        return ""


def loading_spinner(label: str = "Working…"):
    """Return a context manager for a spinner with a consistent label style."""
    return st.spinner(f"⏳ {label}")


def job_url_import(key_prefix: str) -> str:
    """Collapsible 'Import from URL' expander used on Cover Letter and Job Match pages.

    Returns the fetched job description text, or the previously fetched value
    stored in session state (empty string if never fetched).
    """
    from api_client import api, detail, safe_json

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
                with loading_spinner("Fetching job description…"):
                    resp = api("post", "/ai/fetch-job", json={"url": job_url_input.strip()})
                data = safe_json(resp, {})
                if resp.status_code == 200 and data.get("success"):
                    st.session_state[f"{key_prefix}_prefilled_jd"] = data.get("job_description", "")
                    show_success("Job description fetched! Scroll down — it's pre-filled below.")
                    if data.get("warning"):
                        st.warning(data["warning"])
                else:
                    show_error(detail(resp, "Could not fetch job description."))
    return st.session_state.get(f"{key_prefix}_prefilled_jd", "")
