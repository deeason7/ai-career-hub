"""AI Agent page — autonomous multi-step job analysis workflow."""

import streamlit as st

from api_client import api, safe_json


def page_agent() -> None:
    st.title("🤖 AI Agent")
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

        progress_container = st.container()
        with progress_container:
            st.info("⏳ Agent is running... This may take 30-60 seconds.")
            progress_bar = st.progress(0, text="Starting agent...")

        resp = api(
            "post",
            "/agent/analyze",
            json={"job_url": job_url, "resume_id": resume_id},
            timeout=120,
        )

        if resp.status_code != 200:
            st.error(f"Agent failed: {safe_json(resp, {}).get('detail', resp.text)}")
            return

        result = resp.json()
        progress_bar.progress(100, text="Agent completed!")

        _render_results(result)


def _render_results(result: dict) -> None:
    """Render the agent execution results."""
    status = result["status"]
    if status == "completed":
        st.success(f"✅ Agent completed successfully — {len(result['steps'])} steps in {result['total_duration_ms']}ms")
    elif status == "partial":
        st.warning(f"⚠️ Agent completed with {len(result['errors'])} error(s) — {result['total_duration_ms']}ms")
    else:
        st.error(f"❌ Agent failed — {result['total_duration_ms']}ms")

    # Step execution trace
    with st.expander("📊 Execution Trace", expanded=True):
        for step in result["steps"]:
            icon = {"success": "✅", "failed": "❌", "skipped": "⏭️"}.get(step["status"], "❓")
            st.markdown(
                f"{icon} **{step['name']}** — {step['detail']} "
                f"({step['duration_ms']}ms)"
            )

    summary = result.get("summary", {})
    full = result.get("full_results", {})

    # Company & Role
    if summary.get("company") or summary.get("role"):
        st.subheader(f"🏢 {summary.get('role', 'Unknown Role')} @ {summary.get('company', 'Unknown')}")

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
            st.markdown("**Matched:** " + ", ".join(f"`{kw}`" for kw in ats["matched_keywords"][:10]))
        if ats.get("missing_keywords"):
            st.markdown("**Missing:** " + ", ".join(f"`{kw}`" for kw in ats["missing_keywords"][:10]))
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
                        st.markdown(f"- **{rec.get('skill', '')}**: {rec.get('resource', '')} ({rec.get('timeline', '')})")
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
    if result.get("errors"):
        with st.expander("⚠️ Errors"):
            for err in result["errors"]:
                st.error(err)
