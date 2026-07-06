"""Landing showcase — the animated product story under the sign-in card.

Pure HTML/CSS through st.html (scripts don't survive sanitization anyway): a
staggered entrance on the hero, scroll-driven reveals where the browser
supports `animation-timeline: view()`, and plain static content everywhere
else. Palette mirrors .streamlit/config.toml and ui's tone colors.
"""

from __future__ import annotations

import streamlit as st

_SEEN_KEY = "landing_story_seen"

_CSS = """
<style>
  .ch-show { max-width:1020px; margin:0 auto; padding:.6rem 0 2.4rem; color:#1c1e26; }
  .ch-hero { text-align:center; padding:2.6rem 0 1.2rem; }
  .ch-eyebrow { letter-spacing:.16em; font-size:.76rem; font-weight:700; color:#4f46e5;
    text-transform:uppercase; }
  .ch-h1 { font-size:clamp(2rem, 4.6vw, 3.2rem); font-weight:800; line-height:1.07;
    margin:.45rem 0 .9rem; }
  .ch-grad { background:linear-gradient(92deg, #4f46e5, #9333ea);
    -webkit-background-clip:text; background-clip:text; color:transparent; }
  .ch-sub { max-width:640px; margin:0 auto; color:#5a6472; font-size:1.05rem;
    line-height:1.55; }
  .ch-hero > * { animation:ch-rise .7s ease-out both; }
  .ch-hero > :nth-child(2) { animation-delay:.1s; }
  .ch-hero > :nth-child(3) { animation-delay:.22s; }

  .ch-feat { display:flex; gap:2.4rem; align-items:center; padding:2.1rem 0; }
  .ch-flip { flex-direction:row-reverse; }
  .ch-feat-text { flex:1 1 0; min-width:0; }
  .ch-feat-art { flex:1 1 0; min-width:0; display:flex; justify-content:center; }
  .ch-kicker { letter-spacing:.14em; font-size:.7rem; font-weight:700; color:#4f46e5;
    text-transform:uppercase; }
  .ch-feat-title { font-size:1.45rem; font-weight:800; margin:.35rem 0 .55rem;
    line-height:1.2; }
  .ch-feat-copy { color:#5a6472; line-height:1.6; margin:0; }
  .ch-art-card { background:#fff; border:1px solid #e3e5ee; border-radius:16px;
    padding:1.2rem 1.4rem; box-shadow:0 12px 32px rgba(28,30,38,.08); }

  .ch-chip { display:inline-block; background:#4f46e5; color:#fff; padding:2px 9px;
    border-radius:12px; font-size:.72rem; margin:2px; }
  .ch-chip-good { background:#1e7e34; }
  .ch-chip-warn { background:#8a6308; }
  .ch-chip-ghost { background:#eceef6; color:#3b3f4d; }

  .ch-doc-row { display:flex; align-items:center; gap:1rem; }
  .ch-doc { width:110px; flex:none; background:#fff; border:1px solid #e3e5ee;
    border-radius:10px; padding:.7rem; }
  .ch-doc i { display:block; height:7px; border-radius:4px; background:#e9eaf2;
    margin:.42rem 0; }
  .ch-doc .ch-doc-head { width:55%; background:#cfd3ea; }
  .ch-arrow { color:#8a90a0; font-size:1.2rem; flex:none; }
  .ch-chips { display:flex; flex-wrap:wrap; align-content:center; max-width:230px; }

  .ch-gauge-row { display:flex; align-items:center; gap:1.5rem; }
  .ch-gauge { width:118px; height:118px; border-radius:50%; flex:none;
    background:conic-gradient(#4f46e5 0 82%, #eceef6 0); display:grid;
    place-items:center; }
  .ch-gauge-num { width:90px; height:90px; border-radius:50%; background:#fff;
    display:flex; flex-direction:column; align-items:center; justify-content:center;
    font-weight:800; font-size:1.65rem; }
  .ch-gauge-num small { font-size:.6rem; font-weight:600; color:#8a90a0;
    letter-spacing:.08em; text-transform:uppercase; }
  .ch-weights { flex:1; min-width:170px; }
  .ch-w { display:flex; align-items:center; gap:.5rem; margin:.45rem 0;
    font-size:.74rem; color:#5a6472; }
  .ch-w span { width:64px; flex:none; }
  .ch-w b { color:#1c1e26; }
  .ch-track { flex:1; height:7px; border-radius:4px; background:#eceef6;
    overflow:hidden; }
  .ch-track i { display:block; height:100%; border-radius:4px; background:#4f46e5; }

  .ch-letter { position:relative; width:230px; background:#fff;
    border:1px solid #e3e5ee; border-radius:12px; padding:1.1rem;
    box-shadow:0 12px 32px rgba(28,30,38,.08); }
  .ch-letter i { display:block; height:7px; border-radius:4px; background:#e9eaf2;
    margin:.5rem 0; }
  .ch-stamp { position:absolute; right:-14px; top:-14px; transform:rotate(5deg);
    background:#fff; border:2px solid #1e7e34; color:#1e7e34; font-weight:700;
    font-size:.7rem; padding:.28rem .55rem; border-radius:8px; white-space:nowrap; }

  .ch-gap-cols { display:flex; gap:1.2rem; flex-wrap:wrap; }
  .ch-label { display:block; font-size:.66rem; font-weight:700; letter-spacing:.06em;
    text-transform:uppercase; color:#8a90a0; margin-bottom:.25rem; }
  .ch-qs { margin-top:.9rem; }
  .ch-qs i { display:block; height:7px; border-radius:4px; background:#e9eaf2;
    margin:.45rem 0; }

  .ch-pipe { display:flex; flex-wrap:wrap; align-items:flex-start;
    justify-content:center; gap:2px; }
  .ch-node { display:flex; flex-direction:column; align-items:center; gap:3px;
    width:54px; }
  .ch-node span { width:38px; height:38px; border-radius:50%; background:#fff;
    border:2px solid #e3e5ee; display:grid; place-items:center; font-size:1rem;
    animation:ch-node-glow 5.6s infinite; animation-delay:calc(var(--d) * .8s); }
  .ch-node small { font-size:.6rem; color:#5a6472; }
  .ch-link { width:12px; height:2px; background:#e3e5ee; margin-top:18px; }
  @keyframes ch-node-glow {
    0%, 15%, 100% { border-color:#e3e5ee; box-shadow:none; transform:none; }
    5%, 10% { border-color:#4f46e5; box-shadow:0 0 0 6px rgba(79,70,229,.12);
      transform:translateY(-2px); }
  }

  .ch-board { display:flex; gap:.55rem; flex-wrap:wrap; }
  .ch-col { background:#f4f5f8; border-radius:10px; padding:.5rem .55rem;
    min-width:84px; }
  .ch-col b { display:block; font-size:.64rem; color:#5a6472; white-space:nowrap;
    margin-bottom:.15rem; }
  .ch-col i { display:block; height:24px; background:#fff; border:1px solid #e3e5ee;
    border-radius:6px; margin-top:.3rem; }

  .ch-cta { text-align:center; padding:2rem 0 .2rem; }
  .ch-cta-title { font-size:1.3rem; font-weight:800; }
  .ch-fineprint { color:#8a90a0; font-size:.8rem; margin-top:.6rem; line-height:1.5; }

  @keyframes ch-rise {
    from { opacity:0; transform:translateY(26px); }
    to { opacity:1; transform:none; }
  }
  @supports (animation-timeline: view()) {
    .ch-reveal { animation-name:ch-rise; animation-duration:1ms;
      animation-fill-mode:both; animation-timeline:view();
      animation-range:entry 5% entry 45%; }
  }
  @media (max-width:760px) {
    .ch-feat, .ch-flip { flex-direction:column; gap:1.2rem; }
  }
  @media (prefers-reduced-motion: reduce) {
    .ch-show, .ch-show * { animation:none !important; }
  }
</style>
"""

