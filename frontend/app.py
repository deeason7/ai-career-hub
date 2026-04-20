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
import io
import json
import os
import time

import extra_streamlit_components as stx
import requests
import streamlit as st

# ─── Config ───────────────────────────────────────────────────────────────────
API_URL = os.environ.get("API_URL", "http://api:8000/api/v1")

st.set_page_config(
    page_title="AI Career Hub",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Cookie manager — instantiated directly at module level.
# CookieManager is a Streamlit custom component (widget) and MUST NOT be
# wrapped in @st.cache_resource or @st.cache_data: Streamlit cannot replay
# widget calls from cache, which raises CachedWidgetWarning and crashes.
cookie_manager = stx.CookieManager(key="careerhub_session")

# ─── Session State Init ───────────────────────────────────────────────────────
for key in ["token", "user"]:
    if key not in st.session_state:
        st.session_state[key] = None
if "current_page" not in st.session_state:
    st.session_state["current_page"] = "📋 Dashboard"
if "disclaimer_accepted" not in st.session_state:
    st.session_state["disclaimer_accepted"] = False
if "disclaimer_never_show" not in st.session_state:
    st.session_state["disclaimer_never_show"] = False


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


def safe_json(resp: requests.Response, fallback=None):
    """Safely parse JSON from a response; returns fallback on decode errors (e.g. 502s)."""
    try:
        return resp.json()
    except Exception:
        return fallback


def _detail(resp: requests.Response, default: str = "An unexpected error occurred.") -> str:
    """Extract error detail from an error response, safely."""
    data = safe_json(resp, {})
    if isinstance(data, dict):
        return data.get("detail", default)
    return f"API error (HTTP {resp.status_code})"


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
                    data = safe_json(resp, {})
                    st.session_state.token = data.get("access_token")
                    if not st.session_state.token:
                        show_error("Login failed: no token received.")
                        return
                    # Persist JWT in a browser cookie so refreshes keep the session alive.
                    # expires_at matches the backend JWT expiry (60 min).
                    from datetime import datetime, timedelta
                    cookie_manager.set(
                        "auth_token",
                        st.session_state.token,
                        expires_at=datetime.now() + timedelta(hours=1),
                    )
                    me = safe_json(api("get", "/auth/me"), {})
                    st.session_state.user = me
                    show_success("Logged in!")
                    st.rerun()
                elif resp.status_code == 503:
                    st.warning(
                        "⏳ **Database is still warming up** — this is normal after a cold start.\n\n"
                        "Please wait **~30 seconds** and try again."
                    )
                elif resp.status_code == 429:
                    show_error("Too many login attempts. Please wait 1 minute and try again.")
                else:
                    show_error(_detail(resp, "Login failed."))

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
                elif resp.status_code == 503:
                    st.warning(
                        "⏳ **Database is still warming up** — this is normal after a cold start.\n\n"
                        "Please wait **~30 seconds** and try again."
                    )
                elif resp.status_code == 429:
                    show_error("Too many registration attempts. Please wait 1 minute and try again.")
                else:
                    show_error(_detail(resp, "Registration failed."))

# ─── Job URL Import Helper ─────────────────────────────────────────────────────

def _job_url_import(key_prefix: str) -> str:
    """
    Show a collapsible 'Import from URL' expander.
    Returns the fetched job description text, or empty string if not used.
    """
    fetched_jd = ""
    with st.expander("🔗 Import Job from URL (LinkedIn, Greenhouse, Lever…)"):
        st.caption(
            "Paste any public job posting URL. LinkedIn may require login for the full description — "
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
                    show_success("Job description fetched! Scroll down — it’s pre-filled below.")
                    if data.get("warning"):
                        st.warning(data["warning"])
                else:
                    show_error(_detail(resp, "Could not fetch job description."))
    # Return any previously fetched JD stored in session state
    return st.session_state.get(f"{key_prefix}_prefilled_jd", "")


# ─── Disclaimer Modal ───────────────────────────────────────────────────────

@st.dialog("⚠️ Terms & Disclaimer")
def show_disclaimer_modal():
    st.markdown("""
    **Please read before using AI Career Hub.**

    🤖 **AI-Generated Content**
    All outputs (cover letters, ATS scores, interview questions) are generated by AI.
    They may contain inaccuracies. **Always review before submitting to employers.**

    🛡️ **Educational Use Only**
    This platform is provided for educational and demonstration purposes.
    It is not a substitute for professional career, legal, or financial advice.
    The author accepts no liability for outcomes arising from your use of this tool.

    🔒 **Your Data**
    Resume text is stored in a hosted database (Supabase). AI requests are sent
    to Groq’s API. Do **not** upload documents with passport numbers, government
    IDs, or financial details.

    By continuing you acknowledge these terms. Full details in **📜 Legal & Info**.
    """)
    st.divider()
    col_a, col_b = st.columns(2)
    if col_a.button("✅ I Understand", use_container_width=True, type="primary"):
        st.session_state["disclaimer_accepted"] = True
        st.rerun()
    if col_b.button("🔕 Never Show Again", use_container_width=True):
        st.session_state["disclaimer_accepted"] = True
        st.session_state["disclaimer_never_show"] = True
        st.rerun()


# ─── SIDEBAR & NAVIGATION ─────────────────────────────────────────────────────

def sidebar():
    _pages = [
        "📋 Dashboard",
        "📄 My Resumes",
        "✉️ Cover Letter",
        "🎯 ATS Score",
        "🔍 Skill Gap",
        "🎙️ Interview Questions",
        "📊 Job Tracker",
        "📜 Legal & Info",
    ]
    with st.sidebar:
        st.title("🚀 AI Career Hub")
        user = st.session_state.user or {}
        st.markdown(f"👤 **{user.get('full_name', 'User')}**  \n`{user.get('email', '')}`")
        st.divider()

        # Sync radio with session state so buttons can drive navigation
        current_idx = _pages.index(st.session_state["current_page"]) if st.session_state["current_page"] in _pages else 0
        page = st.radio(
            "Navigation",
            _pages,
            index=current_idx,
            label_visibility="collapsed",
        )
        st.session_state["current_page"] = page
        st.divider()
        if st.button("🚪 Logout"):
            cookie_manager.delete("auth_token")  # clear access-token cookie
            # Also clear the HttpOnly refresh-token cookie via the backend endpoint
            try:
                requests.post(f"{API_URL}/auth/logout", timeout=3)
            except Exception:
                pass  # best-effort — local state is still cleared
            st.session_state.token = None
            st.session_state.user = None
            st.session_state["current_page"] = "📋 Dashboard"
            st.rerun()
    return page


# ─── PAGE: DASHBOARD ──────────────────────────────────────────────────────────

def page_dashboard():
    st.title("📋 Dashboard")

    # Resume count
    resumes = safe_json(api("get", "/resumes/"), []) if st.session_state.token else []
    jobs = safe_json(api("get", "/jobs/stats"), {}) if st.session_state.token else {}
    cover_letters = safe_json(api("get", "/cover-letters/"), []) if st.session_state.token else []

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
    if q1.button("📄 Upload Resume", use_container_width=True, type="primary"):
        st.session_state["current_page"] = "📄 My Resumes"
        st.rerun()
    if q2.button("✉️ Generate Cover Letter", use_container_width=True, type="primary"):
        st.session_state["current_page"] = "✉️ Cover Letter"
        st.rerun()
    if q3.button("🎯 Score My Resume", use_container_width=True, type="primary"):
        st.session_state["current_page"] = "🎯 ATS Score"
        st.rerun()


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
                        show_error(_detail(resp, "Upload failed."))

    # List
    resumes_resp = api("get", "/resumes/")
    if resumes_resp.status_code != 200:
        show_error("Could not fetch resumes.")
        return

    resumes = safe_json(resumes_resp, [])
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
    resumes = safe_json(api("get", "/resumes/"), []) if st.session_state.token else []
    if not isinstance(resumes, list) or not resumes:
        st.warning("⚠️ Upload a resume first in **My Resumes**.")
        return

    resume_options = {r["name"]: r["id"] for r in resumes}
    active = next((r["name"] for r in resumes if r["is_active"]), list(resume_options.keys())[0])
    selected_name = st.selectbox("Choose Resume", list(resume_options.keys()), index=list(resume_options.keys()).index(active))
    selected_id = resume_options[selected_name]

    prefilled_jd = _job_url_import("cover_letter")
    jd = st.text_area(
        "Paste the Job Description",
        value=prefilled_jd,
        height=300,
        placeholder="Paste the full job posting here, or import from URL above.",
    )

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
            show_error(_detail(resp, f"API error (HTTP {resp.status_code}). Is the backend running?"))
            return

        cl = safe_json(resp, {})
        task_id = cl.get("task_id")
        cl_id = cl.get("id")
        st.info(f"Task started. ID: `{task_id}`")

        progress = st.progress(0, text="Generating cover letter...")
        status_box = st.empty()
        ticks = 0
        while True:
            time.sleep(2)
            ticks += 1
            poll = safe_json(api("get", f"/cover-letters/task/{task_id}"), {})
            status = poll.get("status", "PENDING")
            progress.progress(min(ticks * 5, 90), text=f"Status: {status}")
            status_box.markdown(f"**Status:** `{status}`")

            if status == "SUCCESS":
                progress.progress(100, text="Done!")
                # Fetch updated record from DB
                detail = safe_json(api("get", f"/cover-letters/{cl_id}"), {})
                cover_text = detail.get("generated_text", "")
                show_success("Cover letter generated!")
                st.text_area("📝 Your Cover Letter", cover_text, height=450)
                dl_col1, dl_col2 = st.columns(2)
                dl_col1.download_button(
                    " Download TXT",
                    cover_text,
                    file_name="cover_letter.txt",
                    use_container_width=True,
                )
                # PDF download — fetch from backend
                pdf_resp = api("get", f"/cover-letters/{cl_id}/pdf")
                if pdf_resp.status_code == 200:
                    dl_col2.download_button(
                        "📄 Download PDF",
                        pdf_resp.content,
                        file_name="cover_letter.pdf",
                        mime="application/pdf",
                        use_container_width=True,
                        type="primary",
                    )
                break
            elif status == "FAILURE":
                show_error("Task failed. Check the backend worker logs.")
                break
            elif ticks > 60:
                show_error("Timed out after 2 minutes. Check the backend logs.")
                break

    st.divider()
    st.subheader("📜 Past Cover Letters")
    history = safe_json(api("get", "/cover-letters/"), [])
    if isinstance(history, list) and history:
        for cl in history[:5]:
            status_label = cl.get("status", "")
            with st.expander(f"Cover Letter — {cl['created_at'][:10]} | Status: `{status_label}`"):
                if cl.get("generated_text"):
                    st.text_area("", cl["generated_text"], height=250, key=f"hist_{cl['id']}")
                    h_col1, h_col2 = st.columns(2)
                    h_col1.download_button(
                        " TXT",
                        cl["generated_text"],
                        file_name="cover_letter.txt",
                        key=f"txt_{cl['id']}",
                        use_container_width=True,
                    )
                    pdf_resp = api("get", f"/cover-letters/{cl['id']}/pdf")
                    if pdf_resp.status_code == 200:
                        h_col2.download_button(
                            "📄 PDF",
                            pdf_resp.content,
                            file_name="cover_letter.pdf",
                            mime="application/pdf",
                            key=f"pdf_{cl['id']}",
                            use_container_width=True,
                            type="primary",
                        )
    else:
        st.info("No cover letters generated yet.")


# ─── PAGE: ATS SCORE ──────────────────────────────────────────────────────────

def page_ats_score():
    st.title("🎯 ATS Score Analyzer")
    st.markdown("Scores your resume against any job description in **< 1 second** — instant algorithmic analysis.")

    resumes = safe_json(api("get", "/resumes/"), []) if st.session_state.token else []
    if not isinstance(resumes, list) or not resumes:
        st.warning("Upload a resume first.")
        return

    resume_options = {r["name"]: r["id"] for r in resumes}
    active = next((r["name"] for r in resumes if r["is_active"]), list(resume_options.keys())[0])
    selected_name = st.selectbox("Resume", list(resume_options.keys()), index=list(resume_options.keys()).index(active))
    selected_id = resume_options[selected_name]

    prefilled_jd = _job_url_import("ats")
    jd = st.text_area("Job Description", value=prefilled_jd, height=250,
                      placeholder="Paste the job description or import from URL above.")

    if st.button("🎯 Score My Resume", type="primary"):
        if not jd.strip():
            show_error("Please paste a job description.")
            return
        with st.spinner("Scoring..."):
            resp = api("post", "/ai/ats-score", json={"job_description": jd, "resume_id": selected_id})

        if resp.status_code == 429:
            show_error("Too many requests. Please wait 1 minute and try again.")
            return
        if resp.status_code != 200:
            show_error(_detail(resp, "Scoring failed."))
            return

        data = safe_json(resp, {})
        score = data["score"]
        sem_score = data.get("semantic_score", 0)

        # --- Main metrics row ---
        color = "🟢" if score >= 70 else "🟡" if score >= 45 else "🔴"
        col1, col2, col3, col4 = st.columns(4)
        col1.metric(f"{color} ATS Score", f"{score}%", help="Composite: 50% semantic + 30% keyword + 20% structure")
        col2.metric("🧠 Semantic Match", f"{sem_score}%", help="Sentence-transformer cosine similarity — catches synonyms and paraphrases")
        col3.metric("🔑 Keyword Score", f"{data['keyword_score']}%", help="Exact + bigram keyword overlap")
        col4.metric("📐 Structure Score", f"{data['structure_score']}%", help="Section presence and resume length")

        st.progress(int(score) / 100)

        # --- Semantic score interpretation ---
        if sem_score >= 70:
            st.success("🧠 High semantic alignment — your resume language closely matches the job description.")
        elif sem_score >= 45:
            st.warning("🧠 Moderate semantic alignment — consider mirroring more of the job description's phrasing.")
        elif sem_score > 0:
            st.error("🧠 Low semantic alignment — your resume content may not be addressing what this role requires.")

        # --- Section-level breakdown ---
        section_scores = data.get("section_scores", {})
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

    resumes = safe_json(api("get", "/resumes/"), []) if st.session_state.token else []
    if not isinstance(resumes, list) or not resumes:
        st.warning("Upload a resume first.")
        return

    resume_options = {r["name"]: r["id"] for r in resumes}
    active = next((r["name"] for r in resumes if r["is_active"]), list(resume_options.keys())[0])
    selected_name = st.selectbox("Resume", list(resume_options.keys()), index=list(resume_options.keys()).index(active))
    selected_id = resume_options[selected_name]

    prefilled_jd = _job_url_import("skill_gap")
    jd = st.text_area("Job Description", value=prefilled_jd, height=250,
                      placeholder="Paste the job description or import from URL above.")

    if st.button("🔍 Analyze Skill Gap", type="primary"):
        if not jd.strip():
            show_error("Please paste a job description.")
            return
        with st.spinner("Analyzing gaps and generating recommendations with AI..."):
            resp = api("post", "/ai/skill-gap", json={"job_description": jd, "resume_id": selected_id})

        if resp.status_code != 200:
            show_error(_detail(resp, "Analysis failed."))
            return

        data = safe_json(resp, {})
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

    resumes = safe_json(api("get", "/resumes/"), []) if st.session_state.token else []
    if not isinstance(resumes, list) or not resumes:
        st.warning("Upload a resume first.")
        return

    resume_options = {r["name"]: r["id"] for r in resumes}
    active = next((r["name"] for r in resumes if r["is_active"]), list(resume_options.keys())[0])
    selected_name = st.selectbox("Resume", list(resume_options.keys()), index=list(resume_options.keys()).index(active))
    selected_id = resume_options[selected_name]

    prefilled_jd = _job_url_import("interview")
    jd = st.text_area("Job Description", value=prefilled_jd, height=200,
                      placeholder="Paste the job description or import from URL above.")

    if st.button("🎙️ Generate Questions", type="primary"):
        if not jd.strip():
            show_error("Please paste a job description.")
            return
        with st.spinner("Generating tailored interview questions..."):
            resp = api("post", "/ai/interview-questions", json={"job_description": jd, "resume_id": selected_id})

        if resp.status_code != 200:
            show_error(_detail(resp, "Failed to generate questions."))
            return

        questions = safe_json(resp, {}).get("questions", [])
        st.subheader(f"🎤 {len(questions)} Interview Questions")
        for i, q in enumerate(questions, 1):
            st.markdown(f"**{i}.** {q}")


# ─── PAGE: JOB TRACKER ───────────────────────────────────────────────────────

STATUS_EMOJIS = {
    "wishlist": "💭",
    "applied": "📤",
    "phone_screen": "📞",
    "interview": "🎯",
    "offer": "🎉",
    "rejected": "❌",
    "accepted": "✅",
}


def _deadline_badge(deadline_str: str | None) -> str:
    """Return an urgency badge string based on how close the deadline is."""
    if not deadline_str:
        return ""
    from datetime import date
    try:
        dl = date.fromisoformat(deadline_str)
    except ValueError:
        return ""
    days = (dl - date.today()).days
    if days < 0:
        return f"  🔴 **Overdue** ({abs(days)}d ago)"
    elif days == 0:
        return "  🔴 **Due Today!**"
    elif days == 1:
        return "  🟡 **Due Tomorrow**"
    elif days <= 7:
        return f"  🟠 **Due in {days}d**"
    else:
        return f"  🗓️ Due {dl.strftime('%b %d')}"


def page_job_tracker():
    st.title("📊 Job Application Tracker")

    # Add application
    with st.expander("➕ Add New Application"):
        with st.form("add_job_form"):
            col1, col2 = st.columns(2)
            company = col1.text_input("Company")
            role = col2.text_input("Role / Title")
            status = st.selectbox("Status", list(STATUS_EMOJIS.keys()))
            job_url = st.text_input("Job URL (optional)")
            deadline = st.date_input("Application Deadline (optional)", value=None)
            notes = st.text_area("Notes", height=80)
            if st.form_submit_button("Add Application", type="primary"):
                resp = api("post", "/jobs/", json={
                    "company": company, "role": role, "status": status,
                    "job_url": job_url or None, "notes": notes or None,
                    "deadline": deadline.isoformat() if deadline else None,
                })
                if resp.status_code == 201:
                    show_success("Application added!")
                    st.rerun()
                else:
                    show_error(_detail(resp, "Failed to add."))

    # Stats
    stats = safe_json(api("get", "/jobs/stats"), {})
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
        badge = _deadline_badge(app.get("deadline"))
        with st.expander(f"{emoji} **{app['company']}** — {app['role']}  |  `{app['status']}`{badge}"):
            col1, col2 = st.columns([3, 1])
            with col1:
                st.markdown(f"**Applied:** {app.get('applied_at', 'N/A')}")
                if app.get("deadline"):
                    badge_text = _deadline_badge(app["deadline"])
                    st.markdown(f"**Deadline:** `{app['deadline']}`{badge_text}")
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
                new_deadline = st.date_input(
                    "Deadline",
                    value=None,
                    key=f"dl_{app['id']}",
                    help="Leave empty to keep existing deadline",
                )
                if st.button("Save", key=f"save_{app['id']}"):
                    patch = {"status": new_status}
                    if new_deadline:
                        patch["deadline"] = new_deadline.isoformat()
                    api("patch", f"/jobs/{app['id']}", json=patch)
                    st.rerun()
                if st.button("🗑️ Delete", key=f"del_{app['id']}"):
                    api("delete", f"/jobs/{app['id']}")
                    st.rerun()


# ─── PAGE: LEGAL & INFO ──────────────────────────────────────────────────────────────

def page_legal():
    st.title("📜 Legal & Info")

    tab_use, tab_terms, tab_disclaimer, tab_ai, tab_privacy = st.tabs([
        "📖 How to Use",
        "📄 Terms of Use",
        "⚠️ Disclaimer",
        "🤖 AI Notice",
        "🔒 Privacy",
    ])

    with tab_use:
        st.subheader("📖 How to Use AI Career Hub")
        st.markdown("""
        1. **Register / Login** — Create a free account with your email and password.
        2. **Upload a Resume** — Go to *My Resumes*, upload a PDF, DOCX, or TXT (max 5 MB).
           Label it clearly (e.g. “Software Engineer 2026”).
        3. **Set an Active Resume** — Mark one resume as active. All AI tools will use it.
        4. **ATS Score** — Paste a job description and score your resume instantly.
           Aim for 70%+ before applying.
        5. **Skill Gap** — Identifies missing skills and suggests learning resources.
        6. **Cover Letter** — Generates a RAG-based letter using only facts from your resume.
           Always proofread before sending.
        7. **Interview Questions** — Get 10 tailored questions based on your resume + job.
        8. **Job Tracker** — Track every application from wishlist to offer.

        > ⚠️ AI outputs are drafts. Review carefully before using in real applications.
        """)

    with tab_terms:
        st.subheader("📄 Terms of Use")
        st.markdown("""
        By using AI Career Hub you agree to the following:

        - You will use this platform for **lawful purposes only**.
        - You will **not** attempt to reverse-engineer, scrape, or abuse the API.
        - You acknowledge that AI-generated content **may be inaccurate** and take full
          responsibility for how you use it.
        - You will **not** upload content that violates intellectual property rights,
          contains malware, or is otherwise illegal.
        - The author reserves the right to **suspend accounts** that abuse the service
          (e.g. rate limit circumvention, uploading malicious files).
        - These terms may change at any time. Continued use constitutes acceptance.

        *Last updated: March 2026*
        """)

    with tab_disclaimer:
        st.subheader("⚠️ Disclaimer")
        st.markdown("""
        **This project is for educational and demonstration purposes only.**

        The author makes no warranties — express or implied — about the completeness,
        reliability, accuracy, or suitability of this software or the AI-generated content
        it produces. Any action you take based on information or output from this platform
        is **strictly at your own risk**.

        The author will **not** be liable for any losses, damages, or negative
        outcomes — financial, professional, or otherwise — arising from:

        - Use or misuse of this software
        - AI-generated content that is inaccurate or unsuitable
        - Reliance on this platform as professional career, legal, or financial advice
        - Data loss or security incidents in self-hosted deployments
        - Downtime, service suspension, or data reset on the free-tier demo

        The live demo is hosted on Render.com free tier and may be suspended or reset
        at any time without notice.
        """)

    with tab_ai:
        st.subheader("🤖 AI Content Notice")
        st.markdown("""
        This platform uses **LLaMA 3.1 8B** via **Groq API** to generate content.

        - AI outputs may be **inaccurate, incomplete, or hallucinated** despite RAG safeguards.
        - Cover letters, interview questions, and skill recommendations are **AI drafts**
          — not professional career advice.
        - The author is **not responsible** for the content of your resume inputs
          or the AI outputs generated from them.
        - **Always proofread** AI-generated cover letters before submitting to real employers.
        - ATS scores are algorithmic estimates — actual applicant tracking systems vary widely.

        By using the AI features you accept that outputs require human review and judgment.
        """)

    with tab_privacy:
        st.subheader("🔒 Privacy Policy")
        st.markdown("""
        **Hosted Services**

        | Platform | Role | Privacy Policy |
        |----------|------|----------------|
        | Render.com | API & frontend hosting | [render.com/privacy](https://render.com/privacy) |
        | Supabase | PostgreSQL database | [supabase.com/privacy](https://supabase.com/privacy) |
        | Groq | AI inference | [groq.com/privacy-policy](https://groq.com/privacy-policy/) |

        **What is stored:**
        - Account email, hashed password (bcrypt), full name
        - Extracted resume text (raw uploaded files are NOT stored)
        - Cover letters, ATS scores, and job application records you create

        **What is NOT stored:**
        - Raw uploaded files (only text is persisted)
        - Payment data (no payments collected)
        - Tracking cookies, fingerprints, or analytics data

        **Your rights:**
        - Delete resumes and job records at any time from the UI
        - To request full account deletion, open a GitHub issue

        **Recommendations:**
        - Do **not** upload resumes containing passport numbers, government IDs,
          or financial account details to the public demo
        - For full data control, self-host using the Docker Compose setup

        *This project does not include analytics, advertising, or third-party tracking.*
        """)


# ─── MAIN ──────────────────────────────────────────────────────────────────────

# ── Session restore from cookie (survives browser refresh) ────────────────────
# On first load after a refresh, session_state is empty. Check the browser
# cookie for a stored JWT and verify it's still valid via /auth/me.
if not st.session_state.token:
    _cookie_token = cookie_manager.get("auth_token")
    if _cookie_token:
        st.session_state.token = _cookie_token  # temp-set so api() sends the header
        _me = safe_json(api("get", "/auth/me"), {})
        if _me and _me.get("email"):
            st.session_state.user = _me          # valid — session fully restored
        else:
            # Token expired or invalid — clear cookie and force re-login
            cookie_manager.delete("auth_token")
            st.session_state.token = None

# ── Page routing ─────────────────────────────────────────────────────────────
if not st.session_state.token:
    page_auth()
else:
    # Show disclaimer modal on first login (unless user clicked Never Show Again)
    if not st.session_state["disclaimer_accepted"] and not st.session_state["disclaimer_never_show"]:
        show_disclaimer_modal()

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
    elif page == "📜 Legal & Info":
        page_legal()
