"""Guided product tour — a Back/Next rail that walks the live app page by page.

The route is data (STEPS); a single render() call in app.py draws the rail
above whatever page is active, so no view knows the tour exists. Wander off
the route and the rail re-syncs to the nearest step for wherever you landed —
it guides, it doesn't cage. Pages that aren't on the route (Legal) just hide
it until you're back.
"""

from __future__ import annotations

import streamlit as st

from components import seed_shared_jd
from ui import nav_to

_STEP_KEY = "tour_step"  # int while touring · None = ended · absent = never started
_OFFER_KEY = "tour_offer_dismissed"
_PROMPT_KEY = "tour_prompted"  # welcome dialog shown this session, whatever the outcome
_FINISHED_KEY = "_tour_finished"  # one-shot: celebrate on the run after Finish

# A believable posting so visitors can feel Job Match and Cover Letter without
# hunting for a real ad first. Plain text, the same shape a paste would have.
_SAMPLE_JD = """\
Backend Engineer — Platform Team
Northwind Labs · Remote · Full-time

We build the APIs behind Northwind's logistics network. You'll design and ship
Python services with FastAPI, model data in PostgreSQL, and keep Redis-backed
queues healthy in production on AWS.

What you'll do
- Own services end to end: design, tests, deploy, observe
- Tune slow queries and cache hot paths
- Review code and mentor junior engineers

What we look for
- 3+ years building production Python web services
- Solid SQL and schema design; Docker and CI/CD fluency
- Bonus: LLM API integration, vector search, or Terraform
"""

# Each step: the nav-registry key it belongs to (app.py's `_nav`), two
# sentences of what-this-is, and one thing to try. `sample` steps offer to
# pre-fill the shared job description so there's something real to click.
STEPS = [
    {
        "page": "home",
        "icon": "🏠",
        "title": "Welcome to AI Career Hub",
        "body": "Everything here exists to get a real application out the door: your "
        "resume in, honest AI letters and scores out, one tracker over all of it.",
        "try": "Press **Next** to walk through — or wander off, the tour follows you.",
    },
    {
        "page": "resumes",
        "icon": "📄",
        "title": "Resumes are the fuel",
        "body": "Upload a PDF or DOCX and it's parsed into structured skills and "
        "experience, then indexed for retrieval — every score and letter downstream "
        "is grounded in *your* text, not invented filler.",
        "try": "Upload a resume (skip anything sensitive) and open its analysis.",
    },
    {
        "page": "job_match",
        "icon": "🎯",
        "title": "Score before you apply",
        "body": "Paste a job description and a hybrid ATS engine grades the match — "
        "half semantic similarity, the rest keywords and structure — then maps your "
        "skill gaps and drafts the interview questions this posting would raise.",
        "try": "No posting handy? Load the sample job below, then hit Analyze.",
        "sample": True,
    },
    {
        "page": "cover_letter",
        "icon": "✉️",
        "title": "Letters that survive review",
        "body": "A first pass drafts from your resume and the posting; a second AI "
        "pass judges honesty and tone, and low-honesty drafts regenerate before you "
        "see them. Refine any version with an instruction and branch the history.",
        "try": "Generate once, then refine with something like *make it more direct*.",
        "sample": True,
    },
    {
        "page": "tracker",
        "icon": "📊",
        "title": "One board over every application",
        "body": "Wishlist to offer, each application sits at exactly one stage — and "
        "letters you generate file themselves here automatically, so nothing slips.",
        "try": "Move an application's status and watch the pipeline on Home update.",
    },
    {
        "page": "agent",
        "icon": "✨",
        "title": "Quick Apply — the whole loop, one URL",
        "body": "Paste a job posting URL and a seven-step agent scrapes it, researches "
        "the company, scores your resume, maps the gaps, writes the letter, and preps "
        "interview questions — each step ticking live as it lands.",
        "try": "Paste any public job URL and run it end to end.",
    },
    {
        "page": "home",
        "icon": "🧭",
        "title": "That's the tour",
        "body": "Upload once, score everything, apply with letters that pass an "
        "honesty check, track it all. Documents expire after 15 days unless you pin "
        "them — details in 📜 Legal & Info. Replay this any time from the sidebar.",
        "try": None,
    },
]

# Palette mirrors .streamlit/config.toml (brand) and ui's neutrals.
_RAIL_CSS = """
<style>
  .ch-tour-head { display:flex; align-items:center; gap:.6rem;
    animation: ch-tour-in .35s ease-out both; }
  .ch-tour-icon { font-size:1.45rem; line-height:1; }
  .ch-tour-title { font-weight:700; font-size:1.05rem; }
  .ch-tour-count { margin-left:auto; font-size:.85rem; color:#5a6472;
    white-space:nowrap; }
  .ch-dots { display:flex; gap:6px; margin-top:.45rem; }
  .ch-dot { width:8px; height:8px; border-radius:50%; background:#d9dbe3;
    transition:background .3s; }
  .ch-dot-done { background:#4f46e5; }
  .ch-dot-now { background:#4f46e5;
    animation: ch-dot-pulse 1.6s ease-in-out infinite; }
  @keyframes ch-dot-pulse {
    0%, 100% { box-shadow:0 0 0 0 rgba(79,70,229,.45); }
    50% { box-shadow:0 0 0 6px rgba(79,70,229,0); }
  }
  @keyframes ch-tour-in {
    from { opacity:0; transform:translateY(6px); }
    to { opacity:1; transform:none; }
  }
  @media (prefers-reduced-motion: reduce) {
    .ch-tour-head, .ch-dot-now { animation:none; }
  }
</style>
"""


