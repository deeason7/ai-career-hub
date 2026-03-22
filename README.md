# 🚀 AI Career Hub

An AI-powered career acceleration platform built with a production-grade engineering stack.
Upload your resume, score it against job descriptions, generate honest cover letters, identify skill gaps, and track applications — all in one place.

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
| 👤 **Multi-Resume Management** | Upload, store, and switch between up to 10 resumes per user |
| 📝 **AI Cover Letter Generator** | RAG-based zero-hallucination generation — only uses facts from your actual resume |
| 🎯 **ATS Score Analyzer** | Instant keyword & structural scoring against any job description |
| 🔍 **Skill Gap Analysis** | Identify missing skills and get AI-powered upskilling recommendations |
| 🎙️ **Interview Question Generator** | 10 tailored questions generated from your resume + job description |
| 📊 **Application Tracker** | Full pipeline tracking: wishlist → applied → interview → offer |

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
│  │  (permanent)   │   └─────────────────────┘  │
│  └────────────────┘                             │
└─────────────────────────────────────────────────┘
```

**Cover letter generation** runs as a FastAPI BackgroundTask (thread) inside the API process — no separate Celery worker service needed.

---

## 🛡️ Security & Reliability

| Area | Implementation |
|------|---------------|
| **Rate Limiting** | `slowapi` — register: 5/min, login: 10/min, AI endpoints: 20/min, cover letter: 5/min |
| **CORS** | Restricted to known origins only (no wildcard `*`) |
| **Password Policy** | Minimum 8 characters enforced at model level |
| **API Docs** | Hidden in production (`PRODUCTION=true` env var) |
| **File Uploads** | 10 MB size limit, 10-resume cap per user |
| **Email Enumeration** | Generic conflict message on duplicate registration |
| **Frontend Resilience** | All API calls wrapped in `safe_json()` — graceful errors on 429/502/503 |
| **Migrations** | `alembic upgrade head` runs on every container start |

---

## 🛠️ Tech Stack

| Layer | Technology |
|-------|-----------|
| **Backend API** | FastAPI, SQLModel, Alembic, Python 3.11 |
| **Database** | PostgreSQL (Supabase — permanent free tier) |
| **AI / LLM** | Groq API (LLaMA 3.1 8B) — cloud; Ollama (local dev) |
| **RAG** | LangChain · FAISS · nomic-embed-text embeddings |
| **Frontend** | Streamlit |
| **Rate Limiting** | slowapi (per-IP, in-memory) |
| **Async Tasks** | FastAPI BackgroundTasks (threads) |
| **Infrastructure** | Docker · Docker Compose |
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
#   SECRET_KEY=any_32char_string
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
# Day-to-day workflow
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

Tests cover: authentication, resume upload, ATS scoring, job tracker CRUD.

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
```

---

## 🗺️ Roadmap

### v1.1 — Security & Reliability (Done)
- [x] Resume file size limit (10 MB) & 10-resume cap
- [x] Rate limiting on auth + AI endpoints (`slowapi`)
- [x] Frontend error boundaries — graceful errors on all API failures
- [x] CORS restricted to known origins
- [x] Password minimum length (8 chars)
- [x] API docs hidden in production
- [x] Email enumeration prevention

### v1.2 — Features
- [ ] Password reset via email (SendGrid/Resend)
- [ ] Cover letter export to PDF (`weasyprint`)
- [ ] LinkedIn job URL → auto-fill job description
- [ ] Application deadline reminders
- [ ] Sentry.io error tracking

### v2.0 — Scale
- [ ] Next.js frontend (replace Streamlit)
- [ ] Resume version history & diff viewer
- [ ] Stripe subscription tiers
- [ ] Browser extension for one-click apply

---

## 🤝 Contributing

1. Fork → `git checkout -b feature/your-feature`
2. Commit: `git commit -m 'feat(scope): description'`
3. Push & open PR to `develop`

---

## 📄 License

MIT © 2026 [deeason7](https://github.com/deeason7)
