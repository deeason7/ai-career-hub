"""AI Agent page — autonomous multi-step job analysis workflow."""

import requests
import streamlit as st

from api_client import api, safe_json
from ui import error_state, page_header

# The pipeline runs as one synchronous call — the backend doesn't expose
# per-step progress — so the wait is shown as honest-indeterminate and the
# real per-step trace renders on completion.
_AGENT_TIMEOUT_S = 120


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

    if st.button("🚀 Run Agent", type="primary", use_container_width=True, disabled=not job_url):
        if not job_url or not selected_resume:
            st.error("Please provide a job URL and select a resume.")
            return

        resume_id = resume_options[selected_resume]

        with st.status("🤖 Agent running — scrape, research, score, write…", expanded=True) as box:
            st.caption(
                "Seven steps run as one pipeline call, typically 30–90 seconds. "
                "The real per-step trace appears when it finishes."
            )
            try:
                resp = api(
                    "post",
                    "/agent/analyze",
                    json={"job_url": job_url, "resume_id": resume_id},
                    timeout=_AGENT_TIMEOUT_S,
                )
            except requests.exceptions.Timeout:
                box.update(label="⏱️ No result after 2 minutes", state="error")
                st.error(
                    "The agent didn't finish in time — the job site may be slow or the "
                    "model cold. Try again in a minute."
                )
                return
            except requests.RequestException:
                box.update(label="🌐 Request failed", state="error")
                error_state("network")
                return

            if resp.status_code != 200:
                box.update(label="❌ Agent failed", state="error")
                error_state(resp)
                return

            result = safe_json(resp, {})
            if not result.get("status"):
                box.update(label="❌ Unexpected response", state="error")
                st.error("The agent returned an unreadable result. Try again.")
                return

            box.update(label="✅ Agent finished", state="complete")
            st.session_state["agent_result"] = result

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
        col1.metric("Overall", f"{score}/100")
        col2.metric("Semantic", f"{ats.get('semantic_score', 0)}/100")
        col3.metric("Keywords", f"{ats.get('keyword_score', 0)}/100")

        if ats.get("matched_keywords"):
            st.markdown(
                "**Matched:** " + ", ".join(f"`{kw}`" for kw in ats["matched_keywords"][:10])
            )
        if ats.get("missing_keywords"):
            st.markdown(
                "**Missing:** " + ", ".join(f"`{kw}`" for kw in ats["missing_keywords"][:10])
            )
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
                            f"- **{rec.get('skill', '')}**: {rec.get('resource', '')} ({rec.get('timeline', '')})"
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
