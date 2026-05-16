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
