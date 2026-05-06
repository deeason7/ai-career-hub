# AI Career Hub

An AI-powered career acceleration platform built with a production-grade engineering stack.
Upload your resume, score it against job descriptions, generate honest cover letters, and track your applications — all in one place.

[![Pipeline](https://github.com/deeason7/ai-career-hub/actions/workflows/pipeline.yml/badge.svg)](https://github.com/deeason7/ai-career-hub/actions/workflows/pipeline.yml)

---

## Live Deployment

| Service | URL |
|---|---|
| **Application** | https://careerhub.deeason.com.np |
| **Health** | https://careerhub.deeason.com.np/health |

> Hosted on AWS (EC2 t3.small + RDS PostgreSQL db.t3.micro, private VPC).
> **Cost-optimised:** Always-on Mon–Fri 9 AM–6 PM ET for recruiter access. Wake-on-Visit (~90s cold start) outside business hours.

---

## Features

| Feature | Description |
|---|---|
| **Multi-Resume Management** | Upload, store, and switch between up to 10 resumes per user (PDF, DOCX, TXT — 5 MB max) |
| **Semantic ATS Scorer** | `sentence-transformers` dense vector similarity + keyword matching + structure heuristics — catches synonym matches that keyword-only ATS systems miss |
| **AI Cover Letter Generator** | Structured LLM generation grounded strictly in resume facts — no hallucinations |
| **AI-as-a-Judge QA** | Second LLM pass scores every cover letter for honesty (1–10) and tone (1–10) — auto-regenerates up to 2× if honesty score falls below threshold |
| **Structured LLM Output** | All LLM responses return Pydantic v2-validated JSON via `instructor` — no regex parsing, deterministic contracts |
| **Workflow Orchestration** | Event-driven cover letter pipeline via n8n Cloud webhooks — graceful fallback to local `BackgroundTasks` |
| **PDF Export** | Download generated cover letters as professionally formatted PDFs |
| **Job URL Import** | Auto-fill job description from any LinkedIn, Greenhouse, Lever, or Workday URL |
| **Skill Gap Analysis** | Identify missing skills with AI-powered upskilling recommendations |
| **Interview Question Generator** | 10 tailored questions generated from your resume and the job description |
| **Application Tracker** | Full pipeline tracking with deadline management and urgency indicators |

---

## Architecture

```
  User → careerhub.deeason.com.np
           │
           │  Route 53 health check
           ├─ EC2 healthy ─────────────────────────────────────┐
           │                                                    │
           └─ EC2 sleeping → CloudFront → S3 wake page         │
                  │  (Lambda boots EC2 + RDS in ~90s)          │
                  └────────────────────────────────────────────┘
                                                               │
                                   GitHub Actions (CI + CD)    │
                                   Lint + test + build + push  │
                                   main → ECR → SSM deploy     │
                                         │                     ▼
                             ┌───────────────────────┐
                             │   AWS EC2 (t3.small)  │
                             │  ┌─────────────────┐  │
                             │  │  nginx (HTTPS)  │  │
                             │  └────────┬────────┘  │
                             │    ┌──────┴──────┐    │
                             │  ┌─▼──────┐  ┌──▼──┐ │
                             │  │FastAPI │  │  ST │ │
                             │  │ :8000  │  │:8501│ │
                             │  └────┬───┘  └─────┘ │
                             │    Redis :6379        │
                             └───────┼───────────────┘
                                     │
                         ┌───────────▼────────────┐
                         │  AWS RDS PostgreSQL 16 │
                         │  (private VPC subnet)  │
                         └────────────────────────┘
                                     │ Groq API
                                     ▼
                             LLaMA 3.1 8B Instant
```

**Cover letter generation** dispatches to n8n Cloud when configured — falls back to `BackgroundTasks`.
**QA review** runs a second LLM pass scoring honesty and tone — auto-regenerates if below threshold.
**Structured output** via `instructor` + Pydantic v2 — all LLM responses validated before persisting.
**ATS scoring** uses `sentence-transformers` `all-MiniLM-L6-v2` (80 MB, CPU, cached via `lru_cache`).
**Secrets** pulled from AWS SSM Parameter Store at deploy time. Zero secrets in source code or git history.
**Deployments** are fully automated — push to `main` triggers GitHub Actions to build ECR images and deploy to EC2 via SSM.

---

## Security & Reliability

| Area | Implementation |
|---|---|
| **Authentication** | JWT (PyJWT, HS256) with `is_active` check on every protected request |
| **Session Management** | Short-lived access tokens + HttpOnly refresh cookie — inaccessible to JavaScript |
| **Rate Limiting** | `slowapi` — registration: 5/min · login: 10/min · AI endpoints: 20/min · cover letters: 5/min |
| **Password Hashing** | `bcrypt` — minimum 8 characters enforced at model level |
| **CORS** | Restricted to known origins — no wildcard `*` with credentials |
| **File Uploads** | 5 MB limit · MIME type allowlist (PDF/DOCX/TXT) · filename sanitisation |
| **Security Headers** | `X-Content-Type-Options` · `X-Frame-Options: DENY` · `Referrer-Policy` · `Permissions-Policy` |
| **HSTS** | Enabled in production — 1-year max-age, includeSubDomains |
| **API Documentation** | Hidden when `PRODUCTION=true` |
| **Input Validation** | All request payloads validated by Pydantic v2 — field-level length constraints |
| **Error Monitoring** | Sentry SDK with PII disabled (`send_default_pii=False`) |
| **LLM Output Validation** | `instructor` enforces Pydantic v2 contracts — retries up to 3× on validation failure |
| **Webhook Auth** | n8n callback endpoint authenticated via shared secret header |
| **IAM Least Privilege** | Custom scoped policies — no wildcards, no unused permissions |
| **EC2 IMDS** | IMDSv2 required — instance metadata not accessible via SSRF |
| **Secrets Management** | AWS SSM Parameter Store — SecureString for all sensitive values |
| **Audit Logs** | CloudWatch 30-day retention on all container logs |
| **Cost Controls** | Daily budget alerting + Lambda auto-stop at spend threshold |
| **Dependency Scanning** | Dependabot configured for weekly pip + monthly GitHub Actions updates |

---

## Tech Stack

| Layer | Technology |
|---|---|
| **Backend API** | FastAPI · SQLModel · Alembic · Python 3.11 |
| **Database** | AWS RDS PostgreSQL 16 (private VPC) |
| **Cache / Rate Limiting** | Redis 7 (Docker, local to EC2) |
| **AI / LLM** | Groq API (LLaMA 3.1 8B Instant) — cloud; Ollama (local dev) |
| **Structured Output** | `instructor` + Pydantic v2 |
| **AI QA** | AI-as-a-Judge reviewer — honesty/tone scoring with auto-regeneration |
| **Semantic NLP** | `sentence-transformers` — `all-MiniLM-L6-v2` |
| **RAG Pipeline** | LangChain · FAISS · Ollama embeddings (local dev path) |
| **Orchestration** | n8n Cloud (optional webhook-based) — fallback to `BackgroundTasks` |
| **PDF Generation** | `reportlab` — server-side, no headless browser |
| **Web Scraping** | `httpx.AsyncClient` + `beautifulsoup4` |
| **Frontend** | Streamlit |
| **Infrastructure** | AWS EC2 · RDS · ECR · Nginx · Docker Compose |
| **Serverless** | AWS Lambda · API Gateway · S3 · CloudFront · Route 53 failover |
| **Scheduling** | EventBridge Scheduler — business-hours start/stop + 90-min idle auto-stop |
| **Observability** | Sentry · AWS CloudWatch (awslogs driver on all containers) |
| **CI/CD** | GitHub Actions — lint + test + build + ECR push + SSM deploy |
| **Code Quality** | ruff (E/F/W/I/B/UP rules) · pre-commit hooks |

---

## Quick Start (Local Development)

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
# Edit backend/.env — minimum required fields:
#   POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB
#   GROQ_API_KEY=gsk_...
#   SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
```

### 3. Start

```bash
docker compose up --build
```

### 4. Access

| Service | URL |
|---|---|
| Frontend | http://localhost:8501 |
| API (Swagger) | http://localhost:8000/docs |
| Health | http://localhost:8000/health |

> **First ATS run:** `sentence-transformers` downloads `all-MiniLM-L6-v2` (~80 MB) on the first request. Subsequent calls use the in-memory singleton — no repeated downloads.

### 5. Developer tooling

```bash
# Install dev dependencies
pip install -r backend/requirements.dev.txt

# Install pre-commit hooks
pre-commit install

# Lint and format
ruff check backend/
ruff format backend/

# Run tests
cd backend && pytest tests/ -v --tb=short
```

---

## Branch Strategy

| Branch | Purpose | Merges to |
|---|---|---|
| `main` | Production — protected | — |
| `develop` | Integration — all work lands here first | `main` via release PR |
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

## Testing

```bash
# Inside the API container
docker exec -it ai-career-hub-api-1 pytest tests/ -v --tb=short

# With a local Python env
cd backend && pytest tests/ -v --tb=short
```

Test coverage: auth, resume upload, ATS scoring, job tracker CRUD, LLM schema validation, instructor client, QA service review logic, n8n webhook callback.

> Rate limiting is automatically disabled in CI via `TESTING=true`.

---

## Cost-Optimised Deployment

| Mode | Schedule | Estimated cost | UX |
|---|---|---|---|
| **Always-On** | Mon–Fri 9 AM–6 PM ET | ~$7.50/mo | Instant load |
| **Wake-on-Visit** | All other times | ~$0.50/mo extra | ~90s cold start |
| **Always-On 24/7** (baseline) | — | ~$27/mo | — |

```
careerhub.deeason.com.np
         │
         ├─ [EC2 up]   → Route 53 PRIMARY  → app (instant)
         └─ [EC2 down] → Route 53 FAILOVER → CloudFront → S3 wake page
                              └──→ Lambda starts EC2 + RDS (~90s)
                                         └──→ auto-redirect to live app

Business Hours (EventBridge, America/New_York):
  cron(0 9  ? * MON-FRI *)  →  start EC2 + RDS
  cron(0 18 ? * MON-FRI *)  →  stop  EC2 + RDS

Off-Hours:
  Visitor hits wake page → Lambda /wake → EC2+RDS start → 90-min idle timer
```

---

## Release History

### v3.0 — Structured Output & Orchestration
- Structured LLM output via `instructor` + Pydantic v2 (typed schemas, validated contracts)
- AI-as-a-Judge QA layer — honesty/tone scoring with auto-regeneration (up to 2× retries)
- n8n Cloud workflow orchestration — event-driven webhooks with graceful fallback
- Automated CD: GitHub Actions → ECR → EC2 SSM

### v2.6 — Business Hours Scheduler
- EventBridge Scheduler: start 9 AM / stop 6 PM ET, Mon–Fri
- Pre-commit hooks: ruff lint+format + file hygiene
- CI: ruff check + format + pytest in GitHub Actions

### v2.5 — Performance & Reliability
- Lambda EC2+RDS status checks parallelised (~400ms vs ~1.3s)
- gzip compression on nginx for JS/CSS/JSON
- Streamlit starts on `service_started` — earlier warm-up
- Wake page: DNS poll + manual button fallback

### v2.0 — AWS Production Deployment
- Migrated from Render/Supabase to AWS EC2 + RDS
- Celery replaced with FastAPI `BackgroundTasks`
- Secrets managed via AWS SSM Parameter Store
- Wake-on-Visit infrastructure (Route 53 failover → CloudFront → Lambda)
- Hardened IAM — least-privilege policies, MFA, IMDSv2

---

## Contributing

1. Fork → `git checkout -b feat/your-feature`
2. Install hooks: `pre-commit install`
3. Follow conventional commits: `feat(scope): description`
4. Open PR to `develop`

---

## License

MIT © 2026 [deeason7](https://github.com/deeason7)

---

## Disclaimer

> This project is for educational and portfolio demonstration purposes.

AI-generated content is not professional career advice. Always review outputs before use in real applications. The author makes no warranties regarding accuracy, reliability, or fitness for any purpose. Use at your own discretion.

---

## Privacy Notice

| Platform | Role | Privacy Policy |
|---|---|---|
| AWS EC2 / RDS | Compute and database | [aws.amazon.com/privacy](https://aws.amazon.com/privacy/) |
| Groq | AI inference | [groq.com/privacy-policy](https://groq.com/privacy-policy/) |

**What is stored:** Account email (hashed password), full name, extracted resume text, cover letters, ATS scores, application records.

**What is not stored:** Raw uploaded files · payment information · tracking data beyond session cookies.

> Do not upload documents containing government IDs, financial account numbers, or other high-sensitivity personal data to the public demo. For sensitive data, self-host using the Docker Compose setup.
