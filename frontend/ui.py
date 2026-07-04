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
    "inject_theme",
    "job_description_input",
    "journey",
    "lifecycle_badge",
    "loading",
    "loading_spinner",
    "metric_tile",
    "nav_to",
    "onboarding_steps",
    "page_header",
    "pipeline_progress",
    "poll_outcome",
    "poll_task",
    "render_qa_scores",
    "score_gauge",
    "score_hero",
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
# (chips, pills) that Streamlit can't style natively. All five clear WCAG AA
# (>=4.5:1) against the white pill text.
_TONE_BG = {
    "good": "#1e7e34",
    "bad": "#b02a37",
    "warn": "#8a6308",  # darkened from goldenrod (#b8860b only reached 3.25:1)
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

# One stylesheet for the whole app, injected each run from app.py. Native
# widgets are restyled through Streamlit's data-testid hooks (stable in 1.5x —
# re-check on a major Streamlit bump); the ch-* classes back our own
# components (score ring, pipeline strip, QA verdict).
_THEME_CSS = """
<style>
  :root { --ch-brand:#4f46e5; --ch-brand-2:#9333ea; --ch-ink:#1c1e26;
    --ch-muted:#5a6472; --ch-line:#e3e5ee; --ch-surface:#f7f8fb; }

  /* Buttons: pill shape, lift on hover, gentle press. */
  .stButton button, .stFormSubmitButton button, .stDownloadButton button {
    border-radius:999px !important;
    transition:transform .15s ease, box-shadow .15s ease, filter .15s ease; }
  .stButton button:hover, .stFormSubmitButton button:hover,
  .stDownloadButton button:hover {
    transform:translateY(-1px); box-shadow:0 6px 18px rgba(28,30,38,.12); }
  .stButton button:active, .stFormSubmitButton button:active {
    transform:translateY(0) scale(.99); }
  .stButton button[kind="primary"], .stFormSubmitButton button[kind="primaryFormSubmit"] {
    background:linear-gradient(92deg, var(--ch-brand), #6d28d9); border:none; }
  .stButton button[kind="primary"]:hover { filter:brightness(1.06); }

  /* Bordered containers read as cards. */
  [data-testid="stVerticalBlockBorderWrapper"] { border-radius:16px;
    box-shadow:0 4px 18px rgba(28,30,38,.05); transition:box-shadow .2s ease; }
  [data-testid="stVerticalBlockBorderWrapper"]:hover {
    box-shadow:0 10px 28px rgba(28,30,38,.09); }

  /* Metrics become tiles without touching call sites. */
  [data-testid="stMetric"] { background:var(--ch-surface);
    border:1px solid var(--ch-line); border-radius:14px; padding:.8rem 1rem; }
  [data-testid="stMetricValue"] { font-weight:800; }
  [data-testid="stMetricLabel"] { color:var(--ch-muted); }

  /* Inputs: brand focus ring. */
  [data-testid="stTextInput"] input, [data-testid="stTextArea"] textarea {
    border-radius:10px; }
  [data-testid="stTextInput"] div[data-baseweb="input"]:focus-within,
  [data-testid="stTextArea"] div[data-baseweb="textarea"]:focus-within {
    border-color:var(--ch-brand); box-shadow:0 0 0 3px rgba(79,70,229,.14); }

  /* Tabs: bolder, brand highlight. */
  .stTabs [data-baseweb="tab"] { font-weight:600; }
  .stTabs [data-baseweb="tab"]:hover { color:var(--ch-brand); }
  .stTabs [data-baseweb="tab-highlight"] { background-color:var(--ch-brand);
    height:3px; border-radius:3px; }

  /* Expanders, progress, dialogs, sidebar nav. */
  [data-testid="stExpander"] details { border-radius:12px; }
  [data-testid="stExpander"] summary:hover { color:var(--ch-brand); }
  .stProgress > div > div > div > div {
    background:linear-gradient(90deg, var(--ch-brand), var(--ch-brand-2));
    border-radius:6px; }
  [data-testid="stDialog"] div[role="dialog"] { border-radius:20px; }
  [data-testid="stSidebarNav"] a { border-radius:10px;
    transition:background .15s ease; }
  [data-testid="stSidebarNav"] a:hover { background:rgba(79,70,229,.08); }

  /* Score ring: an animated conic gauge (static where @property is missing). */
  @property --chp { syntax:'<percentage>'; inherits:false; initial-value:0%; }
  .ch-hero-score { display:flex; flex-wrap:wrap; align-items:center; gap:1.6rem;
    background:#fff; border:1px solid var(--ch-line); border-radius:16px;
    padding:1.2rem 1.4rem; box-shadow:0 12px 32px rgba(28,30,38,.08); }
  .ch-ring { width:126px; height:126px; border-radius:50%; flex:none;
    background:conic-gradient(var(--rc) var(--chp), #eceef6 0);
    display:grid; place-items:center;
    animation:ch-ring-fill .9s ease-out forwards; }
  @keyframes ch-ring-fill { from { --chp:0%; } to { --chp:var(--target); } }
  .ch-ring-in { width:96px; height:96px; border-radius:50%; background:#fff;
    display:flex; flex-direction:column; align-items:center; justify-content:center;
    font-weight:800; font-size:1.8rem; color:var(--ch-ink); }
  .ch-ring-in small { font-size:.6rem; font-weight:600; color:var(--ch-muted);
    letter-spacing:.08em; text-transform:uppercase; }
  .ch-tracks { flex:1; min-width:220px; }
  .ch-tr { display:flex; align-items:center; gap:.6rem; margin:.5rem 0;
    font-size:.8rem; color:var(--ch-muted); }
  .ch-tr > span { width:110px; flex:none; }
  .ch-tr b { color:var(--ch-ink); white-space:nowrap; }
  .ch-track { flex:1; height:8px; border-radius:4px; background:#eceef6;
    overflow:hidden; }
  .ch-track i { display:block; height:100%; border-radius:4px; width:var(--w);
    background:var(--c); transform-origin:left;
    animation:ch-grow .7s ease-out both; }
  @keyframes ch-grow { from { transform:scaleX(0); } }

  /* Pipeline strip: the landing-page vignette, driven by real step states. */
  .ch-pl { display:flex; flex-wrap:wrap; align-items:flex-start; gap:2px; }
  .ch-pn { display:flex; flex-direction:column; align-items:center; gap:3px;
    width:60px; }
  .ch-pn span { width:38px; height:38px; border-radius:50%; background:#fff;
    border:2px solid var(--ch-line); display:grid; place-items:center;
    font-size:1rem; transition:border-color .2s ease, background .2s ease; }
  .ch-pn small { font-size:.62rem; color:var(--ch-muted); }
  .ch-pl i.ch-pl-link { width:10px; height:2px; background:var(--ch-line);
    margin-top:18px; }
  .ch-pn-done span { border-color:var(--ch-brand); background:#eef0fe; }
  .ch-pn-running span { border-color:var(--ch-brand);
    animation:ch-pn-pulse 1.4s ease-in-out infinite; }
  .ch-pn-failed span { border-color:#b02a37; background:#fdecee; }
  .ch-pn-skipped span { border-style:dashed; opacity:.65; }
  .ch-pn-pending span { opacity:.75; }
  @keyframes ch-pn-pulse {
    0%, 100% { box-shadow:0 0 0 0 rgba(79,70,229,.4); }
    50% { box-shadow:0 0 0 7px rgba(79,70,229,0); }
  }

  /* QA verdict: the judge stamp from the landing story, on real scores. */
  .ch-qa { display:flex; align-items:center; gap:.9rem; margin:.3rem 0 .5rem; }
  .ch-qa-stamp { display:inline-block; transform:rotate(-2deg); background:#fff;
    border:2px solid var(--c); color:var(--c); font-weight:700; font-size:.85rem;
    padding:.3rem .7rem; border-radius:8px; }
  .ch-qa-tone { display:inline-block; background:var(--ch-surface);
    border:1px solid var(--ch-line); color:var(--ch-ink); font-weight:600;
    font-size:.8rem; padding:.3rem .7rem; border-radius:999px; }

  @media (prefers-reduced-motion: reduce) {
    * { animation:none !important; transition:none !important; }
  }
</style>
"""


def inject_theme() -> None:
    """Mount the app-wide stylesheet — app.py calls this once per run."""
    st.html(_THEME_CSS)


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


def _clamp_pct(value: float) -> int:
    return int(0 if value < 0 else 100 if value > 100 else value)


def _score_hero_html(score: float, parts: list[dict], center_label: str) -> str:
    """Ring + component tracks; each part is {label, value, note?}."""
    pct = _clamp_pct(score)
    ring_color = _TONE_BG[score_tone(pct)]
    rows = []
    for p in parts:
        v = _clamp_pct(p.get("value", 0))
        note = f" · {p['note']}" if p.get("note") else ""
        rows.append(
            f'<div class="ch-tr"><span>{p["label"]}</span>'
            f'<div class="ch-track"><i style="--w:{v}%; --c:{_TONE_BG[score_tone(v)]}"></i></div>'
            f"<b>{v}%{note}</b></div>"
        )
    return (
        '<div class="ch-hero-score">'
        f'<div class="ch-ring" style="--target:{pct}%; --rc:{ring_color}">'
        f'<div class="ch-ring-in">{pct}<small>{html.escape(center_label)}</small></div></div>'
        f'<div class="ch-tracks">{"".join(rows)}</div>'
        "</div>"
    )


def score_hero(score: float, parts: list[dict], center_label: str = "score") -> None:
    """The flagship scorecard: animated ring + a track per component score."""
    st.html(_score_hero_html(score, parts, center_label))


def _pipeline_html(nodes: list[dict]) -> str:
    """Node strip; each node is {icon, label, state} with state ∈ the ch-pn-* set."""
    bits = []
    for i, n in enumerate(nodes):
        bits.append(
            f'<div class="ch-pn ch-pn-{n["state"]}"><span>{n["icon"]}</span>'
            f"<small>{html.escape(n['label'])}</small></div>"
        )
        if i < len(nodes) - 1:
            bits.append('<i class="ch-pl-link"></i>')
    return f'<div class="ch-pl">{"".join(bits)}</div>'


def pipeline_progress(nodes: list[dict]) -> None:
    """Live pipeline strip — the landing-page vignette wired to real step states."""
    st.html(_pipeline_html(nodes))


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
