"""AI Agent page — autonomous multi-step job analysis workflow."""

import time

import requests
import streamlit as st

from api_client import api, safe_json
from ui import (
    chip_row,
    error_state,
    loading,
    metric_tile,
    nav_to,
    page_header,
    poll_outcome,
    poll_task,
    score_tone,
)

# The submit normally returns 202 in milliseconds; the generous timeout only
# matters for the degraded inline mode (no task store), where the whole
# pipeline rides the one request.
_SUBMIT_TIMEOUT_S = 120
# Poll cap — seven steps usually finish in 30–90s, but a busy model adds
# backoff waits; past this the run is treated as stuck even if it might
# still finish server-side.
_RUN_TIMEOUT_S = 360

# Pipeline checklist, in execution order, keyed by the backend step names.
_STEP_LABELS = {
    "scrape_job": "Scrape the job posting",
    "extract_metadata": "Extract role & company",
    "search_company": "Research the company",
    "score_ats": "Score your ATS match",
    "analyze_gaps": "Analyze skill gaps",
    "write_cover_letter": "Draft a cover letter",
    "generate_questions": "Prepare interview questions",
}
_STEP_ICONS = {
    "success": "✅",
    "failed": "❌",
    "skipped": "⏭️",
    "running": "⏳",
    "pending": "⬜",
}

_OUTCOME_ERRORS = {
    "failed": "The agent run failed on the server. Try again in a minute.",
    "lost": "This run is no longer tracked (it may have expired). Run it again.",
    "auth": "Your session expired during the run. Log in again, then retry.",
    "timeout": "Still running after 6 minutes — the job site or model may be slow. Try again.",
}


def _agent_checklist(steps: dict, running: bool) -> list[str]:
    """Checklist lines in pipeline order; the first pending step shows as running."""
    lines = []
    current_marked = False
    for name, label in _STEP_LABELS.items():
        state = steps.get(name, "pending")
        if state == "pending" and running and not current_marked:
            state = "running"
            current_marked = True
        lines.append(f"{_STEP_ICONS.get(state, '⬜')} {label}")
    return lines


def _agent_status() -> None:
    """One poll tick — runs inside a fragment so only this block re-renders."""
    task = st.session_state.get("agent_task")
    if not task:
        return
    elapsed = time.time() - task["started"]
    http_status, payload = poll_task(f"/agent/task/{task['task_id']}")
    outcome = poll_outcome(http_status, payload.get("status"), elapsed, _RUN_TIMEOUT_S)

    if outcome == "running":
        with st.status(f"🤖 Agent working… {int(elapsed)}s", state="running", expanded=True):
            for line in _agent_checklist(payload.get("steps") or {}, running=True):
                st.markdown(line)
        st.caption("Runs in the background — switching pages won't cancel it.")
        return

    # Terminal state: stop polling and hand control back to a full-page run.
    st.session_state.pop("agent_task", None)
    if outcome == "done":
        st.session_state["agent_result"] = payload.get("result") or {}
    elif outcome == "failed":
        st.session_state["agent_error"] = payload.get("error") or _OUTCOME_ERRORS["failed"]
    else:
        st.session_state["agent_error"] = _OUTCOME_ERRORS[outcome]
    st.rerun(scope="app")


def page_agent() -> None:
    page_header("✨", "Quick Apply")
    st.caption(
        "Paste a job URL and select your resume. The agent autonomously scrapes, "
        "analyzes, scores, and generates everything you need to apply."
    )

    if not st.session_state.get("token"):
        st.warning("Please log in to use the AI Agent.")
        return

    resumes = safe_json(api("get", "/resumes/"), [])
    if not resumes:
        st.info("Upload a resume first to use the agent.")
        return

    resume_options = {f"{r['original_filename']}": r["id"] for r in resumes}

    col1, col2 = st.columns([3, 1])
    with col1:
        job_url = st.text_input(
            "Job Posting URL",
            placeholder="https://linkedin.com/jobs/view/...",
            help="Paste any job listing URL — the agent will scrape it automatically.",
        )
    with col2:
        selected_resume = st.selectbox("Resume", options=list(resume_options.keys()))

    in_flight = bool(st.session_state.get("agent_task"))
    if st.button(
        "🚀 Run Agent",
        type="primary",
        use_container_width=True,
        disabled=not job_url or in_flight,
    ):
        if not job_url or not selected_resume:
            st.error("Please provide a job URL and select a resume.")
            return

        resume_id = resume_options[selected_resume]
        with loading("Starting the agent…"):
            try:
                resp = api(
                    "post",
                    "/agent/analyze",
                    json={"job_url": job_url, "resume_id": resume_id},
                    timeout=_SUBMIT_TIMEOUT_S,
                )
            except requests.exceptions.Timeout:
                st.error(
                    "The agent didn't start in time — the server may be cold. "
                    "Try again in a minute."
                )
                return
            except requests.RequestException:
                error_state("network")
                return

        if resp.status_code == 202:
            task_id = safe_json(resp, {}).get("task_id")
            st.session_state["agent_task"] = {"task_id": task_id, "started": time.time()}
            st.session_state.pop("agent_result", None)
            st.rerun()
        elif resp.status_code == 200:
            # Degraded inline mode — the whole pipeline ran in this request.
            result = safe_json(resp, {})
            if result.get("status"):
                st.session_state["agent_result"] = result
            else:
                st.error("The agent returned an unreadable result. Try again.")
                return
        else:
            error_state(resp)
            return

    if in_flight:
        # Poll inside a fragment: only the checklist re-runs every 2s, so the
        # page stays responsive and navigation never cancels the run.
        st.fragment(_agent_status, run_every="2s")()

    agent_error = st.session_state.pop("agent_error", None)
    if agent_error:
        st.error(agent_error)

    # Rendered from state, outside the click branch, so the report survives
    # reruns (editing the URL or switching resumes no longer wipes it).
    result = st.session_state.get("agent_result")
    if result:
        _render_results(result)


