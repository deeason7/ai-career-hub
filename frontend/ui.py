"""Design-system primitives for the frontend.

One shared vocabulary — headers, cards, metrics, score gauges, chips, status
pills, and honest empty/loading/error states — so styling lives here instead of
being re-invented per page. Pages import everything they need from this module.
"""

import html

import requests
import streamlit as st

from components import (
    job_description_input,
    lifecycle_badge,
    loading_spinner,
    render_qa_scores,
    show_error,
    show_success,
    toast_error,
    toast_success,
)

__all__ = [
    "card",
    "chip_row",
    "empty_state",
    "error_state",
    "job_description_input",
    "journey",
    "lifecycle_badge",
    "loading",
    "loading_spinner",
    "metric_tile",
    "nav_to",
    "onboarding_steps",
    "page_header",
    "poll_outcome",
    "poll_task",
    "render_qa_scores",
    "score_gauge",
    "score_tone",
    "section",
    "show_error",
    "show_success",
    "status_icon",
    "status_pill",
    "toast_error",
    "toast_success",
]

# Semantic colors mirror the chips already used across the app, centralized so
# every good/bad/warn surface agrees. The brand color lives in the theme
# (.streamlit/config.toml); these are only for the few inline-HTML bits
# (chips, pills) that Streamlit can't style natively.
_TONE_BG = {
    "good": "#1e7e34",
    "bad": "#b02a37",
    "warn": "#b8860b",
    "brand": "#4f46e5",
    "neutral": "#5a6472",
}
_TONE_DOT = {"good": "🟢", "warn": "🟡", "bad": "🔴", "neutral": "⚪"}

# Job-application status → (icon, tone). Single source of truth shared by the
# tracker and any page that shows a status (mirrors the backend's status set).
_STATUS_META = {
    "wishlist": ("💭", "neutral"),
    "applied": ("📤", "brand"),
    "phone_screen": ("📞", "brand"),
    "interview": ("🎯", "warn"),
    "offer": ("🎉", "good"),
    "accepted": ("✅", "good"),
    "rejected": ("❌", "bad"),
}


def score_tone(value: float, good: float = 70, ok: float = 45) -> str:
    """Map a 0–100 score to a tone — the one home for the 🟢/🟡/🔴 thresholds."""
    if value >= good:
        return "good"
    if value >= ok:
        return "warn"
    return "bad"


def page_header(icon: str, title: str, subtitle: str | None = None) -> None:
    """Consistent page title block: icon + title, with an optional one-liner."""
    st.title(f"{icon} {title}")
    if subtitle:
        st.caption(subtitle)


def section(title: str, help: str | None = None) -> None:
    """Consistent subheader for a section within a page."""
    st.subheader(title, help=help)


def card(title: str | None = None):
    """A bordered container (use as a context manager); optional header inside."""
    container = st.container(border=True)
    if title:
        container.markdown(f"**{title}**")
    return container


def metric_tile(
    label: str,
    value: str | int | float,
    tone: str | None = None,
    help: str | None = None,
) -> None:
    """Uniform metric; an optional tone prefixes a status dot (🟢/🟡/🔴)."""
    if tone:
        label = f"{_TONE_DOT.get(tone, '')} {label}".strip()
    st.metric(label, value, help=help)


def score_gauge(value: float, label: str, max: int = 100) -> None:
    """Score visual: a tone-dotted big number plus a native progress bar."""
    ratio = value / max if max else 0.0
    ratio = 0.0 if ratio < 0 else 1.0 if ratio > 1 else ratio
    display = f"{value:.0f}%" if max == 100 else f"{value:g}/{max}"
    metric_tile(label, display, tone=score_tone(ratio * 100))
    st.progress(ratio)


def chip_row(items: list, tone: str = "neutral") -> None:
    """Render escaped pill-chips in one place (replaces ad-hoc inline-HTML spans)."""
    labels = [str(i) for i in items if str(i).strip()]
    if not labels:
        st.write("—")
        return
    bg = _TONE_BG.get(tone, _TONE_BG["neutral"])
    chips = " ".join(
        f'<span style="background:{bg};color:#fff;padding:2px 8px;border-radius:12px;'
        f'font-size:0.82em;margin:2px;display:inline-block">{html.escape(c)}</span>'
        for c in labels
    )
    st.markdown(chips, unsafe_allow_html=True)


def status_pill(status: str) -> None:
    """Job-application status as a colored pill — one place defines the look."""
    icon, tone = _STATUS_META.get(status, ("•", "neutral"))
    bg = _TONE_BG.get(tone, _TONE_BG["neutral"])
    label = html.escape(status.replace("_", " ").title())
    st.markdown(
        f'<span style="background:{bg};color:#fff;padding:2px 10px;border-radius:12px;'
        f'font-size:0.85em;display:inline-block">{icon} {label}</span>',
        unsafe_allow_html=True,
    )


