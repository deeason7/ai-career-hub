"""Job match analysis page — ATS score, skill gap, interview prep."""

import time

import requests
import streamlit as st

from api_client import api, safe_json
from ui import (
    chip_row,
    empty_state,
    error_state,
    job_description_input,
    loading,
    metric_tile,
    nav_to,
    page_header,
    poll_outcome,
    poll_task,
    score_hero,
    score_tone,
    show_error,
)

# The submit normally returns 202 in milliseconds; the generous timeout only
# matters for the degraded inline mode (no task store), where several LLM
# calls ride the one request — sequentially, so their times add up.
_SUBMIT_TIMEOUT_S = 150
# Poll cap — the three steps run one at a time and may wait out a busy model;
# past this the task is treated as stuck even if it might still finish.
_TASK_TIMEOUT_S = 300

# Step keys come from the backend task; render them in pipeline order.
_STEP_LABELS = {"ats": "ATS score", "skill_gap": "Skill gap", "interview": "Interview questions"}
_STEP_ICONS = {"pending": "⬜", "running": "⏳", "done": "✅", "failed": "❌", "waiting": "🕐"}

_OUTCOME_ERRORS = {
    "failed": "Analysis failed on the server. Try again in a minute.",
    "lost": "This analysis is no longer tracked (it may have expired). Run it again.",
    "auth": "Your session expired during the analysis. Log in again, then retry.",
    "timeout": "Still running after 5 minutes — the model may be overloaded. Try again shortly.",
}


def _steps_line(steps: dict) -> str:
    """One caption line of step states, in pipeline order, e.g. '✅ ATS score · ⏳ Skill gap'."""
    parts = []
    for name, label in _STEP_LABELS.items():
        state = steps.get(name, "pending")
        if state == "waiting":
            label = f"{label} (model busy — retrying)"
        parts.append(f"{_STEP_ICONS.get(state, '⬜')} {label}")
    return " · ".join(parts)


def _analysis_status() -> None:
    """One poll tick — runs inside a fragment so only this block re-renders."""
    task = st.session_state.get("jm_task")
    if not task:
        return
    elapsed = time.time() - task["started"]
    http_status, payload = poll_task(f"/analysis/task/{task['task_id']}")
    outcome = poll_outcome(http_status, payload.get("status"), elapsed, _TASK_TIMEOUT_S)

    if outcome == "running":
        st.status(f"🔎 Analyzing your match… {int(elapsed)}s", state="running")
        steps = payload.get("steps") or {}
        if steps:
            st.caption(_steps_line(steps))
        st.caption("Runs in the background — switching pages won't cancel it.")
        return

    # Terminal state: stop polling and hand control back to a full-page run.
    st.session_state.pop("jm_task", None)
    if outcome == "done":
        st.session_state["job_match_result"] = payload.get("result") or {}
    elif outcome == "failed":
        st.session_state["jm_error"] = payload.get("error") or _OUTCOME_ERRORS["failed"]
    else:
        st.session_state["jm_error"] = _OUTCOME_ERRORS[outcome]
    st.rerun(scope="app")


def page_job_match() -> None:
    page_header("🎯", "Job Match")
    st.markdown(
        "One job description → **ATS score**, **skill gap**, and **interview questions** — all at once."
    )

    resumes = safe_json(api("get", "/resumes/"), []) if st.session_state.token else []
    if not isinstance(resumes, list) or not resumes:
        if empty_state(
            "📄",
            "Upload a resume to get started",
            "Job Match scores your resume against a job description — upload one first.",
            cta="Upload a resume",
        ):
            nav_to("resumes")
        return

    resume_options = {r["name"]: r["id"] for r in resumes}
    active = next((r["name"] for r in resumes if r["is_active"]), list(resume_options.keys())[0])
    selected_name = st.selectbox(
        "Resume",
        list(resume_options.keys()),
        index=list(resume_options.keys()).index(active),
    )
    selected_id = resume_options[selected_name]

    jd = job_description_input("job_match", height=260)

    in_flight = bool(st.session_state.get("jm_task"))
    if st.button("🔍 Analyze", type="primary", disabled=in_flight):
        if not jd.strip():
            show_error("Please paste a job description.")
            return
        with loading("Submitting analysis…"):
            try:
                resp = api(
                    "post",
                    "/analysis/job-match",
                    json={"resume_id": selected_id, "job_description": jd},
                    timeout=_SUBMIT_TIMEOUT_S,
                )
            except requests.exceptions.Timeout:
                show_error(
                    f"The submit timed out after {_SUBMIT_TIMEOUT_S}s — the server may be "
                    "cold. Try again in a minute."
                )
                return
            except requests.RequestException:
                error_state("network")
                return

        if resp.status_code == 202:
            task_id = safe_json(resp, {}).get("task_id")
            st.session_state["jm_task"] = {"task_id": task_id, "started": time.time()}
            st.session_state.pop("job_match_result", None)
            st.rerun()
        elif resp.status_code == 200:
            # Degraded inline mode — the backend computed everything in this request.
            st.session_state["job_match_result"] = safe_json(resp, {})
        else:
            error_state(resp)
            return

    if in_flight:
        # Poll inside a fragment: only the status block re-runs every 2s, so the
        # page stays responsive and navigation never cancels the analysis.
        st.fragment(_analysis_status, run_every="2s")()

    jm_error = st.session_state.pop("jm_error", None)
    if jm_error:
        show_error(jm_error)

    # Rendered from state, outside the click branch, so the analysis survives
    # reruns (tweaking the JD or switching resumes no longer wipes it).
    data = st.session_state.get("job_match_result")
    if data:
        _render_analysis(data)