_ART_RESUME = (
    '<div class="ch-art-card ch-doc-row">'
    '<div class="ch-doc"><i class="ch-doc-head"></i><i></i><i style="width:85%"></i>'
    '<i style="width:70%"></i><i style="width:90%"></i></div>'
    '<div class="ch-arrow">→</div>'
    '<div class="ch-chips">'
    '<span class="ch-chip">Python</span><span class="ch-chip">FastAPI</span>'
    '<span class="ch-chip">PostgreSQL</span><span class="ch-chip">Docker</span>'
    '<span class="ch-chip">AWS</span>'
    '<span class="ch-chip ch-chip-ghost">indexed for retrieval ✓</span>'
    "</div></div>"
)

_ART_ATS = (
    '<div class="ch-art-card ch-gauge-row">'
    '<div class="ch-gauge"><div class="ch-gauge-num">82<small>match</small></div></div>'
    '<div class="ch-weights">'
    '<div class="ch-w"><span>Semantic</span>'
    '<div class="ch-track"><i style="width:100%"></i></div><b>50%</b></div>'
    '<div class="ch-w"><span>Keywords</span>'
    '<div class="ch-track"><i style="width:60%"></i></div><b>30%</b></div>'
    '<div class="ch-w"><span>Structure</span>'
    '<div class="ch-track"><i style="width:40%"></i></div><b>20%</b></div>'
    "</div></div>"
)

