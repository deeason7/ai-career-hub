# AI Career Hub — Engineering Plan
## GitHub Workflow · Cloud Deployment · Technical Roadmap

---

## Part 1 — GitHub: Professional Workflow from Zero to Production

### 1.1 One-Time Repository Setup

#### Create the remote repo
1. Go to [github.com/new](https://github.com/new)
2. Name: **`ai-career-hub`** · Visibility: **Public** · Do NOT init with README
3. Click **Create repository**

#### Link local repo and push all branches
```bash
cd /Users/deeasonsitaula/Documents/Programming/Final/ai-career-hub

git remote add origin https://github.com/YOUR_USERNAME/ai-career-hub.git

# Push all existing branches
git push -u origin main
git push origin develop
git push origin feature/multi-resume-management
git push origin feature/ats-scorer
git push origin feature/job-tracker
```

#### Add a CI badge to README.md
In [README.md](file:///Users/deeasonsitaula/Documents/Programming/Final/ai-career-hub/README.md), replace `YOUR_USERNAME`:
```markdown
[![CI](https://github.com/YOUR_USERNAME/ai-career-hub/actions/workflows/ci.yml/badge.svg)](https://github.com/YOUR_USERNAME/ai-career-hub/actions)
```

---

### 1.2 Branch Architecture (GitFlow-Lite)

```
main           ──── Production. Auto-deploys on merge. NEVER push directly.
  └── develop  ──── Integration branch. All features merge here first.
        ├── feature/multi-resume-management    ← isolated feature work
        ├── feature/ats-scorer
        ├── feature/job-tracker
        ├── bugfix/fix-session-execute          ← hotfix isolated from features
        └── release/v1.0.0                     ← release candidate branch
```

| Branch | Purpose | Merge target | Who pushes |
|--------|---------|--------------|------------|
| `main` | Production-ready code | — | GitHub Actions only (via PR) |
| `develop` | Latest integrated work | `main` (via release) | PR from feature/* |
| `feature/*` | One feature per branch | `develop` | You (via PR) |
| `bugfix/*` | Bug fixes | `develop` or `main` | You (via PR) |
| `release/v*` | Release preparation | `main` + `develop` | You (via PR) |
| `hotfix/*` | Critical production fix | `main` + `develop` | You (via PR) |

---

### 1.3 Branch Protection Rules (Senior Git Practice)

Go to: **Repo → Settings → Branches → Add rule**

#### Rule 1: Protect `main`
- Pattern: `main`
- ✅ Require pull request before merging (1 approval minimum)
- ✅ Require status checks to pass → add `backend-ci`
- ✅ Require branches to be up to date before merging
- ✅ Restrict who can push → only yourself
- ✅ Do not allow bypassing the above settings

#### Rule 2: Protect `develop`
- Pattern: `develop`
- ✅ Require pull request before merging
- ✅ Require status checks to pass → add `backend-ci`

---

### 1.4 Day-to-Day Feature Development Workflow

This is exactly how a senior developer operates on a team:

```bash
# ── Step 1: Always start from develop, always pull latest ──────────────────
git checkout develop
git pull origin develop

# ── Step 2: Create a focused feature branch ────────────────────────────────
git checkout -b feature/cover-letter-history-export
# Branch name convention: feature/<verb>-<noun>
# Other examples:
#   bugfix/fix-celery-retry-logic
#   chore/update-dependencies
#   docs/add-api-documentation

# ── Step 3: Work in small, atomic commits ──────────────────────────────────
git add backend/app/api/v1/endpoints/cover_letters.py
git commit -m "feat(cover-letters): add CSV export endpoint"
# Commit message convention (Conventional Commits):
#   feat:     new feature
#   fix:      bug fix
#   chore:    non-code change (deps, config)
#   docs:     documentation
#   test:     adding/fixing tests
#   refactor: code change without new feature or fix

git add backend/tests/test_cover_letters.py
git commit -m "test(cover-letters): add CSV export integration test"

# ── Step 4: Push the feature branch ────────────────────────────────────────
git push origin feature/cover-letter-history-export

# ── Step 5: Open a Pull Request on GitHub ──────────────────────────────────
# GitHub → Pull requests → New pull request
# Base: develop  ←  Compare: feature/cover-letter-history-export
#
# PR Title: feat(cover-letters): CSV export for cover letter history
# PR Description:
#   ## Summary
#   Adds a GET /cover-letters/export endpoint that returns all cover
#   letters as a downloadable CSV.
#
#   ## Changes
#   - Added /export endpoint in cover_letters.py
#   - Added 3 integration tests
#
#   ## How to Test
#   1. Register, upload resume, generate a cover letter
#   2. Call GET /api/v1/cover-letters/export
#   3. Verify CSV download

# ── Step 6: CI runs automatically ──────────────────────────────────────────
# GitHub Actions ci.yml runs: lint (ruff) + all pytest tests
# ✅ All checks pass → request merge

# ── Step 7: Merge (squash merge preferred for clean history) ───────────────
# On GitHub: Squash and merge → delete feature branch after merge
```

---

### 1.5 Release Workflow (Shipping to Production)

```bash
# When develop has enough features for a release:

# Step 1 — Create release branch from develop
git checkout develop
git pull origin develop
git checkout -b release/v1.1.0

# Step 2 — Bump version (in README, package metadata)
# Only bugfixes allowed on this branch — no new features

# Step 3 — Open PR: release/v1.1.0 → main
# PR triggers CI; once merged → GitHub Actions auto-deploys to Render

# Step 4 — Tag the release
git checkout main
git pull origin main
git tag -a v1.1.0 -m "Release v1.1.0: cover letter export, ATS improvements"
git push origin v1.1.0

# Step 5 — Merge release back into develop (pick up release fixes)
git checkout develop
git merge main
git push origin develop
```

---

### 1.6 GitHub Secrets Required for CI/CD

**Repo → Settings → Secrets and variables → Actions → New secret**

| Secret | Value | Used by |
|--------|-------|---------|
| `DOCKERHUB_USERNAME` | Your Docker Hub username | [deploy.yml](file:///Users/deeasonsitaula/Documents/Programming/Final/career-ai-platform/.github/workflows/deploy.yml) |
| `DOCKERHUB_TOKEN` | Docker Hub access token | [deploy.yml](file:///Users/deeasonsitaula/Documents/Programming/Final/career-ai-platform/.github/workflows/deploy.yml) |
| `RENDER_DEPLOY_HOOK_API` | Render webhook URL for backend | [deploy.yml](file:///Users/deeasonsitaula/Documents/Programming/Final/career-ai-platform/.github/workflows/deploy.yml) |
| `RENDER_DEPLOY_HOOK_FRONTEND` | Render webhook URL for frontend | [deploy.yml](file:///Users/deeasonsitaula/Documents/Programming/Final/career-ai-platform/.github/workflows/deploy.yml) |

> **Getting Docker Hub Token:** hub.docker.com → Account Settings → Security → New Access Token

---

## Part 2 — Cloud Deployment Architecture

### 2.1 Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    GitHub (Source of Truth)                     │
│  main branch ──► GitHub Actions CI/CD ──► Render.com deploy    │
└─────────────────────────────────────────────────────────────────┘
                                │
                ┌───────────────┼───────────────┐
                ▼               ▼               ▼
         ┌────────────┐  ┌──────────────┐  ┌──────────┐
         │  Render    │  │   Render     │  │  Render  │
         │ Web Service│  │  PostgreSQL  │  │   Redis  │
         │ (FastAPI)  │  │  (Database)  │  │ (Queue)  │
         └────────────┘  └──────────────┘  └──────────┘
                │
         ┌──────┴────────┐
         │   Render      │
         │ Web Service   │
         │ (Streamlit)   │
         └───────────────┘
```

> **Note on Ollama:** Ollama (local LLM) cannot run on Render's free tier due to memory constraints. See Section 2.4 for the AI backend strategy on cloud.

---

### 2.2 Step-by-Step Render.com Deployment

#### Step 1 — Sign up
[render.com](https://render.com) → **Sign up with GitHub** → authorize the `ai-career-hub` repo.

#### Step 2 — Create PostgreSQL Database
Dashboard → **New → PostgreSQL**
```
Name:    ai-career-hub-db
Region:  Ohio (us-east-1)
Plan:    Free (expires 30 days) or Starter ($7/mo) for permanent
```
After creation, copy:
- **Internal Database URL** (format: `postgresql://user:pass@host:5432/db`)

#### Step 3 — Create Redis (Key Value)
Dashboard → **New → Key Value**
```
Name:    ai-career-hub-redis
Plan:    Free
```
Copy the **Internal Redis URL**.

#### Step 4 — Deploy the Backend (FastAPI)
Dashboard → **New → Web Service**
```
Source:         GitHub → ai-career-hub
Root Directory: backend
Runtime:        Docker
Plan:           Free (512MB RAM, spins down after 15min inactivity)
```

Environment Variables to set:
```
POSTGRES_SERVER=    ← hostname from DB URL
POSTGRES_USER=      ← user from DB URL
POSTGRES_PASSWORD=  ← password from DB URL
POSTGRES_DB=        ← database name from DB URL
POSTGRES_PORT=      5432
REDIS_HOST=         ← host from Redis URL
REDIS_PORT=         6379
SECRET_KEY=         ← python3 -c "import secrets; print(secrets.token_hex(32))"
ACCESS_TOKEN_EXPIRE_MINUTES= 1440
OLLAMA_BASE_URL=    (leave blank or use OpenAI — see Section 2.4)
```

After deploy: **Settings → Deploy Hooks → copy URL** → save as GitHub secret `RENDER_DEPLOY_HOOK_API`

#### Step 5 — Deploy the Frontend (Streamlit)
Same as backend but:
```
Root Directory: frontend
```
Additional env var:
```
API_URL=https://YOUR-BACKEND-NAME.onrender.com/api/v1
```
Copy deploy hook → save as `RENDER_DEPLOY_HOOK_FRONTEND`

#### Step 6 — Verify end-to-end
1. Visit `https://YOUR-FRONTEND.onrender.com`
2. Register an account
3. Check `https://YOUR-BACKEND.onrender.com/health`
4. Check `https://YOUR-BACKEND.onrender.com/docs`

---

### 2.3 CI/CD Pipeline Flow

```
Developer pushes to any branch
         │
         ▼
  GitHub Actions ci.yml
  ┌────────────────────┐
  │ 1. Checkout code   │
  │ 2. Python 3.11     │
  │ 3. Install deps    │
  │ 4. ruff lint       │  ◄── fails fast on style errors
  │ 5. pytest tests    │  ◄── uses real Postgres + Redis service containers
  └────────┬───────────┘
           │ (only on merge to main)
           ▼
  GitHub Actions deploy.yml
  ┌────────────────────────┐
  │ 1. Build backend img   │
  │ 2. Push to Docker Hub  │
  │ 3. Build frontend img  │
  │ 4. Push to Docker Hub  │
  │ 5. curl Render API hook │  ◄── triggers rolling deploy
  │ 6. curl Render FE hook  │
  └────────────────────────┘
           │
           ▼
  Render.com pulls new image
  Zero-downtime rolling deploy
```

---

### 2.4 AI Backend Strategy for Cloud (Solving the Ollama Problem)

Ollama requires 4–8 GB RAM — not available on cloud free tiers. Options:

| Option | Cost | Effort | Quality |
|--------|------|--------|---------|
| **OpenAI API (GPT-4o-mini)** | ~$0.001/call | Low — swap 3 lines | Best |
| **Groq API (Llama 3 hosted)** | Free tier (6000 req/day) | Low | Excellent |
| **Hugging Face Inference API** | Free tier | Medium | Good |
| **Keep Ollama locally** | Free | Zero | Good for dev |

**Recommended approach:** Add `OPENAI_API_KEY` env var. If set, use OpenAI. If not, fallback to Ollama. This means local dev uses Ollama, production uses OpenAI.

```python
# In cover_letter.py / resume_parser.py — already structured for this:
if settings.OPENAI_API_KEY:
    llm = ChatOpenAI(model="gpt-4o-mini", api_key=settings.OPENAI_API_KEY)
else:
    llm = Ollama(model=settings.OLLAMA_LLM_MODEL, base_url=settings.OLLAMA_BASE_URL)
```

---

## Part 3 — Gap Analysis & Future Roadmap

### 3.1 Current Gaps (Known Issues to Fix)

| Priority | Gap | Impact | Fix |
|----------|-----|--------|-----|
| 🔴 **P0** | No Alembic migrations — tables created via `create_all` | Production DB won't survive schema changes | Set up `alembic init`, write migration files |
| 🔴 **P0** | No database table creation on deploy (Render) | App crashes on first start against empty DB | Add `alembic upgrade head` to Render startup command |
| 🔴 **P0** | Ollama not available on cloud | All AI features broken on Render | Add OpenAI/Groq API fallback |
| 🟠 **P1** | No email verification on register | Anyone can register with fake emails | Add SendGrid/Resend email flow |
| 🟠 **P1** | No rate limiting | API can be abused | Add `slowapi` middleware |
| 🟠 **P1** | No file size validation on resume upload | Users can upload 1GB files | Add 10MB limit in [file_extractor.py](file:///Users/deeasonsitaula/Documents/Programming/Final/career-ai-platform/backend/app/services/file_extractor.py) |
| 🟡 **P2** | [frontend/app.py](file:///Users/deeasonsitaula/Documents/Programming/Final/career-ai-platform/frontend/app.py) error handling calls `resp.json()` without try/catch | Crashes on non-JSON API errors | Wrap in `try/except` |
| 🟡 **P2** | Tests in [test_api.py](file:///Users/deeasonsitaula/Documents/Programming/Final/career-ai-platform/backend/tests/test_api.py) require live PostgreSQL | Can't run in lightweight CI without DB | Add fixtures using SQLite for unit tests |
| 🟡 **P2** | Celery worker has no retry strategy for Ollama timeouts | Silent failures | LLM requests timeout after 60s, retry 3× |
| ⚪ **P3** | No logging to external service | Hard to debug in prod | Add Sentry.io SDK |
| ⚪ **P3** | Frontend is not responsive (mobile) | Poor mobile experience | Streamlit config + CSS |

---

### 3.2 Short-Term Roadmap (Next 2–4 Weeks)

**v1.1 — Production Ready**
- [ ] Set up Alembic: `alembic init migrations` → write initial migration → add `alembic upgrade head` to deploy command
- [ ] Add OpenAI/Groq fallback LLM so AI works on Render
- [ ] Add `slowapi` rate limiting (10 req/min per user on AI endpoints)
- [ ] Fix Streamlit error handling: wrap all `resp.json()` in try/except
- [ ] Add file size limit (10 MB) and MIME type validation in [file_extractor.py](file:///Users/deeasonsitaula/Documents/Programming/Final/career-ai-platform/backend/app/services/file_extractor.py)
- [ ] Write `CONTRIBUTING.md` and `DEPLOYMENT.md` docs
- [ ] Add GitHub Issue templates and PR template

---

### 3.3 Medium-Term Roadmap (1–2 Months)

**v1.2 — User Experience**
- [ ] **Password reset via email** — SendGrid integration
- [ ] **Resume versioning** — track changes to a resume over time
- [ ] **Cover letter templates** — formal, casual, creative styles
- [ ] **Application deadline reminders** — Celery beat scheduled tasks
- [ ] **Export to PDF** — generate downloadable cover letters using `weasyprint`
- [ ] **LinkedIn job import** — paste LinkedIn URL, auto-fill job description
- [ ] **Dashboard analytics** — response rate, interview conversion charts

**v1.3 — AI Enhancements**
- [ ] **Resume improvement suggestions** — LLM reviews resume and gives specific rewrite recommendations
- [ ] **Company research tool** — given a company name, summarize Glassdoor/news sentiment
- [ ] **Salary benchmarking** — integrate with a salary API (Glassdoor/Levels.fyi)
- [ ] **Multi-language cover letters** — French, Spanish, German output
- [ ] **RAG quality improvement** — use `langchain` parent-child chunking for better context retrieval
- [ ] **Fine-tuned scoring model** — train a small classifier on ATS pass/fail data

---

### 3.4 Long-Term Vision (3–6 Months)

**v2.0 — Platform Scale**
- [ ] **Next.js frontend** — replace Streamlit for a production-grade, mobile-first UI
- [ ] **Subscription tiers** — Stripe integration for Pro features (unlimited cover letters, advanced AI)
- [ ] **Team/recruiter accounts** — share resumes, pipeline views, collaboration
- [ ] **Browser extension** — one-click job application from LinkedIn/Indeed
- [ ] **Kubernetes deployment** — from Render free tier → AWS EKS for scale
- [ ] **Model fine-tuning pipeline** — use user feedback (thumbs up/down on cover letters) to fine-tune the LLM
- [ ] **Vector search upgrade** — replace FAISS with Pinecone or pgvector for production-grade RAG
- [ ] **GDPR compliance** — data export, right-to-deletion, cookie consent

---

### 3.5 Technical Debt to Address

```
backend/
├── No type stubs for SQLModel models          → Add mypy strict mode
├── Missing __all__ exports in __init__ files  → Explicit public API
├── Sync Celery task touches DB without ORM    → Migrate to SQLAlchemy Core
├── No structured logging (using print/logger) → Add structlog + Sentry
└── test_api.py requires live DB               → Mock with pytest fixtures

frontend/
├── app.py is a 300-line monolith              → Split into pages/ directory
├── No state management                        → Use st.session_state properly
├── API_URL hardcoded in file                  → Read from env at runtime
└── No loading states on AI calls              → Add proper spinners
```

---

### 3.6 Metrics to Track (Definition of Success)

Once deployed, track these to know if the platform is working:

| Metric | Target | Tool |
|--------|--------|------|
| API P95 response time | < 200ms (non-AI) | Render metrics |
| Cover letter generation time | < 30s | Flower / Celery |
| ATS score accuracy | > 80% user satisfaction | In-app thumbs up/down |
| Monthly Active Users | 50 in month 1 | PostHog (free) |
| Error rate | < 1% of requests | Sentry.io |
| Uptime | > 99.5% | UptimeRobot (free) |

---

## Quick Reference — Git Commands Cheatsheet

```bash
# New feature
git checkout develop && git pull origin develop
git checkout -b feature/<name>
# ... work ...
git add -p                          # stage interactively (patch-level)
git commit -m "feat(<scope>): <message>"
git push origin feature/<name>
# → Open PR on GitHub

# Hotfix on production
git checkout main && git pull origin main
git checkout -b hotfix/<name>
# ... fix ...
git commit -m "fix: <critical fix message>"
# → PR to main → auto-deploys → merge back to develop

# Sync develop into your feature branch (avoid big merge conflicts)
git fetch origin
git rebase origin/develop           # keeps history clean (vs. merge)

# Clean up merged branches
git branch -d feature/<name>        # local
git push origin --delete feature/<name>  # remote

# View branch graph
git log --oneline --graph --all --decorate
```