def start() -> None:
    """Jump to step one — the sidebar button and the Home offer both land here."""
    st.session_state[_STEP_KEY] = 0
    st.session_state[_OFFER_KEY] = True  # the invite's job is done either way
    nav_to("home")  # switch_page reruns; falls through only if the registry is gone
    st.rerun()


@st.dialog("👋 Welcome to AI Career Hub")
def _prompt_dialog() -> None:
    st.markdown(
        "**Take the 60-second tour?** It walks every feature in order — resumes, "
        "ATS scoring, cover letters, the Quick Apply agent, and the tracker — on "
        "your real account, with a sample job ready to load."
    )
    go, later = st.columns(2)
    if go.button(
        "🚀 Start the tour", type="primary", use_container_width=True, key="tour_prompt_go"
    ):
        start()
    if later.button("Maybe later", use_container_width=True, key="tour_prompt_later"):
        st.rerun()


def prompt() -> None:
    """Unmissable first-visit invite — a dialog on Home, once per session.

    The flag is set before showing, so the rerun from an ✕-dismiss can't
    re-open it; after any dismissal the slim offer() row stays as the fallback.
    """
    if (
        _STEP_KEY in st.session_state
        or st.session_state.get(_OFFER_KEY)
        or st.session_state.get(_PROMPT_KEY)
    ):
        return
    st.session_state[_PROMPT_KEY] = True
    _prompt_dialog()


def offer() -> None:
    """Slim 'take the tour' invite for Home; gone once started or dismissed."""
    if _STEP_KEY in st.session_state or st.session_state.get(_OFFER_KEY):
        return
    with st.container(border=True):
        text, go, later = st.columns([4, 1.3, 1], vertical_alignment="center")
        text.markdown("🧭 **First time here?** A 60-second tour covers every feature, in order.")
        if go.button("Show me", type="primary", use_container_width=True, key="tour_offer_go"):
            start()
        if later.button("Later", use_container_width=True, key="tour_offer_later"):
            st.session_state[_OFFER_KEY] = True
            st.rerun()


def _resync(idx: int, page: str) -> int | None:
    """Nearest step for `page` (ties go forward); None when the page is off-route."""
    if STEPS[idx]["page"] == page:
        return idx
    matches = [i for i, s in enumerate(STEPS) if s["page"] == page]
    if not matches:
        return None
    return min(matches, key=lambda i: (abs(i - idx), -i))


def _goto(idx: int) -> None:
    st.session_state[_STEP_KEY] = idx
    nav_to(STEPS[idx]["page"])  # same-page switches still rerun, so the rail redraws
    st.rerun()


def _header_html(step: dict, idx: int) -> str:
    """Title row + progress dots; the entrance animation replays on every step."""
    dots = "".join(
        '<span class="ch-dot{}"></span>'.format(
            " ch-dot-done" if i < idx else " ch-dot-now" if i == idx else ""
        )
        for i in range(len(STEPS))
    )
    return (
        f"{_RAIL_CSS}"
        '<div class="ch-tour-head">'
        f'<span class="ch-tour-icon">{step["icon"]}</span>'
        f'<span class="ch-tour-title">{step["title"]}</span>'
        f'<span class="ch-tour-count">step {idx + 1} of {len(STEPS)}</span>'
        "</div>"
        f'<div class="ch-dots">{dots}</div>'
    )


def render(page: str) -> None:
    """Draw the rail for `page` — called once per run from app.py, above the view."""
    if st.session_state.pop(_FINISHED_KEY, False):
        st.balloons()
    idx = st.session_state.get(_STEP_KEY)
    if not isinstance(idx, int):
        return
    synced = _resync(idx, page)
    if synced is None:
        return  # off-route page — keep the step, hide the rail
    idx = st.session_state[_STEP_KEY] = synced

    step = STEPS[idx]
    last = idx == len(STEPS) - 1
    with st.container(border=True):
        st.html(_header_html(step, idx))
        st.markdown(step["body"])
        if step["try"]:
            st.caption(f"💡 {step['try']}")
        if step.get("sample") and st.button(
            "✨ Load the sample job for me", key=f"tour_sample_{idx}"
        ):
            seed_shared_jd(_SAMPLE_JD)
            st.rerun()
        back, nxt, end, _ = st.columns([1, 1, 1, 3])
        if back.button("⬅ Back", key="tour_back", disabled=idx == 0, use_container_width=True):
            _goto(idx - 1)
        label = "Finish ✓" if last else "Next ➡"
        if nxt.button(label, key="tour_next", type="primary", use_container_width=True):
            if last:
                st.session_state[_STEP_KEY] = None
                st.session_state[_FINISHED_KEY] = True
                st.rerun()
            else:
                _goto(idx + 1)
        if not last and end.button("End tour", key="tour_end", use_container_width=True):
            st.session_state[_STEP_KEY] = None
            st.rerun()
