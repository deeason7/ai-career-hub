"""Job match analysis page — ATS score, skill gap, interview prep."""

import streamlit as st

from api_client import api, detail, safe_json
from components import show_error


def _job_url_import_jm(key_prefix: str) -> str:
    fetched_jd = ""
    with st.expander("🔗 Import Job from URL (LinkedIn, Greenhouse, Lever…)"):
        st.caption(
            "Paste any public job posting URL. LinkedIn may require login — "
            "in that case paste the text manually."
        )
        job_url_input = st.text_input(
            "Job Posting URL",
            placeholder="https://www.linkedin.com/jobs/view/...",
            key=f"{key_prefix}_url_input",
        )
        if st.button("🚀 Fetch Job Description", key=f"{key_prefix}_fetch_btn"):
            if not job_url_input.strip():
                show_error("Please enter a URL.")
            else:
                with st.spinner("Fetching job description…"):
                    resp = api("post", "/ai/fetch-job", json={"url": job_url_input.strip()})
                data = safe_json(resp, {})
                if resp.status_code == 200 and data.get("success"):
                    fetched_jd = data.get("job_description", "")
                    st.session_state[f"{key_prefix}_prefilled_jd"] = fetched_jd
                    st.success("Job description fetched! Scroll down — it's pre-filled below.")
                    if data.get("warning"):
                        st.warning(data["warning"])
                else:
                    show_error(detail(resp, "Could not fetch job description."))
    return st.session_state.get(f"{key_prefix}_prefilled_jd", "")


def page_job_match() -> None:
    st.title("🎯 Job Match Analysis")
    st.markdown(
        "One job description → **ATS score**, **skill gap**, and **interview questions** — all at once."
    )

    resumes = safe_json(api("get", "/resumes/"), []) if st.session_state.token else []
    if not isinstance(resumes, list) or not resumes:
        st.warning("⚠️ Upload a resume first in **My Resumes**.")
        return

    resume_options = {r["name"]: r["id"] for r in resumes}
    active = next(
        (r["name"] for r in resumes if r["is_active"]), list(resume_options.keys())[0]
    )
    selected_name = st.selectbox(
        "Resume", list(resume_options.keys()),
        index=list(resume_options.keys()).index(active),
    )
    selected_id = resume_options[selected_name]

    prefilled_jd = _job_url_import_jm("job_match")
    jd = st.text_area(
        "Job Description", value=prefilled_jd, height=260,
        placeholder="Paste the full job posting here, or import from URL above.",
    )

    if st.button("🔍 Analyze", type="primary"):
        if not jd.strip():
            show_error("Please paste a job description.")
            return
        with st.spinner("Running ATS scoring, skill gap analysis, and interview prep in parallel…"):
            resp = api("post", "/analysis/job-match", json={"resume_id": selected_id, "job_description": jd})

        if resp.status_code == 429:
            show_error("Too many requests. Please wait 1 minute and try again.")
            return
        if resp.status_code == 502:
            show_error("AI service temporarily unavailable. Please try again.")
            return
        if resp.status_code != 200:
            show_error(detail(resp, f"Analysis failed (HTTP {resp.status_code})."))
            return

        data = safe_json(resp, {})
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
            c1.metric(f"{color} ATS Score", f"{score}%", help="Composite: 50% semantic + 30% keyword + 20% structure")
            c2.metric("🧠 Semantic Match", f"{sem_score}%", help="Sentence-transformer cosine similarity — catches synonyms")
            c3.metric("🔑 Keywords", f"{kw_score}%", help="Exact + bigram keyword overlap")
            c4.metric("📐 Structure", f"{struct_score}%", help="Section presence and resume length")
            st.progress(int(score) / 100)
            if sem_score >= 70:
                st.success("🧠 High semantic alignment — your resume language closely matches the JD.")
            elif sem_score >= 45:
                st.warning("🧠 Moderate semantic alignment — consider mirroring more of the JD's phrasing.")
            elif sem_score > 0:
                st.error("🧠 Low semantic alignment — your resume may not address what this role requires.")
            section_scores = ats.get("section_scores", {})
            if section_scores:
                st.subheader("📊 Section Alignment with JD")
                sec_cols = st.columns(len(section_scores))
                for col, (sec, sec_score) in zip(sec_cols, section_scores.items()):
                    sec_color = "🟢" if sec_score >= 60 else "🟡" if sec_score >= 35 else "🔴"
                    col.metric(f"{sec_color} {sec.title()}", f"{sec_score}%" if sec_score > 0 else "—")
            st.divider()
            col_l, col_r = st.columns(2)
            with col_l:
                st.subheader("✅ Matched Keywords")
                matched = ats.get("matched_keywords", [])
                if matched:
                    st.markdown(
                        " ".join(
                            f'<span style="background:#1e7e34;color:#fff;padding:2px 8px;border-radius:12px;font-size:0.82em;margin:2px;display:inline-block">{kw}</span>'
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
                            f'<span style="background:#b02a37;color:#fff;padding:2px 8px;border-radius:12px;font-size:0.82em;margin:2px;display:inline-block">{kw}</span>'
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