def _render_analysis(data: dict) -> None:
    """Render the combined analysis result in three tabs, plus the next step."""
    ats = data.get("ats", {})
    skill_gap = data.get("skill_gap", {})
    questions = data.get("interview_questions", [])

    tab_ats, tab_gap, tab_interview = st.tabs(["🎯 ATS Score", "🔍 Skill Gap", "🎙️ Interview Prep"])

    with tab_ats:
        score = ats.get("score", 0)
        sem_score = ats.get("semantic_score", 0)
        kw_score = ats.get("keyword_score", 0)
        struct_score = ats.get("structure_score", 0)
        score_hero(
            score,
            [
                {"label": "🧠 Semantic", "value": sem_score, "note": "50% weight"},
                {"label": "🔑 Keywords", "value": kw_score, "note": "30%"},
                {"label": "📐 Structure", "value": struct_score, "note": "20%"},
            ],
            center_label="ATS match",
        )
        st.caption(
            "Semantic = sentence-transformer similarity (catches synonyms) · "
            "Keywords = exact + bigram overlap · Structure = section presence & length."
        )
        if sem_score >= 70:
            st.success("🧠 High semantic alignment — your resume language closely matches the JD.")
        elif sem_score >= 45:
            st.warning(
                "🧠 Moderate semantic alignment — consider mirroring more of the JD's phrasing."
            )
        elif sem_score > 0:
            st.error(
                "🧠 Low semantic alignment — your resume may not address what this role requires."
            )
        section_scores = ats.get("section_scores", {})
        if section_scores:
            st.subheader("📊 Section Alignment with JD")
            sec_cols = st.columns(len(section_scores))
            for col, (sec, sec_score) in zip(sec_cols, section_scores.items(), strict=True):
                with col:
                    metric_tile(
                        sec.title(),
                        f"{sec_score}%" if sec_score > 0 else "—",
                        tone=score_tone(sec_score, good=60, ok=35),
                    )
        st.divider()
        col_l, col_r = st.columns(2)
        with col_l:
            st.subheader("✅ Matched Keywords")
            chip_row(ats.get("matched_keywords", [])[:30], tone="good")
        with col_r:
            st.subheader("❌ Missing Keywords")
            chip_row(ats.get("missing_keywords", [])[:20], tone="bad")
        recs = ats.get("recommendations", [])
        if recs:
            st.subheader("💡 Recommendations")
            for rec in recs:
                st.markdown(f"- {rec}")

    with tab_gap:
        sg_score = skill_gap.get("ats_score", 0)
        metric_tile("ATS Score", f"{sg_score}%", tone=score_tone(sg_score))
        col_l, col_r = st.columns(2)
        with col_l:
            st.subheader("✅ Skills You Have")
            chip_row(skill_gap.get("matched_skills", [])[:15], tone="good")
        with col_r:
            st.subheader("❌ Missing Skills")
            chip_row(skill_gap.get("missing_skills", [])[:15], tone="bad")
        priority_gaps = skill_gap.get("priority_gaps", [])
        if priority_gaps:
            st.subheader("🚨 Priority Gaps")
            st.warning(", ".join(priority_gaps))
        learning = skill_gap.get("learning_recommendations", [])
        if learning:
            st.subheader("📚 Learning Path")
            for rec in learning:
                if isinstance(rec, dict):
                    with st.expander(f"📖 {rec.get('skill', 'Skill')}"):
                        if rec.get("resource"):
                            st.markdown(f"**Resource:** {rec['resource']}")
                        if rec.get("platform"):
                            st.markdown(f"**Platform:** {rec['platform']}")
                        if rec.get("timeline"):
                            st.markdown(f"**Timeline:** {rec['timeline']}")
                else:
                    st.markdown(f"- {rec}")

    with tab_interview:
        if questions:
            st.subheader(f"🎤 {len(questions)} Interview Questions")
            for i, q in enumerate(questions, 1):
                st.markdown(f"**{i}.** {q}")
        else:
            st.info("No interview questions generated. Try again with a more detailed JD.")

    st.divider()
    h1, h2 = st.columns([1, 1])
    with h1:
        if st.button(
            "✉️ Write a cover letter for this JD",
            type="primary",
            use_container_width=True,
        ):
            nav_to("cover_letter")
    with h2:
        st.caption("Your pasted job description carries over automatically.")
