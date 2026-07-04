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
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=UTC)
        days_left = (exp - datetime.now(UTC)).days
        if days_left < 0:
            return "  🔴 expired"
        elif days_left == 0:
            return "  🔴 expires today"
        elif days_left <= 3:
            return f"  🟠 expires in {days_left}d"
        else:
            return f"  🗓️ expires in {days_left}d"
    except (ValueError, AttributeError, TypeError):
        return ""


def loading_spinner(label: str = "Working…"):
    """Return a context manager for a spinner with a consistent label style."""
    return st.spinner(f"⏳ {label}")


# Mirrors the backend HALLUCINATION_THRESHOLD: honesty below this is where generation
# would auto-regenerate, so surface it in red here too.
_HONESTY_OK = 6


def render_qa_scores(honesty: int | None, tone: int | None, flags: str | None) -> None:
    """Show a revision's QA honesty/tone scores and any flags.

    `flags` arrives as a JSON-encoded list (or None) on the revision payload.
    """
    if honesty is None:
        return
    ok = honesty >= _HONESTY_OK
    color = "#1e7e34" if ok else "#b02a37"
    tone_chip = f'<span class="ch-qa-tone">🎯 Tone {tone}/10</span>' if tone is not None else ""
    st.html(
        f'<div class="ch-qa"><span class="ch-qa-stamp" style="--c:{color}">'
        f"{'✓' if ok else '✗'} Honesty {honesty}/10</span>{tone_chip}</div>"
    )
    if not flags:
        return

    import json

    try:
        parsed = json.loads(flags)
    except (ValueError, TypeError):
        parsed = []
    if parsed:
        st.warning("⚠️ QA flags:\n" + "\n".join(f"- {f}" for f in parsed))


_SHARED_JD_KEY = "shared_jd"


def job_description_input(page_key: str, height: int = 280, label: str = "Job Description") -> str:
    """A job-description field shared across pages.

    The JD lives in st.session_state['shared_jd'], so pasting or importing it on
    one page (Cover Letter) carries to others (Job Match) for the session. Each
    page seeds its own text widget from the shared value and syncs edits back;
    `page_key` just keeps the per-page widget keys unique.
    """
    st.session_state.setdefault(_SHARED_JD_KEY, "")
    _job_url_import(page_key)

    widget_key = f"jd_input_{page_key}"
    if widget_key not in st.session_state:
        st.session_state[widget_key] = st.session_state[_SHARED_JD_KEY]
    jd = st.text_area(
        label,
        height=height,
        key=widget_key,
        placeholder="Paste the full job posting here, or import from URL above.",
    )
    st.session_state[_SHARED_JD_KEY] = jd
    return jd


def seed_shared_jd(text: str) -> None:
    """Programmatically fill the shared JD (the tour's sample job uses this).

    Owns the same keys as job_description_input: update the shared value and
    drop each page's widget copy so its next render re-seeds from the new text.
    """
    st.session_state[_SHARED_JD_KEY] = text
    for page_key in ("job_match", "cover_letter"):
        st.session_state.pop(f"jd_input_{page_key}", None)


def _job_url_import(page_key: str) -> None:
    """'Import from URL' expander; on success writes the JD into the shared field."""
    from api_client import api, detail, safe_json

    with st.expander("🔗 Import Job from URL (LinkedIn, Greenhouse, Lever…)"):
        st.caption(
            "Paste any public job posting URL. LinkedIn may require login — "
            "in that case paste the text manually."
        )
        url = st.text_input(
            "Job Posting URL",
            placeholder="https://www.linkedin.com/jobs/view/...",
            key=f"{page_key}_url_input",
        )
        if st.button("🚀 Fetch Job Description", key=f"{page_key}_fetch_btn"):
            if not url.strip():
                show_error("Please enter a URL.")
                return
            with loading_spinner("Fetching job description…"):
                resp = api("post", "/ai/fetch-job", json={"url": url.strip()})
            data = safe_json(resp, {})
            if resp.status_code == 200 and data.get("success"):
                st.session_state[_SHARED_JD_KEY] = data.get("job_description", "")
                st.session_state.pop(f"jd_input_{page_key}", None)
                if data.get("warning"):
                    st.warning(data["warning"])
                show_success("Job description fetched — filled in below.")
                st.rerun()
            else:
                show_error(detail(resp, "Could not fetch job description."))