_ART_LETTER = (
    '<div class="ch-letter">'
    '<div class="ch-stamp">Honesty 9/10 · Tone 8/10 ✓</div>'
    '<i style="width:40%"></i><i></i><i style="width:92%"></i><i style="width:85%"></i>'
    '<i style="width:60%"></i><i style="width:88%"></i><i style="width:45%"></i>'
    "</div>"
)

_ART_GAP = (
    '<div class="ch-art-card">'
    '<div class="ch-gap-cols">'
    '<div><span class="ch-label">On your resume</span>'
    '<span class="ch-chip ch-chip-good">Python</span>'
    '<span class="ch-chip ch-chip-good">SQL</span>'
    '<span class="ch-chip ch-chip-good">Docker</span></div>'
    '<div><span class="ch-label">Worth adding</span>'
    '<span class="ch-chip ch-chip-warn">Terraform</span>'
    '<span class="ch-chip ch-chip-warn">Kubernetes</span></div>'
    "</div>"
    '<div class="ch-qs"><span class="ch-label">Likely interview questions</span>'
    '<i></i><i style="width:78%"></i><i style="width:64%"></i></div>'
    "</div>"
)

# Mirrors the real seven-step agent pipeline, in order.
_PIPELINE = [
    ("🔗", "scrape"),
    ("🏷️", "extract"),
    ("🔎", "research"),
    ("🎯", "score"),
    ("🧩", "gaps"),
    ("✉️", "letter"),
    ("🎤", "questions"),
]

_ART_BOARD = (
    '<div class="ch-art-card ch-board">'
    '<div class="ch-col"><b>💭 Wishlist</b><i></i><i></i></div>'
    '<div class="ch-col"><b>📤 Applied</b><i></i><i></i><i></i></div>'
    '<div class="ch-col"><b>🎯 Interview</b><i></i></div>'
    '<div class="ch-col"><b>🎉 Offer</b><i></i></div>'
    "</div>"
)


def _art_agent() -> str:
    nodes = []
    for i, (emoji, label) in enumerate(_PIPELINE):
        nodes.append(
            f'<div class="ch-node" style="--d:{i}"><span>{emoji}</span><small>{label}</small></div>'
        )
        if i < len(_PIPELINE) - 1:
            nodes.append('<i class="ch-link"></i>')
    return f'<div class="ch-art-card ch-pipe">{"".join(nodes)}</div>'


_FEATURES = [
    {
        "kicker": "Resumes + retrieval",
        "title": "Your words, structured.",
        "copy": "Uploads are parsed into skills and experience, then embedded into a "
        "per-user vector index. Everything generated later retrieves from your own "
        "resume — grounding, not guesswork.",
        "art": _ART_RESUME,
    },
    {
        "kicker": "ATS scoring",
        "title": "Know the number before they do.",
        "copy": "Every posting gets a hybrid score — 50% semantic similarity, 30% "
        "keywords, 20% structure — with a per-section breakdown, so you fix the "
        "resume before you send it, not after the rejection.",
        "art": _ART_ATS,
    },
    {
        "kicker": "Cover letters",
        "title": "Drafted, then cross-examined.",
        "copy": "One model writes; a second judges honesty and tone against your "
        "actual resume, and low-scoring drafts regenerate before you see them. "
        "Refine with plain-English commands, branch any version, export the PDF.",
        "art": _ART_LETTER,
    },
    {
        "kicker": "Skill gap + interview prep",
        "title": "See the gap. Close it.",
        "copy": "Missing skills ranked by how much the posting cares, each with a "
        "concrete way to close it — plus the interview questions this job "
        "description is likely to produce.",
        "art": _ART_GAP,
    },
    {
        "kicker": "Quick Apply agent",
        "title": "One URL in. Application kit out.",
        "copy": "A seven-step agent scrapes the posting, researches the company, "
        "scores the match, maps the gaps, writes the letter, and preps questions — "
        "with live progress and honest partial results if a step fails.",
        "art": _art_agent(),
    },
    {
        "kicker": "Tracker",
        "title": "The pipeline, not a spreadsheet.",
        "copy": "Wishlist → applied → interview → offer: every application sits at "
        "exactly one stage, generated letters auto-file themselves as wishlist "
        "entries, and Home shows the whole funnel.",
        "art": _ART_BOARD,
    },
]

