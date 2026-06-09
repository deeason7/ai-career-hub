"""Job match analysis page — ATS score, skill gap, interview prep."""

import html

import requests
import streamlit as st

from api_client import api, safe_json
from components import job_description_input, show_error
from ui import error_state, page_header

# ATS + skill gap + interview questions ride one request through several LLM
# calls; the 30s client default read-timed-out in prod when the model was cold.
_ANALYZE_TIMEOUT_S = 90


def page_job_match() -> None:
    page_header("🎯", "Job Match")
    st.markdown(
        "One job description → **ATS score**, **skill gap**, and **interview questions** — all at once."
    )

    resumes = safe_json(api("get", "/resumes/"), []) if st.session_state.token else []
    if not isinstance(resumes, list) or not resumes:
        st.warning("⚠️ Upload a resume first in **My Resumes**.")
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

    if st.button("🔍 Analyze", type="primary"):
        if not jd.strip():
            show_error("Please paste a job description.")
            return
        with st.spinner(
            "Analyzing — ATS score, skill gap, interview prep. Usually under a minute…"
        ):
            try:
                resp = api(
                    "post",
                    "/analysis/job-match",
                    json={"resume_id": selected_id, "job_description": jd},
                    timeout=_ANALYZE_TIMEOUT_S,
                )
            except requests.exceptions.Timeout:
                show_error(
                    f"Analysis timed out after {_ANALYZE_TIMEOUT_S}s — the model may be "
                    "cold. Try again in a minute."
                )
                return
            except requests.RequestException:
                error_state("network")
                return

        if resp.status_code != 200:
            error_state(resp)
            return

        st.session_state["job_match_result"] = safe_json(resp, {})

    # Rendered from state, outside the click branch, so the analysis survives
    # reruns (tweaking the JD or switching resumes no longer wipes it).
    data = st.session_state.get("job_match_result")
    if data:
        _render_analysis(data)


def _render_analysis(data: dict) -> None:
    """Render the combined analysis result in three tabs."""
    ats = data.get("ats", {})
    skill_gap = data.get("skill_gap", {})
    questions = data.get("interview_questions", [])

    tab_ats, tab_gap, tab_interview = st.tabs(["🎯 ATS Score", "🔍 Skill Gap", "🎙️ Interview Prep"])

    with tab_ats:
        score = ats.get("score", 0)
        sem_score = ats.get("semantic_score", 0)
        kw_score = ats.get("keyword_score", 0)
        struct_score = ats.get("structure_score", 0)
        color = "🟢" if score >= 70 else "🟡" if score >= 45 else "🔴"
        c1, c2, c3, c4 = st.columns(4)
        c1.metric(
            f"{color} ATS Score",
            f"{score}%",
            help="Composite: 50% semantic + 30% keyword + 20% structure",
        )
        c2.metric(
            "🧠 Semantic Match",
            f"{sem_score}%",
            help="Sentence-transformer cosine similarity — catches synonyms",
        )
        c3.metric("🔑 Keywords", f"{kw_score}%", help="Exact + bigram keyword overlap")
        c4.metric(
            "📐 Structure",
            f"{struct_score}%",
            help="Section presence and resume length",
        )
        st.progress(int(score) / 100)
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
                sec_color = "🟢" if sec_score >= 60 else "🟡" if sec_score >= 35 else "🔴"
                col.metric(
                    f"{sec_color} {sec.title()}",
                    f"{sec_score}%" if sec_score > 0 else "—",
                )
        st.divider()
        col_l, col_r = st.columns(2)
        with col_l:
            st.subheader("✅ Matched Keywords")
            matched = ats.get("matched_keywords", [])
            if matched:
                st.markdown(
                    " ".join(
                        f'<span style="background:#1e7e34;color:#fff;padding:2px 8px;'
                        f'border-radius:12px;font-size:0.82em;margin:2px;display:inline-block">'
                        f"{html.escape(str(kw))}</span>"
                        for kw in matched[:30]
                    ),
                    unsafe_allow_html=True,
                )
            else:
                st.write("None")
        with col_r:
            st.subheader("❌ Missing Keywords")
            missing = ats.get("missing_keywords", [])
            if missing:
                st.markdown(
                    " ".join(
                        f'<span style="background:#b02a37;color:#fff;padding:2px 8px;'
                        f'border-radius:12px;font-size:0.82em;margin:2px;display:inline-block">'
                        f"{html.escape(str(kw))}</span>"
                        for kw in missing[:20]
                    ),
                    unsafe_allow_html=True,
                )
            else:
                st.write("None")
        recs = ats.get("recommendations", [])
        if recs:
            st.subheader("💡 Recommendations")
            for rec in recs:
                st.markdown(f"- {rec}")

    with tab_gap:
        sg_score = skill_gap.get("ats_score", 0)
        sg_color = "🟢" if sg_score >= 70 else "🟡" if sg_score >= 45 else "🔴"
        st.metric(f"{sg_color} ATS Score", f"{sg_score}%")
        col_l, col_r = st.columns(2)
        with col_l:
            st.subheader("✅ Skills You Have")
            for s in skill_gap.get("matched_skills", [])[:15]:
                st.markdown(f"- `{s}`")
        with col_r:
            st.subheader("❌ Missing Skills")
            for s in skill_gap.get("missing_skills", [])[:15]:
                st.markdown(f"- `{s}`")
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
