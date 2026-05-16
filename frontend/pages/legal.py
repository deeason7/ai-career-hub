"""Legal & Info page — how-to, terms, disclaimer, AI notice, privacy."""

import streamlit as st


def page_legal() -> None:
    st.title("📜 Legal & Info")

    tab_use, tab_terms, tab_disclaimer, tab_ai, tab_privacy = st.tabs(
        ["📖 How to Use", "📄 Terms of Use", "⚠️ Disclaimer", "🤖 AI Notice", "🔒 Privacy"]
    )

    with tab_use:
        st.subheader("📖 How to Use AI Career Hub")
        st.markdown("""
        1. **Register / Login** — Create a free account with your email and password.
        2. **Upload a Resume** — Go to *My Resumes*, upload a PDF, DOCX, or TXT (max 5 MB).
           Label it clearly (e.g. "Software Engineer 2026").
        3. **Set an Active Resume** — Mark one resume as active. All AI tools will use it.
        4. **Job Match Analysis** — Paste one job description and get your ATS score,
           skill gap breakdown, and 10 tailored interview questions — all in one click.
           Aim for 70%+ ATS before applying.
        5. **Cover Letter** — Generates a RAG-based letter using only facts from your resume.
           Always proofread before sending.
        6. **Job Tracker** — Track every application from wishlist to offer.

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
