# 🚀 AI Career Hub

An AI-powered career acceleration platform built with a production-grade engineering stack.  
Upload your resume, score it semantically against job descriptions, generate honest cover letters, track applications with deadlines — all in one place.

[![CI](https://github.com/deeason7/ai-career-hub/actions/workflows/ci.yml/badge.svg)](https://github.com/deeason7/ai-career-hub/actions/workflows/ci.yml)
[![Deploy](https://github.com/deeason7/ai-career-hub/actions/workflows/deploy.yml/badge.svg)](https://github.com/deeason7/ai-career-hub/actions/workflows/deploy.yml)

## 🌐 Live Demo

| Service | URL |
|---------|-----|
| **Frontend** | https://ai-career-hub-frontend.onrender.com |
| **API (Swagger)** | https://ai-career-hub-api.onrender.com/docs |
| **Health Check** | https://ai-career-hub-api.onrender.com/health |

> **Note:** Free tier services spin down after 15 min of inactivity. First load may take ~30s to wake up.

---

## ✨ Features

| Feature | Details |
|---------|---------|
| 👤 **Multi-Resume Management** | Upload, store, and switch between up to 10 resumes per user (PDF, DOCX, TXT — 5 MB max) |
| 🧠 **Semantic ATS Score Analyzer** | sentence-transformers dense vector similarity + keyword matching + structure scoring — catches synonym matches that keyword-only ATS misses |
| 📝 **AI Cover Letter Generator** | RAG-based zero-hallucination generation using FAISS + LangChain — only uses facts from YOUR resume |
| 📄 **PDF Export** | Download any generated cover letter as a professionally formatted PDF |
| 🔗 **Job URL Import** | Paste a LinkedIn / Greenhouse / Lever URL to auto-fill the job description field |
| 🔍 **Skill Gap Analysis** | Identify missing skills with AI-powered upskilling recommendations |
| 🎙️ **Interview Question Generator** | 10 tailored questions generated from your resume + job description |
| 📊 **Application Tracker** | Full pipeline tracking with optional deadline dates and color-coded urgency badges |
| ⚖️ **Legal Disclaimer** | Post-login disclaimer modal with "I Understand" + "Never Show Again" options |

---

## 🏗️ Architecture

```
                    GitHub Actions (CI)
                          │  lint + test on every PR
                          ▼
┌─────────────────────────────────────────────────┐
│                  Render.com                     │
│  ┌──────────────┐        ┌──────────────────┐  │
│  │  Streamlit   │◄──────►│    FastAPI       │  │
│  │  Frontend    │  HTTP  │    Backend       │  │
│  └──────────────┘        └────────┬─────────┘  │
│                                   │             │
│              ┌────────────────────┤             │
│              │                    │             │
│  ┌───────────▼────┐   ┌──────────▼──────────┐  │
│  │   Supabase     │   │    Groq API (free)  │  │
│  │   PostgreSQL   │   │  LLaMA 3.1 8B LLM  │  │
│  │  + RLS Rules   │   └─────────────────────┘  │
│  └────────────────┘                             │
└─────────────────────────────────────────────────┘
```

**Cover letter generation** runs as a FastAPI `BackgroundTask` — no separate Celery worker needed.  
**Semantic ATS scoring** uses `all-MiniLM-L6-v2` (80 MB, CPU-only, loaded once at startup via `lru_cache`).

---

## 🛡️ Security & Reliability

| Area | Implementation |
|------|---------------|
| **Rate Limiting** | `slowapi` — register: 5/min, login: 10/min, AI: 20/min, cover letter: 5/min, job fetch: 10/min |
| **CORS** | Restricted to known origins only (no wildcard `*`) |
| **Database RLS** | Row Level Security enabled on all tables (Alembic migration 001) — blocks direct PostgREST access |
| **JWT Security** | `PyJWT` (migrated from vulnerable `python-jose`); 24h expiry |
| **Password Policy** | Minimum 8 characters enforced at model level |
| **File Uploads** | 5 MB size limit, strict MIME type allowlist (PDF/DOCX/TXT), filename sanitization |
| **Security Headers** | `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `X-XSS-Protection` on every response |
| **API Docs** | Hidden in production (`PRODUCTION=true` env var) |
| **Input Validation** | JD ≤ 10,000 chars, resume name ≤ 100 chars enforced by Pydantic |
| **Error Monitoring** | Sentry SDK integrated — opt-in via `SENTRY_DSN` env var |
| **Migrations** | `alembic upgrade head` runs on every container start |
| **Email Enumeration** | Generic conflict message on duplicate registration |

---

## 🛠️ Tech Stack

| Layer | Technology |
|-------|-----------|
| **Backend API** | FastAPI 0.111, SQLModel, Alembic, Python 3.11 |
| **Database** | PostgreSQL via Supabase (permanent free tier) + Row Level Security |
| **AI / LLM** | Groq API (LLaMA 3.1 8B instant) — cloud; Ollama (local dev) |
| **Semantic NLP** | `sentence-transformers` — `all-MiniLM-L6-v2` for ATS semantic scoring |
| **RAG Pipeline** | LangChain · FAISS · nomic-embed-text embeddings |
| **PDF Generation** | `reportlab` — server-side, no headless browser needed |
| **Web Scraping** | `httpx` + `beautifulsoup4` — JSON-LD structured data extraction |
| **Frontend** | Streamlit |
| **Security** | PyJWT, passlib[bcrypt], slowapi, python-magic (MIME validation) |
| **Infrastructure** | Docker · Docker Compose · nginx |
| **CI/CD** | GitHub Actions → Render.com auto-deploy |

---

## 🚀 Quick Start (Local Development)

### Prerequisites
- Docker & Docker Compose
- Git

### 1. Clone
```bash
git clone https://github.com/deeason7/ai-career-hub.git
cd ai-career-hub
```

### 2. Configure environment
```bash
cp backend/.env.example backend/.env
# Edit backend/.env — minimum required:
#   POSTGRES_* (or let Docker use defaults)
#   GROQ_API_KEY=gsk_... (free at console.groq.com)
#   SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
```

### 3. Run
```bash
docker compose up --build
```

### 4. Open
| Service | URL |
|---------|-----|
| Frontend | http://localhost:8501 |
| API Swagger | http://localhost:8000/docs |

> **First run:** `sentence-transformers` downloads `all-MiniLM-L6-v2` (~80 MB) on first ATS score request. Subsequent requests are fast (model cached in memory).

---

## 🌿 Branch Strategy (GitFlow-Lite)

| Branch | Purpose | Merges to |
|--------|---------|-----------|
| `main` | Production — protected, auto-deploys | — |
| `develop` | Integration — all PRs merge here first | `main` (via release) |
| `feature/*` | New feature work | `develop` |
| `fix/*` | Bug fixes | `develop` |
| `hotfix/*` | Critical production fixes | `main` + `develop` |

```bash
git checkout develop && git pull origin develop
git checkout -b feature/my-feature
# ... work, commit ...
git push origin feature/my-feature
# Open PR: feature/my-feature → develop
```

---

## 🧪 Tests

```bash
# Start DB first
docker compose up db -d

# Run tests
docker exec -it ai-career-hub-api-1 pytest tests/ -v --tb=short
```

Tests cover: authentication, resume upload, ATS scoring (keyword + semantic), job tracker CRUD.

> Rate limiting is automatically disabled in CI via `TESTING=true` environment variable.

---

## 📦 Deployment

Deployed on [Render.com](https://render.com) with infrastructure-as-code via `render.yaml`.

| Service | Type | Plan |
|---------|------|------|
| `ai-career-hub-api` | Web Service (Docker) | Free |
| `ai-career-hub-frontend` | Web Service (Docker) | Free |
| PostgreSQL | Supabase | Free (permanent) |

**Required environment variables on Render:**
```
POSTGRES_SERVER, POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB, POSTGRES_PORT
REDIS_HOST, REDIS_PORT, REDIS_PASSWORD
SECRET_KEY
GROQ_API_KEY
PRODUCTION=true
SENTRY_DSN=      # optional — Sentry project DSN
```

---

## 🗺️ Roadmap

### ✅ v1.1 — Security & Reliability
- [x] File upload: 5 MB limit, MIME type allowlist, filename sanitization
- [x] Rate limiting on auth + AI endpoints (`slowapi`)
- [x] CORS restricted to known origins
- [x] Security headers on every response
- [x] JWT migrated to `PyJWT`
- [x] Row Level Security enabled on all DB tables
- [x] API docs hidden in production
- [x] Sentry error tracking integrated

### ✅ v1.2 — Features
- [x] Cover letter PDF export (`reportlab`)
- [x] LinkedIn / Greenhouse / Lever job URL → auto-fill job description
- [x] Application deadline field with urgency badges (🔴🟡🟠)
- [x] Legal disclaimer modal with "Never Show Again"
- [x] Semantic ATS scoring (`sentence-transformers`)

### 🔜 v1.3 — ML & Data Science
- [ ] Resume section classifier (spaCy NER)
- [ ] Application pipeline funnel chart (Plotly)
- [ ] Skill gap priority scorer (TF-IDF + co-occurrence ranking)
- [ ] Resume quality scorer (action verb density, readability score)
- [ ] Hybrid RAG: BM25 + Dense + Cross-encoder reranker

### 🔜 v2.0 — Scale
- [ ] Password reset via email (Resend.com)
- [ ] Cover letter tone selector (formal / casual / creative)
- [ ] Next.js frontend (replace Streamlit)
- [ ] Resume version history & diff viewer
- [ ] Stripe subscription tiers

---

## 🤝 Contributing

1. Fork → `git checkout -b feature/your-feature`
2. Commit: `git commit -m 'feat(scope): description'`
3. Push & open PR to `develop`

---

## 📄 License

MIT © 2026 [deeason7](https://github.com/deeason7)

---

## ⚠️ Disclaimer

> **This project is for educational and demonstration purposes only.**

The author makes no warranties — express or implied — about the completeness, reliability, accuracy, or suitability of this software or the AI-generated content it produces. Any action you take based on information or output from this platform is **strictly at your own risk**.

The author will **not** be liable for any losses, damages, or negative outcomes — financial, professional, or otherwise — arising from:

- Use or misuse of this software
- AI-generated cover letters, ATS scores, or interview questions that are inaccurate or unsuitable
- Reliance on this platform's output as professional career, legal, or financial advice
- Data loss or security incidents resulting from self-hosted deployments

**AI-generated content is not professional advice.** Always review and verify AI outputs before using them in real job applications.

---

## 🤖 AI Content Notice

This platform uses large language models (LLaMA 3.1 via Groq API) to generate content. The AI:

- May produce **inaccurate, incomplete, or hallucinated** information despite RAG safeguards
- Should **not** be used as a substitute for professional career counselling
- Generates outputs based on the resume and job description you provide — the author is **not responsible** for the content of your inputs or outputs

Always proofread AI-generated cover letters and questions before submitting to employers.

---

## 🔒 Privacy Notice

**Live Demo Deployment**

The live demo at `ai-career-hub-frontend.onrender.com` is hosted on third-party platforms:

| Platform | Role | Privacy Policy |
|----------|------|---------------|
| [Render.com](https://render.com) | Hosts API and frontend containers | [render.com/privacy](https://render.com/privacy) |
| [Supabase](https://supabase.com) | Hosts PostgreSQL database | [supabase.com/privacy](https://supabase.com/privacy) |
| [Groq](https://groq.com) | Processes AI inference requests | [groq.com/privacy-policy](https://groq.com/privacy-policy/) |

**What is stored:**
- Account email, hashed password (bcrypt), and full name
- Resume text content extracted from uploaded files (raw files are NOT stored)
- Cover letters, ATS scores, and job application records you create

**What is NOT stored:**
- Raw uploaded files (only extracted text is persisted)
- Payment information (no payments collected)
- Browser fingerprints, cookies beyond session, or tracking data

**Your rights:**
- Delete resumes and job tracker entries at any time from the UI
- To request full account deletion, open a GitHub issue

**Recommendations:**
- Do **not** upload resumes containing passport numbers, government IDs, or financial account details to the public demo
- For sensitive data, self-host using the Docker Compose setup — your data stays on your infrastructure
- The live demo is provided as-is with **no uptime or data retention guarantees**