_HERO = (
    '<div class="ch-hero">'
    '<div class="ch-eyebrow">What&#8217;s inside</div>'
    '<div class="ch-h1">The job hunt,<br><span class="ch-grad">engineered.</span></div>'
    '<p class="ch-sub">Score your resume against any posting, send cover letters that '
    "pass an honesty check, and let a seven-step agent build the whole application "
    "kit from a single job URL.</p>"
    "</div>"
)

_FINEPRINT = (
    '<p class="ch-fineprint">AI-generated content can be wrong — review everything '
    "before you send it. Documents expire after 15 days unless you keep them. "
    "Details in 📜 Legal &amp; Info after you sign in.</p>"
)

_CTA = (
    '<div class="ch-cta ch-reveal">'
    '<div class="ch-cta-title">Ready? Create your free account in the form above ↑</div>'
    f"{_FINEPRINT}</div>"
)

# Inside the overlay the sign-in form is *behind* the story, so the CTA is a
# second close trigger (same checkbox as the ✕ pill).
_CTA_OVERLAY = (
    '<div class="ch-cta">'
    '<label class="ch-cta-close" for="ch-dismiss">Create your free account →</label>'
    f"{_FINEPRINT}</div>"
)

# The overlay closes without JavaScript (st.html strips scripts): a hidden
# checkbox flips display:none on its sibling when either label is clicked.
_OVERLAY_CSS = """
<style>
  .ch-dismiss { display:none; }
  .ch-dismiss:checked + .ch-overlay { display:none; }
  .ch-overlay { position:fixed; inset:0; z-index:999999; background:#ffffff;
    overflow-y:auto; overscroll-behavior:contain; padding:0 1.2rem 2rem;
    animation:ch-fade .45s ease-out both; }
  .ch-overlay .ch-show { padding-top:3.2rem; }
  .ch-close { position:fixed; top:1rem; right:1.2rem; z-index:2; background:#fff;
    border:1px solid #e3e5ee; border-radius:999px; padding:.45rem 1rem;
    font-size:.85rem; font-weight:600; color:#3b3f4d; cursor:pointer;
    box-shadow:0 4px 16px rgba(28,30,38,.08); }
  .ch-close:hover { border-color:#4f46e5; color:#4f46e5; }
  .ch-cta-close { display:inline-block; background:#4f46e5; color:#fff;
    font-weight:700; padding:.7rem 1.5rem; border-radius:999px; cursor:pointer; }
  .ch-cta-close:hover { background:#4338ca; }
  @keyframes ch-fade { from { opacity:0; } to { opacity:1; } }
  @media (prefers-reduced-motion: reduce) { .ch-overlay { animation:none; } }
</style>
"""


def _feature_section(i: int, feat: dict) -> str:
    flip = " ch-flip" if i % 2 else ""
    return (
        f'<section class="ch-feat{flip} ch-reveal">'
        f'<div class="ch-feat-text"><div class="ch-kicker">{feat["kicker"]}</div>'
        f'<div class="ch-feat-title">{feat["title"]}</div>'
        f'<p class="ch-feat-copy">{feat["copy"]}</p></div>'
        f'<div class="ch-feat-art">{feat["art"]}</div>'
        "</section>"
    )


def _story_html(cta: str) -> str:
    sections = "".join(_feature_section(i, f) for i, f in enumerate(_FEATURES))
    return f'<div class="ch-show">{_HERO}{sections}{cta}</div>'


def _page_html() -> str:
    return f"{_CSS}{_story_html(_CTA)}"


def _overlay_html() -> str:
    return (
        f"{_CSS}{_OVERLAY_CSS}"
        '<input class="ch-dismiss" id="ch-dismiss" type="checkbox">'
        '<div class="ch-overlay">'
        '<label class="ch-close" for="ch-dismiss">✕ Skip to sign in</label>'
        f"{_story_html(_CTA_OVERLAY)}"
        "</div>"
    )


def render() -> None:
    """The inline story — auth.py mounts this under the login/register tabs."""
    st.html(_page_html())


def render_overlay() -> None:
    """First arrival only: the story as a full-screen, closeable overlay.

    Closing is client-side CSS, invisible to the server — so the overlay
    renders exactly once per session, and every rerun after that (a failed
    login, a tab dance) falls back to the inline story instead of re-blocking
    the form.
    """
    if st.session_state.get(_SEEN_KEY):
        return
    st.session_state[_SEEN_KEY] = True
    st.html(_overlay_html())
