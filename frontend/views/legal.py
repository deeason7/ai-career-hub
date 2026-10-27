"""Legal & Info page — how-to, terms, disclaimer, AI notice, privacy."""

import streamlit as st

from ui import page_header


def page_legal() -> None:
    page_header("📜", "Legal & Info")

    tab_use, tab_terms, tab_disclaimer, tab_ai, tab_privacy = st.tabs(
        [
            "📖 How to Use",
            "📄 Terms of Use",
            "⚠️ Disclaimer",
            "🤖 AI Notice",
            "🔒 Privacy",
        ]
    )

    with tab_use:
        st.subheader("📖 How to Use AI Career Hub")
        st.markdown("""
        1. **Register / Login** — Create a free account with your email and password.
        2. **Upload a Resume** — Go to *My Resumes*, upload a PDF, DOCX, or TXT (max 5 MB).
           Label it clearly (e.g. "Software Engineer 2026").
        3. **Set an Active Resume** — Mark one resume as active. All AI tools will use it.
        4. **Job Match Analysis** — Paste one job description and get your ATS score,
           skill gap breakdown, and tailored interview questions.
           Review the matching evidence and gaps; the score is not a hiring prediction.
        5. **Cover Letter** — Creates a draft grounded in your resume context, with a model QA review.
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

        The live demo uses free hosted services that can sleep during inactivity.
        Startup time varies by provider; a paused service may require the owner to resume it.
        """)

    with tab_ai:
        st.subheader("🤖 AI Content Notice")
        st.markdown("""
        This platform uses a hosted language model via **Groq API** to generate content.

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

        The public demo uses Streamlit Community Cloud for the website, Hugging Face
        Spaces for the API, Neon PostgreSQL for stored records, Upstash Redis for
        temporary task and session state, and Qdrant Cloud for document retrieval.
        Resume and job-description text is sent to Groq for AI inference.
        Self-hosted installations may use different providers.

        **What is stored:**
        - Account email, hashed password (bcrypt), full name
        - Extracted resume text (raw uploaded files are NOT stored)
        - Cover letters, revisions, ATS scores, and job application records you create
        - Document chunks and embeddings used for retrieval
        - Selected account activity and operational diagnostics

        **What is NOT stored:**
        - Raw uploaded files (only text is persisted)
        - Payment data (no payments collected)
        - Advertising profiles or product analytics collected by this application

        **Retention and deletion:**
        - The first resume is retained until deleted. Later resumes and saved letters
          are scheduled for cleanup after 15 days; there is no pin/unpin control.
        - You can delete resumes and job records from the UI. Removing a resume also
          removes its saved letters, while tracker history can remain.
        - Scheduled cleanup does not yet erase all retrieval copies. Explicit resume
          deletion attempts to remove that resume's retrieval copies, but related
          letter and posting copies can remain. Complete deletion is still being improved.
        - There is no self-service account deletion. Contact the repository owner
          privately for a request; do not post personal documents in a public issue.
        - Hosting providers may retain operational logs and backups under their policies.

        **Recommendations:**
        - Do **not** upload resumes containing passport numbers, government IDs,
          or financial account details to the public demo
        - For full data control, self-host using the Docker Compose setup

        *The app uses a sign-in cookie. Hosting providers and optional error reporting
        may process technical usage information; this app does not provide advertising.*
        """)
