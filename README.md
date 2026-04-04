# 🚀 AI Career Hub

An AI-powered career acceleration platform built with a production-grade engineering stack.  
Upload your resume, score it semantically against job descriptions, generate honest cover letters, track applications with deadlines — all in one place.

[![CI](https://github.com/deeason7/ai-career-hub/actions/workflows/ci.yml/badge.svg)](https://github.com/deeason7/ai-career-hub/actions/workflows/ci.yml)
[![Deploy](https://github.com/deeason7/ai-career-hub/actions/workflows/deploy.yml/badge.svg)](https://github.com/deeason7/ai-career-hub/actions/workflows/deploy.yml)

## 🌐 Live

| Service | URL |
|---------|-----|
| **Frontend** | https://careerhub.deeason.com.np |
| **API (Swagger)** | https://careerhub.deeason.com.np/api/v1/docs *(dev only)* |
| **Health Check** | https://careerhub.deeason.com.np/health |

> Hosted on AWS EC2 (t3.micro) behind nginx. RDS PostgreSQL (free tier) in private VPC.

---

## ✨ Features

| Feature | Details |
|---------|---------|
| 👤 **Multi-Resume Management** | Upload, store, and switch between up to 10 resumes per user (PDF, DOCX, TXT — 5 MB max) |
| 🧠 **Semantic ATS Scorer** | `sentence-transformers` dense vector similarity + keyword matching + structure scoring — catches synonym matches keyword-only ATS systems miss |
| 📝 **AI Cover Letter Generator** | RAG-based generation using FAISS + LangChain — only uses facts from YOUR resume, no hallucinations |
| 📄 **PDF Export** | Download any generated cover letter as a professionally formatted PDF via `reportlab` |
| 🔗 **Job URL Import** | Paste a LinkedIn / Greenhouse / Lever / Workday URL to auto-fill the job description |
| 🔍 **Skill Gap Analysis** | Identify missing skills with AI-powered upskilling recommendations |
| 🎙️ **Interview Question Generator** | 10 tailored questions generated from your resume + job description |
| 📊 **Application Tracker** | Full pipeline tracking with deadline dates and colour-coded urgency badges (🔴🟡🟠) |
| ⚖️ **Legal Disclaimer** | Post-login disclaimer modal with "I Understand" + "Never Show Again" options |

---

## 🏗️ Architecture

```
                    GitHub Actions (CI)
                          │  lint + test on push to main/develop
                          ▼
              ┌───────────────────────┐
              │     AWS EC2 (t3.micro)│
              │                       │
              │  ┌─────────────────┐  │
              │  │  nginx (port 80)│  │
              │  └────────┬────────┘  │
              │           │           │
              │    ┌──────┴──────┐    │
              │    │             │    │
              │  ┌─▼──────┐  ┌──▼──┐ │
              │  │FastAPI │  │ ST  │ │
              │  │:8000   │  │:8501│ │
              │  └────┬───┘  └─────┘ │
              │       │ Redis:6379    │
              └───────┼───────────────┘
                      │
          ┌───────────▼────────────┐
          │  AWS RDS PostgreSQL    │
          │  (private VPC subnet)  │
          └────────────────────────┘
                      │ Groq API (cloud LLM)
                      ▼
              LLaMA 3.1 8B Instant
```

**Cover letter generation** runs as a FastAPI `BackgroundTask` — no separate Celery worker.  
**ATS scoring** uses sentence-transformers `all-MiniLM-L6-v2` (80 MB, CPU-only, singleton via `lru_cache`).  
**Secrets** are pulled from AWS SSM Parameter Store at deploy time via `infra/scripts/pull-secrets.sh`.

---

## 🛡️ Security & Reliability

| Area | Implementation |
|------|---------------|
| **Authentication** | JWT (`PyJWT`, HS256) — 24h expiry, `is_active` check on every request |
| **Token Validation** | Malformed `sub` claim → 401 (not 500) — `ValueError` caught before UUID parse |
| **Rate Limiting** | `slowapi` — register: 5/min · login: 10/min · AI: 20/min · cover letter: 5/min · job fetch: 10/min |
| **Password Policy** | Minimum 8 characters enforced at model level; `bcrypt` hashing |
| **CORS** | Restricted to known origins only — no wildcard `*` with credentials |
| **File Uploads** | 5 MB size limit · strict MIME type allowlist (PDF/DOCX/TXT) · filename sanitization |
| **Security Headers** | `X-Content-Type-Options` · `X-Frame-Options: DENY` · `Referrer-Policy` · `X-XSS-Protection` |
| **API Docs** | Hidden when `PRODUCTION=true` — no attack surface leakage |
| **Input Validation** | JD ≤ 10,000 chars · resume name ≤ 100 chars · enforced by Pydantic v2 |
| **Error Monitoring** | Sentry SDK integrated — opt-in via `SENTRY_DSN` |
| **LLM Failures** | 502 Bad Gateway returned (not raw 500) when Groq/Ollama are unavailable |
| **Production Startup** | `create_all()` skipped in production — Alembic owns the schema |

---

## 🛠️ Tech Stack

| Layer | Technology |
|-------|-----------|
| **Backend API** | FastAPI 0.111 · SQLModel · Alembic · Python 3.11 |
| **Database** | AWS RDS PostgreSQL 16 (private VPC) |
| **AI / LLM** | Groq API (LLaMA 3.1 8B instant) — cloud; Ollama (local dev fallback) |
| **Semantic NLP** | `sentence-transformers` — `all-MiniLM-L6-v2` for ATS semantic scoring |
| **RAG Pipeline** | LangChain · FAISS · `nomic-embed-text` embeddings |
| **PDF Generation** | `reportlab` — server-side, no headless browser |
| **Web Scraping** | `httpx.AsyncClient` + `beautifulsoup4` — JSON-LD first, meta/HTML fallback |
| **Frontend** | Streamlit |
| **Security** | PyJWT · passlib[bcrypt] · slowapi · python-magic (MIME validation) |
| **Infrastructure** | AWS EC2 · RDS · ECR · nginx · Docker Compose |
| **Observability** | Sentry · AWS CloudWatch (awslogs driver) |
| **CI** | GitHub Actions — ruff lint + pytest on push to `main`/`develop` |

---

## 🚀 Quick Start (Local Development)

### Prerequisites
- Docker & Docker Compose
- A free [Groq API key](https://console.groq.com)

### 1. Clone
```bash
git clone https://github.com/deeason7/ai-career-hub.git
cd ai-career-hub
```

### 2. Configure environment
```bash
cp backend/.env.example backend/.env
# Minimum required fields in backend/.env:
#   POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB
#   GROQ_API_KEY=gsk_...
#   SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
```

### 3. Start
```bash
docker compose up --build
```

### 4. Open

| Service | URL |
|---------|-----|
| Frontend | http://localhost:8501 |
| API Swagger | http://localhost:8000/docs |
| Health | http://localhost:8000/health |

> **First ATS run:** `sentence-transformers` downloads `all-MiniLM-L6-v2` (~80 MB) on the first request. Subsequent calls use the in-memory singleton.

---

## 🌿 Branch Strategy

| Branch | Purpose | Merges to |
|--------|---------|-----------|
| `main` | Production — protected | — |
| `develop` | Integration — all work lands here | `main` (via release PR) |
| `feat/*` | New features | `develop` |
| `fix/*` | Bug fixes | `develop` |
| `hotfix/*` | Critical production fixes | `main` + `develop` |

```bash
git checkout develop && git pull origin develop
git checkout -b feat/my-feature
# ... work, commit ...
git push origin feat/my-feature
# Open PR: feat/my-feature → develop
```

---

## 🧪 Tests

```bash
# Run inside the API container (no local Python needed)
docker exec -it ai-career-hub-api-1 pytest tests/ -v --tb=short

# Or with a local Python env
cd backend
POSTGRES_SERVER=localhost POSTGRES_USER=... pytest tests/ -v --tb=short
```

Tests cover: auth, resume upload, ATS scoring (keyword + semantic), job tracker CRUD.

> Rate limiting is automatically disabled in CI via `TESTING=true`.

---

## ☁️ Deployment (AWS EC2)

### Infrastructure
| Resource | Details |
|----------|---------|
| EC2 | `t3.micro` — Docker Compose stack |
| RDS | PostgreSQL 16 · `db.t3.micro` · private subnet |
| ECR | `REDACTED_ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com` |
| Secrets | AWS SSM Parameter Store → `.env.prod` |
| Logs | CloudWatch (`/portfolio/careerhub-*`) |

### Deploy workflow
```bash
# On your local machine — build & push images
export ECR_REGISTRY=REDACTED_ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin $ECR_REGISTRY
docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml push

# On EC2 — pull secrets & restart stack
bash infra/scripts/pull-secrets.sh          # writes .env.prod from SSM
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d --remove-orphans
docker image prune -f
```

### Required SSM Parameters
```
/careerhub/POSTGRES_SERVER
/careerhub/POSTGRES_USER
/careerhub/POSTGRES_PASSWORD
/careerhub/POSTGRES_DB
/careerhub/SECRET_KEY
/careerhub/GROQ_API_KEY
/careerhub/SENTRY_DSN       # optional
/careerhub/ALLOWED_ORIGINS
```

---

## 🗺️ Roadmap

### ✅ v1.x — Security & Features
- [x] File upload: 5 MB limit, MIME type allowlist, filename sanitization
- [x] Rate limiting on auth + AI endpoints
- [x] CORS restricted, security headers on every response
- [x] JWT migrated to `PyJWT`
- [x] Cover letter PDF export
- [x] LinkedIn / Greenhouse / Lever job URL auto-fill (async httpx)
- [x] Application deadline field with urgency badges
- [x] Semantic ATS scoring (`sentence-transformers`)
- [x] Legal disclaimer modal

### ✅ v2.0 — AWS Migration
- [x] Migrated from Render/Supabase → AWS EC2 + RDS
- [x] Celery replaced with FastAPI `BackgroundTasks`
- [x] Alembic migrations hardened with `IF NOT EXISTS`
- [x] UUID parse security fix (ValueError → 401)
- [x] LLM failure handling (502 instead of 500)
- [x] Async httpx replaces blocking sync client
- [x] O(N) stats + activate queries replaced with SQL COUNT/UPDATE
- [x] CloudWatch log driver on all containers

### 🔜 v2.1 — ML & Data Science
- [ ] Resume section classifier (spaCy NER)
- [ ] Application pipeline funnel chart (Plotly)
- [ ] Skill gap priority scorer (TF-IDF + co-occurrence ranking)
- [ ] Resume quality scorer (action verb density, readability)
- [ ] Hybrid RAG: BM25 + Dense + Cross-encoder reranker

### 🔜 v3.0 — Scale
- [ ] Next.js frontend (replace Streamlit)
- [ ] Password reset via email
- [ ] Cover letter tone selector (formal / casual / creative)
- [ ] Resume version history & diff viewer
- [ ] Automated CD via GitHub Actions → EC2 SSH

---

## 🤝 Contributing

1. Fork → `git checkout -b feat/your-feature`
2. Commit: `git commit -m 'feat(scope): description'`
3. Push & open PR to `develop`

---

## 📄 License

MIT © 2026 [deeason7](https://github.com/deeason7)

---

## ⚠️ Disclaimer

> **This project is for educational and demonstration purposes only.**

The author makes no warranties about the completeness, reliability, accuracy, or suitability of this software or the AI-generated content it produces. Any action you take based on output from this platform is **strictly at your own risk**.

The author will **not** be liable for losses, damages, or negative outcomes arising from use of this software, AI-generated content that is inaccurate, or data loss from self-hosted deployments.

**AI-generated content is not professional advice.** Always review and verify AI outputs before using them in real job applications.

---

## 🔒 Privacy Notice

**Live Deployment**

| Platform | Role | Privacy Policy |
|----------|------|---------------|
| [AWS EC2](https://aws.amazon.com) | Hosts containers | [aws.amazon.com/privacy](https://aws.amazon.com/privacy/) |
| [AWS RDS](https://aws.amazon.com/rds/) | PostgreSQL database | [aws.amazon.com/privacy](https://aws.amazon.com/privacy/) |
| [Groq](https://groq.com) | AI inference | [groq.com/privacy-policy](https://groq.com/privacy-policy/) |

**What is stored:**
- Account email, hashed password (bcrypt), and full name
- Resume text extracted from uploaded files (raw files are **not** stored)
- Cover letters, ATS scores, and job application records you create

**What is NOT stored:**
- Raw uploaded files — only extracted text is persisted
- Payment information — no payments collected
- Browser fingerprints, cookies beyond session, or tracking data

**Recommendations:**
- Do **not** upload resumes containing passport numbers, government IDs, or financial account details to the public demo
- For sensitive data, self-host using the Docker Compose setup — your data stays on your infrastructure
- The live demo is provided as-is with **no uptime or data retention guarantees**
