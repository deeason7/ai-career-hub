# 🚀 AI Career Hub

An AI-powered career acceleration platform built with a production-grade engineering stack.  
Upload your resume, score it semantically against job descriptions, generate honest cover letters, track applications with deadlines — all in one place.

[![CI](https://github.com/deeason7/ai-career-hub/actions/workflows/ci.yml/badge.svg)](https://github.com/deeason7/ai-career-hub/actions/workflows/ci.yml)
[![Deploy](https://github.com/deeason7/ai-career-hub/actions/workflows/deploy.yml/badge.svg)](https://github.com/deeason7/ai-career-hub/actions/workflows/deploy.yml)

## 🌐 Live

| Service | URL |
|---------|-----|
| **App** | https://careerhub.deeason.com.np |
| **Health Check** | https://careerhub.deeason.com.np/health |

> Hosted on AWS (EC2 t3.small + RDS PostgreSQL db.t3.micro, private VPC).  
> **Cost-optimised:** Runs on a hybrid schedule — instant access Mon–Fri 9 AM–6 PM ET (always-on for recruiters), Wake-on-Visit (90s cold boot on demand) outside business hours. [See how it works ↓](#️-cost-optimised-deployment)

---

## ✨ Features

| Feature | Details |
|---------|---------|
| 👤 **Multi-Resume Management** | Upload, store, and switch between up to 10 resumes per user (PDF, DOCX, TXT — 5 MB max) |
| 🧠 **Semantic ATS Scorer** | `sentence-transformers` dense vector similarity + keyword matching + structure scoring — catches synonym matches keyword-only ATS systems miss |
| 📝 **AI Cover Letter Generator** | RAG-based generation using FAISS + LangChain — only uses facts from YOUR resume, no hallucinations |
| 🛡️ **AI-as-a-Judge QA** | Second LLM pass scores every cover letter for honesty (1–10) and tone (1–10) — auto-regenerates up to 2× if honesty < 6 |
| 🔧 **Structured LLM Output** | All LLM calls return Pydantic v2-validated JSON via `instructor` — no regex parsing, deterministic contracts |
| 🔗 **n8n Workflow Orchestration** | Event-driven cover letter pipeline via n8n Cloud webhooks — graceful fallback to local `BackgroundTasks` |
| 📄 **PDF Export** | Download any generated cover letter as a professionally formatted PDF via `reportlab` |
| 🔗 **Job URL Import** | Paste a LinkedIn / Greenhouse / Lever / Workday URL to auto-fill the job description |
| 🔍 **Skill Gap Analysis** | Identify missing skills with AI-powered upskilling recommendations |
| 🎙️ **Interview Question Generator** | 10 tailored questions generated from your resume + job description |
| 📊 **Application Tracker** | Full pipeline tracking with deadline dates and colour-coded urgency badges (🔴🟡🟠) |
| ⚖️ **Legal Disclaimer** | Post-login disclaimer modal with "I Understand" + "Never Show Again" options |

---

## 🏗️ Architecture

```
  Recruiter visits careerhub.deeason.com.np
             │
             │  Route 53 health check
             ├─ EC2 healthy ──────────────────────────────────────────┐
             │                                                         │
             └─ EC2 sleeping → CloudFront → S3 wake page              │
                    │  (Lambda boots EC2 + RDS in ~90s, auto-redirects)│
                    │  (EventBridge auto-stops after 90 min of uptime) │
                    │                                                  │
                    └──────────────────────────────────────────────────┘
                                                                       │
                                         GitHub Actions (CI)           │
                                         ruff lint + pytest on push    │
                                               │                       ▼
                                   ┌───────────────────────┐
                                   │   AWS EC2 (t3.small)  │
                                   │  ┌─────────────────┐  │
                                   │  │  nginx (HTTPS)  │  │
                                   │  └────────┬────────┘  │
                                   │    ┌──────┴──────┐    │
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
                                           │ Groq API
                                           ▼
                                   LLaMA 3.1 8B Instant
```

**Cover letter generation** dispatches to n8n Cloud (event-driven webhook) when configured — falls back to local `BackgroundTasks` if n8n is unreachable.  
**AI QA review** runs a second LLM pass ("Reviewer" persona) scoring honesty and tone — auto-regenerates up to 2× if honesty < 6/10.  
**Structured output** via `instructor` + Pydantic v2 — all LLM responses are validated before persisting to DB.  
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
| **LLM Output Validation** | `instructor` enforces Pydantic v2 contracts on every LLM response — garbage output retries up to 3× before clean 502 |
| **n8n Webhook Auth** | Callback endpoint validates `X-Webhook-Secret` header — not JWT (internal service) |
| **Production Startup** | `create_all()` skipped in production — Alembic owns the schema |
| **IAM Least Privilege** | Custom least-privilege IAM policies — scoped to named project resources; no `RunInstances`, no wildcards |
| **MFA** | Enforced on root account (no access keys) and all developer IAM users |
| **EC2 IMDS** | IMDSv2 required — SSRF attacks cannot steal EC2 instance role credentials |
| **EC2 Role** | Read-only SSM parameter access; ECR pull-only; no S3, no KMS, no write permissions |
| **Secrets Rotation** | All secrets (DB, JWT, Groq, IAM keys) rotated and managed via AWS SSM Parameter Store |
| **Budget Kill Switch** | Lambda auto-stops EC2 + RDS when daily AWS spend exceeds $5 — zero run-away billing risk |
| **Audit Logs** | CloudTrail logging to private S3 bucket; CloudWatch 30-day retention on all container logs |
| **Cost Anomaly Detection** | AWS ML-based anomaly detector fires on statistically unusual spend patterns |

---

## 🛠️ Tech Stack

| Layer | Technology |
|-------|-----------|
| **Backend API** | FastAPI 0.111 · SQLModel · Alembic · Python 3.11 |
| **Database** | AWS RDS PostgreSQL 16 (private VPC, on-demand) |
| **Cache** | Redis 7 (Docker, local to EC2) |
| **AI / LLM** | Groq API (LLaMA 3.1 8B instant) — cloud; Ollama (local dev fallback) |
| **Structured Output** | `instructor` + Pydantic v2 — validated JSON contracts on all LLM responses |
| **AI QA** | AI-as-a-Judge reviewer persona — honesty/tone scoring with auto-regeneration |
| **Semantic NLP** | `sentence-transformers` — `all-MiniLM-L6-v2` for ATS semantic scoring |
| **RAG Pipeline** | LangChain · FAISS · `nomic-embed-text` embeddings |
| **Orchestration** | n8n Cloud (webhook-based, optional) — graceful fallback to local BackgroundTasks |
| **PDF Generation** | `reportlab` — server-side, no headless browser |
| **Web Scraping** | `httpx.AsyncClient` + `beautifulsoup4` — JSON-LD first, meta/HTML fallback |
| **Frontend** | Streamlit |
| **Security** | PyJWT · passlib[bcrypt] · slowapi · python-magic (MIME validation) |
| **Infrastructure** | AWS EC2 · RDS · ECR · nginx (Docker SSL) · Docker Compose |
| **Serverless** | AWS Lambda · API Gateway · S3 · CloudFront · Route 53 failover |
| **Scheduling** | EventBridge Scheduler — 90-min idle auto-stop + Mon–Fri 9 AM/6 PM ET business-hours start/stop |
| **Observability** | Sentry · AWS CloudWatch (awslogs driver) |
| **CI** | GitHub Actions — ruff lint + format check + pytest on push to `main`/`develop` |
| **CD** | GitHub Actions — Docker build → ECR push → EC2 deploy via SSM on push to `main` |
| **Code Quality** | ruff (lint + format, rules: E/F/W/I/B/UP) · pre-commit hooks (trailing whitespace, YAML/JSON check, large-file guard) |

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

### 5. Developer tooling (optional but recommended)

```bash
# Install dev dependencies (includes ruff, pytest, mypy, pre-commit)
pip install -r backend/requirements.dev.txt

# Install pre-commit hooks (runs ruff + hygiene checks before every commit)
pre-commit install

# Run linter manually
ruff check backend/        # check
ruff check --fix backend/  # auto-fix UP007, UP017, UP035
ruff format backend/       # format

# Run tests
cd backend && pytest tests/ -v --tb=short
```

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

Tests cover: auth, resume upload, ATS scoring (keyword + semantic), job tracker CRUD, LLM schema validation, instructor client integration, QA service review logic, n8n webhook callback.  
**37 total tests** (34 pass, 3 xfail — model-specific edge cases).

> Rate limiting is automatically disabled in CI via `TESTING=true`.

---

## ☁️ Cost-Optimised Deployment

The app uses a **hybrid scheduling model** to balance cost and recruiter experience:

| Mode | Schedule | Cost | UX |
|------|----------|------|----|
| **Always-On** | Mon–Fri 9 AM – 6 PM ET | ~$7.50/mo | Instant load — no wait |
| **Wake-on-Visit** | All other times | ~$0.50/mo extra | ~90s cold boot on demand |
| **Always-On (baseline)** | 24/7 | ~$27/mo | — |

```
careerhub.deeason.com.np
         │
         ├─ [EC2 up]   → Route 53 PRIMARY  → real app (no wait)
         └─ [EC2 down] → Route 53 FAILOVER → CloudFront → S3 wake page
                              └──→ Lambda starts EC2 + RDS
                                         └──→ auto-redirect in ~90s

Business Hours (EventBridge Scheduler, America/New_York):
  cron(0 9  ? * MON-FRI *)  →  action:wake  →  start EC2 + RDS
  cron(0 18 ? * MON-FRI *)  →  action:stop  →  stop  EC2 + RDS

Off-Hours:
  Visitor hits S3 wake page → Lambda /wake → EC2+RDS start → 90-min idle timer
```

### AWS Infrastructure
| Resource | Details |
|----------|---------|
| EC2 | `t3.small` (Ubuntu 24.04) — Docker Compose stack |
| RDS | PostgreSQL 16 · `db.t3.micro` · private subnet |
| ECR | `<ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com` |
| Secrets | AWS SSM Parameter Store → `.env.prod` |
| Logs | CloudWatch (`/portfolio/careerhub-*`) |
| Wake page | S3 static site → CloudFront (HTTPS) — always-on, ~$0/month |
| Wake API | API Gateway HTTP API + Lambda (`portfolio-wake-controller`) |
| Failover | Route 53 health check → failover routing (EC2 ↔ CloudFront) |
| Scheduler | EventBridge Scheduler: business-hours start/stop + 90-min idle auto-stop |

### Deploy workflow
```bash
# On your local machine — build & push images
export ECR_REGISTRY=$(aws sts get-caller-identity --query Account --output text).dkr.ecr.us-east-1.amazonaws.com
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin $ECR_REGISTRY
docker build --platform linux/amd64 -t $ECR_REGISTRY/careerhub-backend:latest ./backend
docker push $ECR_REGISTRY/careerhub-backend:latest

# On EC2 — connect then deploy
aws ssm start-session --target $INSTANCE_ID --region us-east-1
sudo su - ubuntu && cd ~/ai-career-hub
bash infra/scripts/deploy.sh
```

### Key infrastructure scripts
| Script | Purpose |
|--------|---------|
| `infra/scripts/start.sh` | Manually start EC2 + RDS + wait for health |
| `infra/scripts/stop.sh` | Manually stop EC2 + RDS |
| `infra/scripts/deploy.sh` | On-EC2 deploy: pull secrets + images + restart stack |
| `infra/scripts/setup-wake-on-visit.sh` | One-time Wake-on-Visit provisioning |
| `infra/scripts/setup-business-hours.sh` | Install/update business-hours recurring schedules |
| `infra/wake-page/wake_controller.py` | Lambda: routes `/wake`, `/status`, `action:stop`, `action:wake` |

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

### ✅ v2.0 — AWS Production Deployment
- [x] Migrated from Render/Supabase → AWS EC2 + RDS
- [x] Celery replaced with FastAPI `BackgroundTasks`
- [x] Alembic migrations hardened with `IF NOT EXISTS`
- [x] UUID parse security fix (ValueError → 401 from None)
- [x] LLM failure handling (502 instead of 500)
- [x] Async httpx replaces blocking sync client
- [x] O(N) stats + activate queries replaced with SQL COUNT/UPDATE
- [x] CloudWatch log driver on all containers + 30-day retention policy
- [x] Docker images built for `linux/amd64`, pushed to ECR (lifecycle: 3 images max)
- [x] Secrets in SSM Parameter Store — zero secrets in source code or git history
- [x] Full git history audit + credential rotation via `git-filter-repo`
- [x] AWS Budgets alerts (daily $5 + monthly $40) + ML cost anomaly detection
- [x] Stack live on EC2 — all Alembic migrations applied against RDS
- [x] Hardened IAM — least-privilege custom policies, MFA on root + developer user
- [x] IMDSv2 enforced on EC2 — eliminates SSRF-based credential theft vector
- [x] EC2 IAM role tightened — read-only SSM, no S3/KMS/write access
- [x] Budget kill switch — Lambda auto-stops EC2 + RDS at $5/day spend threshold
- [x] Wake on Visit — on-demand infrastructure (Route 53 failover → CloudFront → Lambda → EC2/RDS boot)

### ✅ v2.5 — Performance & Reliability
- [x] Lambda parallelized EC2+RDS status checks via `ThreadPoolExecutor` (~400ms vs ~1.3s)
- [x] gzip compression on nginx for JS/CSS/JSON assets (~50% smaller payloads)
- [x] `proxy_read_timeout` 300s — supports long-running Groq cover letter requests
- [x] Split `requirements.txt` / `requirements.dev.txt` — dev tools out of production image (~300MB saved)
- [x] Streamlit starts on `service_started` — ~10s earlier warm-up
- [x] Wake page: 45s DNS hard-redirect replaced with 90s poll + manual button fallback
- [x] Wake page: RDS `stopping → stopped` auto-rewake (re-triggers `/wake` automatically)
- [x] Wake page: `btn-pulse` CSS animation for DNS-stall CTA

### ✅ v2.6 — Business Hours Scheduler + Housekeeping
- [x] EventBridge Scheduler recurring rules: start 9 AM ET / stop 6 PM ET, Mon–Fri
- [x] `wake_controller.py` — `action:wake` routed to `handle_scheduled_wake()` (no idle timer set — 6 PM stop handles it)
- [x] `_start_all()` extracted — shared EC2+RDS start logic for HTTP /wake and scheduled wake
- [x] `setup-business-hours.sh` — idempotent install/update/remove of business-hours schedules
- [x] `.pre-commit-config.yaml` — ruff (lint + format) + trailing whitespace + YAML/JSON check + large-file guard
- [x] `backend/ruff.toml` — expanded to B (bugbear) + UP (pyupgrade) rules
- [x] CI: `ci.yml` installs `requirements.dev.txt` — ruff and pytest now available in GitHub Actions
- [x] All 59 ruff errors resolved (52 auto-fixed UP007/UP017/UP035, 7 B904 manually fixed)

### ✅ v3.0 — Structured Output & Orchestration
- [x] Structured LLM output via `instructor` + Pydantic v2 (6 typed schemas, validated contracts)
- [x] AI-as-a-Judge QA layer — honesty/tone scoring with auto-regeneration (up to 2× retries)
- [x] n8n Cloud workflow orchestration — event-driven webhooks with graceful fallback
- [x] Automated CD via GitHub Actions → ECR → EC2 SSM
- [x] 37 tests (34 pass, 3 xfail)

### 🔜 v3.1 — ML & Data Science
- [ ] Resume section classifier (spaCy NER)
- [ ] Application pipeline funnel chart (Plotly)
- [ ] Skill gap priority scorer (TF-IDF + co-occurrence ranking)
- [ ] Resume quality scorer (action verb density, readability)
- [ ] Hybrid RAG: BM25 + Dense + Cross-encoder reranker

### 🔜 v4.0 — Scale
- [ ] Next.js frontend (replace Streamlit)
- [ ] Password reset via email
- [ ] Cover letter tone selector (formal / casual / creative)
- [ ] Resume version history & diff viewer

---

## 🤝 Contributing

1. Fork → `git checkout -b feat/your-feature`
2. Install hooks: `pre-commit install`
3. Commit: `git commit -m 'feat(scope): description'`
4. Push & open PR to `develop`

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