def status_icon(status: str) -> str:
    """The icon half of status_pill, for plain-text spots like expander titles."""
    return _STATUS_META.get(status, ("•", "neutral"))[0]


def nav_to(key: str) -> None:
    """Switch to a page registered in app.py's nav registry; no-op if unknown."""
    page = st.session_state.get("_nav", {}).get(key)
    if page is not None:
        st.switch_page(page)


def empty_state(icon: str, title: str, body: str, cta: str | None = None) -> bool:
    """Canonical 'nothing here yet' block; returns True if the optional CTA is clicked."""
    st.markdown(f"### {icon} {title}")
    st.caption(body)
    if cta:
        return st.button(cta, type="primary")
    return False


def onboarding_steps(has_resume: bool, has_letter: bool, has_applied: bool) -> list[dict]:
    """The 3-step onboarding journey, built from account state (pure — drives `journey`)."""
    return [
        {
            "done": has_resume,
            "icon": "📄",
            "label": "Upload a resume",
            "cta": "Upload your first resume",
            "nav": "resumes",
        },
        {
            "done": has_letter,
            "icon": "✨",
            "label": "Draft an application",
            "cta": "Run Quick Apply",
            "nav": "agent",
        },
        {
            "done": has_applied,
            "icon": "📊",
            "label": "Apply & track",
            "cta": "Open your tracker",
            "nav": "tracker",
        },
    ]


def _active_step(steps: list[dict]) -> int | None:
    """Index of the first not-done step, or None when every step is done."""
    return next((i for i, s in enumerate(steps) if not s.get("done")), None)


def journey(steps: list[dict]) -> str | None:
    """Render the onboarding stepper; return the active step's nav key if its CTA is clicked.

    Done steps show a check, the first not-done step is highlighted with its CTA,
    later steps are muted. The caller does the `nav_to`, keeping this a pure render
    (mirrors `empty_state`). Pairs with `onboarding_steps`.
    """
    active = _active_step(steps)
    clicked: str | None = None
    for i, (col, step) in enumerate(zip(st.columns(len(steps)), steps, strict=True)):
        with col:
            if step.get("done"):
                st.markdown("### ✅")
                st.caption(step["label"])
            elif i == active:
                st.markdown(f"### {step['icon']}")
                st.markdown(f"**{step['label']}**")
                if step.get("cta") and st.button(
                    step["cta"], type="primary", key=f"journey_{step['nav']}"
                ):
                    clicked = step["nav"]
            else:
                st.markdown(f"### {step['icon']}")
                st.caption(step["label"])
    return clicked


def error_state(resp_or_kind: requests.Response | str) -> None:
    """Render an honest error — auth vs cold-start vs network vs server/client.

    Accepts a Response or an explicit kind string. Never collapses a 401 or a
    5xx into a generic "cold start", which is the bug this replaces.
    """
    from api_client import detail  # lazy: keep this module import-light

    if isinstance(resp_or_kind, str):
        kind, resp = resp_or_kind, None
    else:
        resp = resp_or_kind
        kind = _classify(getattr(resp, "status_code", None))

    if kind == "auth":
        st.warning("🔒 Your session has expired. Please log in again.")
    elif kind == "cold":
        st.info("⏳ The server is waking up. Give it ~30 seconds, then retry.")
    elif kind == "network":
        st.error("🌐 Couldn't reach the server. Check your connection and retry.")
    elif kind == "rate":
        st.warning("🚦 Too many requests — wait a minute and try again.")
    else:
        st.error(f"❌ {detail(resp) if resp is not None else 'Something went wrong.'}")


def _classify(code: int | None) -> str:
    if code in (401, 403):
        return "auth"
    if code == 429:
        return "rate"
    if code in (502, 503, 504):
        return "cold"
    if code is None:
        return "network"
    return "server"


def poll_task(path: str) -> tuple[int | None, dict]:
    """One tick of an async-task poll: (http_status, payload); (None, {}) on a network blip."""
    from api_client import api, safe_json  # lazy: keep this module import-light

    try:
        resp = api("get", path)
    except requests.RequestException:
        return None, {}
    return resp.status_code, safe_json(resp, {}) or {}


def poll_outcome(
    http_status: int | None, task_status: str | None, elapsed: float, timeout_s: float
) -> str:
    """Classify one poll tick of a background task.

    Transient trouble (a network blip, a 5xx) reads as "running" so a hiccup
    doesn't kill the poll; the elapsed cap is the backstop.
    """
    if http_status == 404:
        return "lost"  # unknown or expired task id
    if http_status in (401, 403):
        return "auth"
    if task_status == "SUCCESS":
        return "done"
    if task_status == "FAILURE":
        return "failed"
    if elapsed > timeout_s:
        return "timeout"
    return "running"


def loading(label: str = "Working…"):
    """Consistent spinner (context manager) — the design-system name for it."""
    return st.spinner(f"⏳ {label}")