def _render_results(result: dict) -> None:
    """Render the agent execution results."""
    status = result.get("status", "failed")
    steps = result.get("steps", [])
    duration = result.get("total_duration_ms", 0)
    errors = result.get("errors", [])
    if status == "completed":
        st.success(f"✅ Agent completed successfully — {len(steps)} steps in {duration}ms")
    elif status == "partial":
        st.warning(f"⚠️ Agent completed with {len(errors)} error(s) — {duration}ms")
    else:
        st.error(f"❌ Agent failed — {duration}ms")

    # Step execution trace
    with st.expander("📊 Execution Trace", expanded=True):
        for step in steps:
            icon = {"success": "✅", "failed": "❌", "skipped": "⏭️"}.get(step["status"], "❓")
            st.markdown(f"{icon} **{step['name']}** — {step['detail']} ({step['duration_ms']}ms)")

    summary = result.get("summary", {})
    full = result.get("full_results", {})

    # Company & Role
    if summary.get("company") or summary.get("role"):
        st.subheader(
            f"🏢 {summary.get('role', 'Unknown Role')} @ {summary.get('company', 'Unknown')}"
        )

    # Company research
    if full.get("company_research"):
        with st.expander("🔍 Company Research"):
            st.markdown(full["company_research"])

    # ATS Score
    ats = full.get("ats_result")
    if ats:
        st.subheader("📊 ATS Score")
        score = ats.get("score", 0)
        col1, col2, col3 = st.columns(3)
        with col1:
            metric_tile("Overall", f"{score}/100", tone=score_tone(score))
        with col2:
            metric_tile("Semantic", f"{ats.get('semantic_score', 0)}/100")
        with col3:
            metric_tile("Keywords", f"{ats.get('keyword_score', 0)}/100")

        if ats.get("matched_keywords"):
            st.markdown("**Matched:**")
            chip_row([str(kw) for kw in ats["matched_keywords"][:10]], tone="good")
        if ats.get("missing_keywords"):
            st.markdown("**Missing:**")
            chip_row([str(kw) for kw in ats["missing_keywords"][:10]], tone="bad")
        if ats.get("recommendations"):
            for rec in ats["recommendations"]:
                st.markdown(f"- {rec}")

    # Skill Gaps
    gaps = full.get("skill_gap")
    if gaps and gaps.get("priority_gaps"):
        with st.expander("🎯 Skill Gaps & Learning Paths"):
            for gap in gaps["priority_gaps"]:
                st.markdown(f"- **{gap}**")
            recs = gaps.get("learning_recommendations", [])
            if recs:
                st.markdown("**Recommended Learning:**")
                for rec in recs:
                    if isinstance(rec, dict):
                        st.markdown(
                            f"- **{rec.get('skill', '')}**: {rec.get('resource', '')} "
                            f"on {rec.get('platform', '')} ({rec.get('timeline', '')})"
                        )
                    else:
                        st.markdown(f"- {rec}")

    # Cover Letter
    cl = full.get("cover_letter")
    if cl and cl.get("cover_letter"):
        with st.expander("✉️ Generated Cover Letter", expanded=True):
            st.text_area("Cover Letter", cl["cover_letter"], height=300, disabled=True)

    # Interview Questions
    questions = full.get("interview_questions")
    if questions:
        with st.expander("🎤 Interview Questions"):
            for i, q in enumerate(questions, 1):
                st.markdown(f"**{i}.** {q}")

    # Errors
    if errors:
        with st.expander("⚠️ Errors"):
            for err in errors:
                st.error(err)

    st.divider()
    if st.button("📊 Open your tracker", use_container_width=True):
        nav_to("tracker")
