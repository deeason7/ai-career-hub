"""
AI Career Hub — Streamlit Frontend
Full-featured multi-section app with:
  - Auth (register/login)
  - Multi-Resume Management
  - AI Cover Letter Generator (async polling)
  - ATS Scorer
  - Skill Gap Analysis
  - Interview Question Generator
  - Job Application Tracker
"""
import time
import io
import json
import requests
import streamlit as st

import os

# ─── Config ───────────────────────────────────────────────────────────────────
API_URL = os.environ.get("API_URL", "http://api:8000/api/v1")

st.set_page_config(
    page_title="AI Career Hub",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Session State Init ───────────────────────────────────────────────────────
for key in ["token", "user"]:
    if key not in st.session_state:
        st.session_state[key] = None


# ─── Helpers ──────────────────────────────────────────────────────────────────

def api(method: str, path: str, **kwargs) -> requests.Response:
    headers = kwargs.pop("headers", {})
    if st.session_state.token:
        headers["Authorization"] = f"Bearer {st.session_state.token}"
    return getattr(requests, method)(f"{API_URL}{path}", headers=headers, **kwargs)


def extract_text(uploaded_file) -> str:
    if uploaded_file.name.endswith(".pdf"):
        import PyPDF2
        reader = PyPDF2.PdfReader(uploaded_file)
        return "\n".join(p.extract_text() for p in reader.pages if p.extract_text())
    elif uploaded_file.name.endswith(".docx"):
        import docx
        doc = docx.Document(uploaded_file)
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    return uploaded_file.getvalue().decode("utf-8")


def show_error(msg: str):
    st.error(f"❌ {msg}")


def show_success(msg: str):
    st.success(f"✅ {msg}")


# ─── AUTH PAGES ───────────────────────────────────────────────────────────────

def page_auth():
    st.title("🚀 AI Career Hub")
    st.markdown(
        "An AI-powered platform for job seekers — multi-resume management, "
        "RAG cover letters, ATS scoring, and more."
    )
    tab_login, tab_register = st.tabs(["🔐 Login", "📝 Register"])

    with tab_login:
        with st.form("login_form"):
            email = st.text_input("Email")
            password = st.text_input("Password", type="password")
            if st.form_submit_button("Login", type="primary"):
                resp = requests.post(f"{API_URL}/auth/login", data={"username": email, "password": password})
                if resp.status_code == 200:
                    st.session_state.token = resp.json()["access_token"]
                    me = api("get", "/auth/me").json()
                    st.session_state.user = me
                    show_success("Logged in!")
                    st.rerun()
                else:
                    show_error(resp.json().get("detail", "Login failed."))

    with tab_register:
        with st.form("register_form"):
            name = st.text_input("Full Name")
            r_email = st.text_input("Email")
            r_password = st.text_input("Password", type="password")
            if st.form_submit_button("Create Account", type="primary"):
                resp = requests.post(f"{API_URL}/auth/register", json={
                    "email": r_email, "full_name": name, "password": r_password
                })
                if resp.status_code == 201:
                    show_success("Account created! Please log in.")
                else:
                    show_error(resp.json().get("detail", "Registration failed."))


# ─── SIDEBAR & NAVIGATION ─────────────────────────────────────────────────────

def sidebar():
    with st.sidebar:
        st.title("🚀 AI Career Hub")
        user = st.session_state.user or {}
        st.markdown(f"👤 **{user.get('full_name', 'User')}**  \n`{user.get('email', '')}`")
        st.divider()

        page = st.radio(
            "Navigation",
            [
                "📋 Dashboard",
                "📄 My Resumes",
                "✉️ Cover Letter",
                "🎯 ATS Score",
                "🔍 Skill Gap",
                "🎙️ Interview Questions",
                "📊 Job Tracker",
            ],
            label_visibility="collapsed",
        )
        st.divider()
        if st.button("🚪 Logout"):
            st.session_state.token = None
            st.session_state.user = None
            st.rerun()
    return page


# ─── PAGE: DASHBOARD ──────────────────────────────────────────────────────────

def page_dashboard():
    st.title("📋 Dashboard")

    # Resume count
    resumes = api("get", "/resumes/").json() if st.session_state.token else []
    jobs = api("get", "/jobs/stats").json() if st.session_state.token else {}
    cover_letters = api("get", "/cover-letters/").json() if st.session_state.token else []

    col1, col2, col3 = st.columns(3)
    col1.metric("📄 Resumes", len(resumes) if isinstance(resumes, list) else 0)
    col2.metric("✉️ Cover Letters", len(cover_letters) if isinstance(cover_letters, list) else 0)
    col3.metric("📊 Applications", jobs.get("total", 0) if isinstance(jobs, dict) else 0)

    st.divider()
    st.subheader("Application Pipeline")
    if isinstance(jobs, dict) and "by_status" in jobs:
        statuses = jobs["by_status"]
        cols = st.columns(len(statuses))
        status_emojis = {
            "wishlist": "⭐", "applied": "📨", "phone_screen": "📞",
            "interview": "🎤", "offer": "🎉", "rejected": "❌", "accepted": "✅"
        }
        for col, (s, count) in zip(cols, statuses.items()):
            col.metric(f"{status_emojis.get(s, '')} {s.replace('_', ' ').title()}", count)

    st.divider()
    st.subheader("🚀 Quick Actions")
    q1, q2, q3 = st.columns(3)
    q1.info("Upload a resume → **My Resumes**")
    q2.info("Generate a cover letter → **Cover Letter**")
    q3.info("Score your resume → **ATS Score**")


# ─── PAGE: RESUMES ────────────────────────────────────────────────────────────

def page_resumes():
    st.title("📄 My Resumes")
    st.markdown("Upload up to **10 resumes**. Activate the one to use for AI features.")

    # Upload
    with st.expander("➕ Upload a New Resume", expanded=True):
        with st.form("upload_form"):
            label = st.text_input("Resume Label (e.g. 'ML Engineer Resume')", placeholder="ML Engineer 2026")
            file = st.file_uploader("File (PDF, DOCX, TXT)", type=["pdf", "docx", "txt"])
            if st.form_submit_button("Upload & Parse", type="primary"):
                if not label.strip():
                    show_error("Please provide a label.")
                elif not file:
                    show_error("Please select a file.")
                else:
                    with st.spinner("🔍 Extracting text and parsing resume with AI..."):
                        resp = api("post", "/resumes/upload",
                                  data={"name": label},
                                  files={"file": (file.name, file.getvalue(), file.type)})
                    if resp.status_code == 201:
                        show_success(f"Resume '{label}' uploaded and parsed!")
                        st.rerun()
                    else:
                        show_error(resp.json().get("detail", "Upload failed."))

    # List
    resumes_resp = api("get", "/resumes/")
    if resumes_resp.status_code != 200:
        show_error("Could not fetch resumes.")
        return

    resumes = resumes_resp.json()
    if not resumes:
        st.info("No resumes yet. Upload one above!")
        return

    st.subheader(f"Your Resumes ({len(resumes)})")
    for r in resumes:
        badge = "🟢 **ACTIVE**" if r["is_active"] else "⚪ inactive"
        with st.expander(f"{badge} — {r['name']}  |  `{r['original_filename']}`"):
            col1, col2, col3 = st.columns(3)

            if not r["is_active"]:
                if col1.button("✅ Set as Active", key=f"activate_{r['id']}"):
                    api("put", f"/resumes/{r['id']}/activate")
                    show_success(f"'{r['name']}' is now your active resume.")
                    st.rerun()

            if col2.button("🔍 View Analysis", key=f"analysis_{r['id']}"):
                analysis_resp = api("get", f"/resumes/{r['id']}/analysis")
                if analysis_resp.status_code == 200:
                    st.json(analysis_resp.json())
                else:
                    show_error("No analysis available.")

            if col3.button("🗑️ Delete", key=f"delete_{r['id']}"):
                api("delete", f"/resumes/{r['id']}")
                show_success("Deleted.")
                st.rerun()


# ─── PAGE: COVER LETTER ───────────────────────────────────────────────────────

def page_cover_letter():
    st.title("✉️ AI Cover Letter Generator")
    st.markdown("Generates a **zero-hallucination** cover letter using RAG — only facts from YOUR resume.")

    # Resume selector
    resumes = api("get", "/resumes/").json() if st.session_state.token else []
    if not isinstance(resumes, list) or not resumes:
        st.warning("⚠️ Upload a resume first in **My Resumes**.")
        return

    resume_options = {r["name"]: r["id"] for r in resumes}
    active = next((r["name"] for r in resumes if r["is_active"]), list(resume_options.keys())[0])
    selected_name = st.selectbox("Choose Resume", list(resume_options.keys()), index=list(resume_options.keys()).index(active))
    selected_id = resume_options[selected_name]

    jd = st.text_area("Paste the Job Description", height=300, placeholder="Paste the full job posting here...")

    if st.button("🚀 Generate Cover Letter", type="primary"):
        if not jd.strip():
            show_error("Please paste the job description.")
            return

        with st.spinner("Dispatching AI task..."):
            resp = api("post", "/cover-letters/generate", json={
                "job_description": jd,
                "resume_id": selected_id,
            })

        if resp.status_code != 202:
            show_error(resp.json().get("detail", "Failed to start task.") if resp.content else "Failed to start task (empty response).")
            return

        cl = resp.json()
        task_id = cl.get("task_id")
        cl_id = cl.get("id")
        st.info(f"Task started. ID: `{task_id}`")

        progress = st.progress(0, text="Generating cover letter...")
        status_box = st.empty()
        ticks = 0
        while True:
            time.sleep(2)
            ticks += 1
            poll = api("get", f"/cover-letters/task/{task_id}").json()
            status = poll.get("status", "PENDING")
            progress.progress(min(ticks * 5, 90), text=f"Status: {status}")
            status_box.markdown(f"**Status:** `{status}`")

            if status == "SUCCESS":
                progress.progress(100, text="Done!")
                # Fetch updated record from DB
                detail = api("get", f"/cover-letters/{cl_id}").json()
                cover_text = detail.get("generated_text", "")
                show_success("Cover letter generated!")
                st.text_area("📝 Your Cover Letter", cover_text, height=450)
                st.download_button("⬇️ Download as TXT", cover_text, file_name="cover_letter.txt")
                break
            elif status == "FAILURE":
                show_error("Task failed. Check the backend worker logs.")
                break
            elif ticks > 60:
                show_error("Timed out after 2 minutes. Check if the Celery worker is running.")
                break

    # History
    st.divider()
    st.subheader("📜 Past Cover Letters")
    history = api("get", "/cover-letters/").json()
    if isinstance(history, list) and history:
        for cl in history[:5]:
            with st.expander(f"Cover Letter — {cl['created_at'][:10]} | Status: `{cl['status']}`"):
                if cl.get("generated_text"):
                    st.text_area("", cl["generated_text"], height=250, key=f"hist_{cl['id']}")
    else:
        st.info("No cover letters generated yet.")


# ─── PAGE: ATS SCORE ──────────────────────────────────────────────────────────

def page_ats_score():
    st.title("🎯 ATS Score Analyzer")
    st.markdown("Scores your resume against any job description in **< 1 second** — instant algorithmic analysis.")

    resumes = api("get", "/resumes/").json() if st.session_state.token else []
    if not isinstance(resumes, list) or not resumes:
        st.warning("Upload a resume first.")
        return

    resume_options = {r["name"]: r["id"] for r in resumes}
    active = next((r["name"] for r in resumes if r["is_active"]), list(resume_options.keys())[0])
    selected_name = st.selectbox("Resume", list(resume_options.keys()), index=list(resume_options.keys()).index(active))
    selected_id = resume_options[selected_name]

    jd = st.text_area("Job Description", height=250)

    if st.button("🎯 Score My Resume", type="primary"):
        if not jd.strip():
            show_error("Please paste a job description.")
            return
        with st.spinner("Scoring..."):
            resp = api("post", "/ai/ats-score", json={"job_description": jd, "resume_id": selected_id})

        if resp.status_code != 200:
            show_error(resp.json().get("detail", "Scoring failed."))
            return

        data = resp.json()
        score = data["score"]

        col1, col2, col3 = st.columns(3)
        color = "🟢" if score >= 70 else "🟡" if score >= 45 else "🔴"
        col1.metric(f"{color} ATS Score", f"{score}%")
        col2.metric("🔑 Keyword Score", f"{data['keyword_score']}%")
        col3.metric("📐 Structure Score", f"{data['structure_score']}%")

        st.progress(int(score) / 100)

        col_l, col_r = st.columns(2)
        with col_l:
            st.subheader("✅ Matched Keywords")
            st.write(", ".join(data["matched_keywords"]) or "None")
        with col_r:
            st.subheader("❌ Missing Keywords")
            st.write(", ".join(data["missing_keywords"]) or "None")

        if data["recommendations"]:
            st.subheader("💡 Recommendations")
            for rec in data["recommendations"]:
                st.markdown(f"- {rec}")


# ─── PAGE: SKILL GAP ──────────────────────────────────────────────────────────

def page_skill_gap():
    st.title("🔍 Skill Gap Analysis")
    st.markdown("Identify your skill gaps and get **personalized learning recommendations**.")

    resumes = api("get", "/resumes/").json() if st.session_state.token else []
    if not isinstance(resumes, list) or not resumes:
        st.warning("Upload a resume first.")
        return

    resume_options = {r["name"]: r["id"] for r in resumes}
    active = next((r["name"] for r in resumes if r["is_active"]), list(resume_options.keys())[0])
    selected_name = st.selectbox("Resume", list(resume_options.keys()), index=list(resume_options.keys()).index(active))
    selected_id = resume_options[selected_name]

    jd = st.text_area("Job Description", height=250)

    if st.button("🔍 Analyze Skill Gap", type="primary"):
        if not jd.strip():
            show_error("Please paste a job description.")
            return
        with st.spinner("Analyzing gaps and generating recommendations with AI..."):
            resp = api("post", "/ai/skill-gap", json={"job_description": jd, "resume_id": selected_id})

        if resp.status_code != 200:
            show_error(resp.json().get("detail", "Analysis failed."))
            return

        data = resp.json()
        st.metric("ATS Score", f"{data['ats_score']}%")

        col_l, col_r = st.columns(2)
        with col_l:
            st.subheader("✅ Skills You Have")
            for s in data["matched_skills"][:15]:
                st.markdown(f"- `{s}`")
        with col_r:
            st.subheader("❌ Missing Skills")
            for s in data["missing_skills"][:15]:
                st.markdown(f"- `{s}`")

        if data.get("priority_gaps"):
            st.subheader("🚨 Priority Gaps (High-value skills)")
            st.warning(", ".join(data["priority_gaps"]))

        if data.get("learning_recommendations"):
            st.subheader("📚 AI Learning Recommendations")
            for rec in data["learning_recommendations"]:
                st.markdown(f"- {rec}")


# ─── PAGE: INTERVIEW QUESTIONS ────────────────────────────────────────────────

def page_interview_questions():
    st.title("🎙️ Interview Question Generator")
    st.markdown("Get **10 tailored interview questions** based on your resume and the job description.")

    resumes = api("get", "/resumes/").json() if st.session_state.token else []
    if not isinstance(resumes, list) or not resumes:
        st.warning("Upload a resume first.")
        return

    resume_options = {r["name"]: r["id"] for r in resumes}
    active = next((r["name"] for r in resumes if r["is_active"]), list(resume_options.keys())[0])
    selected_name = st.selectbox("Resume", list(resume_options.keys()), index=list(resume_options.keys()).index(active))
    selected_id = resume_options[selected_name]

    jd = st.text_area("Job Description", height=200)

    if st.button("🎙️ Generate Questions", type="primary"):
        if not jd.strip():
            show_error("Please paste a job description.")
            return
        with st.spinner("Generating tailored interview questions..."):
            resp = api("post", "/ai/interview-questions", json={"job_description": jd, "resume_id": selected_id})

        if resp.status_code != 200:
            show_error(resp.json().get("detail", "Failed to generate questions."))
            return

        questions = resp.json().get("questions", [])
        st.subheader(f"🎤 {len(questions)} Interview Questions")
        for i, q in enumerate(questions, 1):
            st.markdown(f"**{i}.** {q}")


# ─── PAGE: JOB TRACKER ────────────────────────────────────────────────────────

def page_job_tracker():
    st.title("📊 Job Application Tracker")

    STATUS_EMOJIS = {
        "wishlist": "⭐", "applied": "📨", "phone_screen": "📞",
        "interview": "🎤", "offer": "🎉", "rejected": "❌", "accepted": "✅"
    }

    # Add application
    with st.expander("➕ Add New Application"):
        with st.form("add_job_form"):
            col1, col2 = st.columns(2)
            company = col1.text_input("Company")
            role = col2.text_input("Role / Title")
            status = st.selectbox("Status", list(STATUS_EMOJIS.keys()))
            job_url = st.text_input("Job URL (optional)")
            notes = st.text_area("Notes", height=80)
            if st.form_submit_button("Add Application", type="primary"):
                resp = api("post", "/jobs/", json={
                    "company": company, "role": role, "status": status,
                    "job_url": job_url or None, "notes": notes or None,
                })
                if resp.status_code == 201:
                    show_success("Application added!")
                    st.rerun()
                else:
                    show_error(resp.json().get("detail", "Failed to add."))

    # Stats
    stats = api("get", "/jobs/stats").json()
    if isinstance(stats, dict) and "by_status" in stats:
        st.subheader(f"📈 Pipeline — {stats['total']} Applications")
        cols = st.columns(7)
        for col, (s, count) in zip(cols, stats["by_status"].items()):
            col.metric(f"{STATUS_EMOJIS.get(s, '')} {s.replace('_', ' ').title()}", count)

    # Filter
    st.divider()
    filter_status = st.selectbox("Filter by Status", ["All"] + list(STATUS_EMOJIS.keys()))
    params = {} if filter_status == "All" else {"status_filter": filter_status}
    apps_resp = api("get", "/jobs/", params=params)
    apps = apps_resp.json() if apps_resp.status_code == 200 else []

    if not apps:
        st.info("No applications yet. Add one above!")
        return

    for app in apps:
        emoji = STATUS_EMOJIS.get(app["status"], "")
        with st.expander(f"{emoji} **{app['company']}** — {app['role']}  |  `{app['status']}`"):
            col1, col2 = st.columns([3, 1])
            with col1:
                st.markdown(f"**Applied:** {app.get('applied_at', 'N/A')}")
                if app.get("job_url"):
                    st.markdown(f"**URL:** [{app['job_url']}]({app['job_url']})")
                if app.get("notes"):
                    st.markdown(f"**Notes:** {app['notes']}")
            with col2:
                new_status = st.selectbox(
                    "Update Status",
                    list(STATUS_EMOJIS.keys()),
                    index=list(STATUS_EMOJIS.keys()).index(app["status"]),
                    key=f"status_{app['id']}",
                )
                if st.button("Save", key=f"save_{app['id']}"):
                    api("patch", f"/jobs/{app['id']}", json={"status": new_status})
                    st.rerun()
                if st.button("🗑️ Delete", key=f"del_{app['id']}"):
                    api("delete", f"/jobs/{app['id']}")
                    st.rerun()


# ─── MAIN ─────────────────────────────────────────────────────────────────────

if not st.session_state.token:
    page_auth()
else:
    page = sidebar()

    if page == "📋 Dashboard":
        page_dashboard()
    elif page == "📄 My Resumes":
        page_resumes()
    elif page == "✉️ Cover Letter":
        page_cover_letter()
    elif page == "🎯 ATS Score":
        page_ats_score()
    elif page == "🔍 Skill Gap":
        page_skill_gap()
    elif page == "🎙️ Interview Questions":
        page_interview_questions()
    elif page == "📊 Job Tracker":
        page_job_tracker()
