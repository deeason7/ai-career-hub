# AI Career Hub — Infrastructure Reference

> Last updated: 2026-05-01 | Platform version: v3.0 | Region: `us-east-1`

---

## Table of Contents

1. [AWS Architecture](#aws-architecture)
2. [AWS Resources](#aws-resources)
3. [Boot Sequence](#boot-sequence)
4. [Wake-on-Visit Flow](#wake-on-visit-flow)
5. [Key File Reference](#key-file-reference)
6. [Operational Commands](#operational-commands)
7. [Change History](#change-history)

---

## AWS Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│  VISITOR                                                         │
│    └── careerhub.deeason.com.np                                  │
└──────────────────────────┬───────────────────────────────────────┘
                           │
                    ┌──────▼──────┐
                    │  Route 53   │  Health check on EC2 :80/health
                    │  Hosted Zone│  Failover: EC2 healthy vs sleeping
                    └──────┬──────┘
             ┌─────────────┴─────────────┐
             │ EC2 healthy               │ EC2 sleeping
             ▼                           ▼
    ┌─────────────────┐        ┌──────────────────────┐
    │  EC2 t3.small   │        │  CloudFront + S3      │
    │  Ubuntu 24.04   │        │  Wake Splash Page     │
    │  nginx (443/80) │        │  index.html           │
    │  FastAPI :8000  │        └──────────┬───────────┘
    │  Streamlit :8501│                   │ API Gateway
    │  Redis :6379    │                   ▼
    └────────┬────────┘        ┌──────────────────────┐
             │                 │  Lambda               │
    ┌────────▼────────┐        │  portfolio-wake-      │
    │  RDS PostgreSQL │        │  controller           │
    │  db.t3.micro    │        │  - Start EC2 + RDS    │
    │  Private VPC    │        │  - Schedule auto-stop │
    └─────────────────┘        └──────────────────────┘
                                          │ EventBridge Scheduler
                               ┌──────────▼───────────┐
                               │  Auto-Sleep           │
                               │  90 min after wake    │
                               │  Stops EC2 + RDS      │
                               └──────────────────────┘
```

---

## AWS Resources

### EC2

| Field | Value |
|---|---|
| Instance type | `t3.small` (2 vCPU, 2 GB RAM) |
| AMI | Ubuntu 24.04 LTS |
| Region | `us-east-1` |
| Tag | `Name=portfolio-server` |
| IAM Role | EC2 instance profile — SSM read, ECR pull, CloudWatch logs write |
| Access | SSM Session Manager only — no port 22, no SSH keys |
| Containers | Redis, FastAPI (api), Streamlit (frontend), Nginx — Docker Compose stack |

### RDS

| Field | Value |
|---|---|
| Identifier | `portfolio-db` |
| Engine | PostgreSQL 16 |
| Instance class | `db.t3.micro` |
| Subnet | Private VPC — no public endpoint |
| Credentials | SSM Parameter Store → `.env.prod` at deploy time |
| Cold-start time | ~3–4 minutes from stopped state |
| Note | App starts without blocking on RDS — async background migration task |

### ECR

| Repository | Contents |
|---|---|
| `careerhub-backend` | FastAPI + Alembic image (`linux/amd64`) |
| `careerhub-frontend` | Streamlit image (`linux/amd64`) |

Images built with `--platform linux/amd64` from Apple Silicon Mac. Lifecycle policy: retain last 3 images per repository.

### Lambda

| Field | Value |
|---|---|
| Function name | `portfolio-wake-controller` |
| Runtime | Python 3.12 |
| Timeout | 30s |
| Handler | `wake_controller.lambda_handler` |
| Role | `portfolio-wake-lambda-role` |
| Trigger | API Gateway (`POST /wake`, `GET /status`), EventBridge Scheduler (auto-stop, business-hours) |

### API Gateway

- HTTP API → Lambda `portfolio-wake-controller`
- Routes: `POST /wake`, `GET /status`
- CORS enabled
- Endpoint embedded in `infra/wake-page/index.html`

### CloudFront + S3

| Field | Value |
|---|---|
| S3 bucket | `careerhub-wake-page` (account-scoped) |
| Files | `index.html` — wake splash page |
| CloudFront | Points to S3 bucket via Origin Access Control (OAC) — S3 is private |

### Route 53

| Field | Value |
|---|---|
| Hosted zone | `deeason.com.np` |
| A record | `careerhub.deeason.com.np` — EC2 elastic IP (Primary) |
| Failover | CloudFront distribution (served when EC2 health check fails) |
| TTL | 60s |
| Health check | HTTP on port 80, path `/health`, 30s interval |

### EventBridge Scheduler

- One-time schedule created on every `/wake` call
- Fires 90 minutes after the most recent wake
- Invokes Lambda with `{"action": "stop"}` payload
- Self-deletes after firing (`ActionAfterCompletion: DELETE`)
- Each new `/wake` resets the timer by deleting and recreating the schedule

### SSM Parameter Store

All secrets under `/portfolio/careerhub/`:

```
POSTGRES_SERVER     RDS endpoint hostname
POSTGRES_USER       DB username
POSTGRES_PASSWORD   DB password (SecureString)
POSTGRES_DB         Database name
POSTGRES_PORT       5432
SECRET_KEY          JWT signing key (SecureString)
GROQ_API_KEY        Groq LLM API key (SecureString)
ALLOWED_ORIGINS     CORS allowed origins
PRODUCTION          "true"
SENTRY_DSN          (optional — Sentry error tracking)
```

### IAM

| Principal | Type | Purpose |
|---|---|---|
| `deeason-dev` | IAM user | Local development + deployments |
| `portfolio-developer` | Inline policy | Least-privilege EC2/RDS/SSM/ECR/Lambda/Route53 — project resources only |
| `portfolio-wake-lambda-role` | Lambda execution role | EC2/RDS start/stop, EventBridge Scheduler create/delete/describe |
| `portfolio-wake-scheduler-role` | EventBridge role | Invoke `portfolio-wake-controller` |
| EC2 instance profile | Instance role | SSM `/portfolio/*` read, ECR pull, CloudWatch logs write |

MFA enforced on root account and all IAM users. Root account has no access keys and is not used for daily operations.

### CloudWatch Logs

| Log group | Source |
|---|---|
| `/portfolio/careerhub-backend` | FastAPI container (awslogs driver, 30-day retention) |
| `/portfolio/careerhub-frontend` | Streamlit container (awslogs driver, 30-day retention) |
| `/portfolio/careerhub-nginx` | Nginx container (awslogs driver, 30-day retention) |
| `/aws/lambda/portfolio-wake-controller` | Lambda wake/sleep events |

---

## Boot Sequence

### Cold Boot (EC2 + RDS both stopped) — ~51s to app healthy

```
t=0         Lambda receives /wake → starts EC2 + RDS simultaneously
t=~30s      EC2 transitions stopped → running (OS fully booted)
t=~30s      Docker daemon starts (systemd)
t=~32s      unless-stopped containers restart from cached ECR images:
              Redis, FastAPI (api), Streamlit (frontend), Nginx
t=~33s      boot-deploy service starts:
              git pull origin main  (picks up latest config changes)
              docker compose up -d --remove-orphans
t=~35s      Redis: healthy
t=~38s      FastAPI (uvicorn): starts immediately — no Alembic wait
              _run_migrations_when_db_ready() starts as background task
t=~40s      GET http://{EC2_IP}:80/health → nginx → FastAPI → {"status":"ok"}
t=~50s      Wake page Lambda detects healthy
t=~55s      Wake page shows "App is Live!" → user redirected to app

Background (non-blocking):
t=+3–4 min  RDS becomes available
t=+3–4 min  Background task connects, runs alembic upgrade head
t=+3–4 min  All DB-dependent features (login, resumes, AI tools) now available

503 during DB cold-start:
  FastAPI returns 503 {"detail": "Database is starting up. Please try again in 30 seconds."}
  Streamlit shows a warning prompt — no unhandled errors
```

---

## Wake-on-Visit Flow

### User journey — app sleeping

1. Visitor hits `careerhub.deeason.com.np`
2. Route 53 health check on EC2 fails (EC2 stopped) → failover to CloudFront
3. CloudFront serves S3 `index.html` (wake splash page)
4. Splash page calls `GET /status` → Lambda returns `{ec2: "stopped", app: "down"}`
5. Splash page shows "Wake" button
6. User clicks → `POST /wake` → Lambda starts EC2 + RDS, schedules 90-min auto-stop
7. Splash page polls `GET /status` every 4–8 seconds
8. Lambda detects EC2 `/health` → 200 → returns `{app: "healthy"}`
9. Splash page redirects to `https://careerhub.deeason.com.np`

### User journey — app running

1. Visitor hits `careerhub.deeason.com.np`
2. Route 53 health check passes → A record → EC2 nginx → Streamlit app
3. No wake page, no redirect

### Auto-sleep

- Every `/wake` call creates or resets an EventBridge Scheduler one-time rule
- Rule fires 90 minutes after the most recent wake call
- Invokes Lambda `{"action": "stop"}` → stops EC2 + RDS
- Schedule self-deletes after firing
- Recruiter re-visits within 90 min → `/wake` resets the 90-min timer

---

## Key File Reference

```
ai-career-hub/
├── backend/
│   ├── Dockerfile                     CMD: uvicorn only (alembic runs as async background task)
│   ├── app/
│   │   ├── main.py                    FastAPI app, lifespan, async migration task, 503 handler
│   │   ├── core/
│   │   │   ├── config.py              Settings (reads .env.prod in production)
│   │   │   ├── db.py                  SQLAlchemy async + sync engines
│   │   │   ├── limiter.py             slowapi rate limiter (Redis-backed in production)
│   │   │   └── security.py            JWT creation/verification, bcrypt hashing
│   │   ├── api/v1/
│   │   │   ├── endpoints/             Route handlers: auth, resumes, cover-letters, ai, jobs, webhooks
│   │   │   └── deps.py                Auth dependency injection
│   │   ├── models/                    SQLModel table definitions
│   │   └── services/
│   │       ├── ats_scorer.py          Hybrid semantic + keyword + structure scoring
│   │       ├── cover_letter.py        Cover letter generation (Groq + Ollama paths)
│   │       ├── llm_client.py          instructor-patched LLM client (singleton)
│   │       ├── qa_service.py          AI-as-a-Judge review pass
│   │       └── resume_parser.py       LLM-based structured resume extraction
│   ├── migrations/                    Alembic migration scripts
│   └── tests/                         Test suite (auth, resumes, ATS, QA, LLM, webhooks)
├── frontend/
│   └── app.py                         Streamlit UI (auth, resumes, AI tools, application tracker)
├── docker-compose.yml                 Local development stack
├── docker-compose.prod.yml            Production stack (ECR images, awslogs, health checks)
├── infra/
│   ├── nginx/
│   │   └── nginx.conf                 SSL termination, gzip, proxy routing, HSTS
│   ├── wake-page/
│   │   ├── index.html                 S3/CloudFront wake splash page
│   │   └── wake_controller.py         Lambda: wake/stop/status/scheduled-wake
│   └── scripts/
│       ├── start.sh                   Start EC2 + RDS, wait for health
│       ├── stop.sh                    Stop EC2 + RDS
│       ├── deploy.sh                  EC2 deploy: pull secrets + images + restart stack
│       ├── rollback.sh                Re-tag previous ECR image as :latest and redeploy
│       ├── pull-secrets.sh            SSM → .env.prod on EC2
│       ├── install-boot-deploy.sh     Install systemd boot-deploy service on EC2
│       ├── setup-wake-on-visit.sh     One-time AWS infrastructure provisioning
│       └── setup-business-hours.sh    Install/update EventBridge Scheduler rules
├── nginx/
│   └── nginx.conf                     Development nginx config (local Docker Compose only)
└── .github/
    ├── workflows/
    │   └── pipeline.yml               CI (lint + test) + CD (build + push + deploy) pipeline
    └── dependabot.yml                 Weekly pip + monthly GitHub Actions dependency updates
```

---

## Operational Commands

### Start / Stop

```bash
# Full cold start (waits for app healthy, times it)
bash infra/scripts/start.sh

# Start without waiting
bash infra/scripts/start.sh --no-wait

# Stop both EC2 + RDS
bash infra/scripts/stop.sh
```

### SSM Connect

```bash
INSTANCE_ID=$(aws ec2 describe-instances \
  --filters "Name=tag:Name,Values=portfolio-server" \
            "Name=instance-state-name,Values=running" \
  --query "Reservations[0].Instances[0].InstanceId" \
  --output text --region us-east-1)

aws ssm start-session --target "$INSTANCE_ID" --region us-east-1
# Then: sudo su - ubuntu && cd ~/ai-career-hub
```

### Deploy New Code

```bash
# Automated (push to main triggers GitHub Actions)

# Manual
export ECR_REGISTRY=$(aws sts get-caller-identity --query Account --output text).dkr.ecr.us-east-1.amazonaws.com
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin "$ECR_REGISTRY"

docker build --platform linux/amd64 -t "$ECR_REGISTRY/careerhub-backend:latest" ./backend
docker push "$ECR_REGISTRY/careerhub-backend:latest"

docker build --platform linux/amd64 -t "$ECR_REGISTRY/careerhub-frontend:latest" ./frontend
docker push "$ECR_REGISTRY/careerhub-frontend:latest"

# On EC2 via SSM
cd ~/ai-career-hub && git pull origin main
bash infra/scripts/deploy.sh
```

### Rollback

```bash
# On EC2 via SSM
bash infra/scripts/rollback.sh <previous-git-sha>
```

### View Logs

```bash
# On EC2
docker compose -f docker-compose.prod.yml logs -f api
docker compose -f docker-compose.prod.yml logs -f nginx
sudo journalctl -u app-boot-deploy.service -f

# From local machine (CloudWatch)
aws logs tail /portfolio/careerhub-backend --follow --region us-east-1
aws logs tail /aws/lambda/portfolio-wake-controller --follow --region us-east-1
```

### Health Checks

```bash
# Public endpoint
curl -sf https://careerhub.deeason.com.np/health

# On EC2 — direct (bypasses Route53/DNS)
curl -s http://localhost/health

# Container status
docker compose -f docker-compose.prod.yml ps
```

### nginx reload (after config change, no rebuild)

```bash
docker compose -f docker-compose.prod.yml exec nginx nginx -t
docker compose -f docker-compose.prod.yml exec nginx nginx -s reload
```

### Run Alembic migrations manually

```bash
# On EC2 (migrations run automatically on startup — manual only if needed)
docker compose -f docker-compose.prod.yml exec api alembic -c /app/alembic.ini upgrade head
```

---

## Change History

### v3.1 — 2026-04-18 — Automated CD + CI Polish

- **CI/CD:** Merged into single `pipeline.yml` — ruff lint + format + pytest on PR; ECR build + push + SSM deploy on push to `main`
- **CD:** Automated health check + auto-rollback to previous SHA on failure
- **LLM tests:** All Groq-dependent tests marked `xfail` — clean CI without real API key
- **Code:** SQLModel `session.exec()` standardised across all endpoints; `Optional[X]` → `X | None` modernisation

### v3.0 — 2026-04-13 — Structured Output & Orchestration

- Structured LLM output via `instructor` + Pydantic v2 — 6 typed schemas
- AI-as-a-Judge QA layer — honesty/tone scoring, auto-regeneration up to 2× retries
- n8n Cloud workflow orchestration — webhook dispatch with graceful fallback to `BackgroundTasks`
- Refresh tokens (HttpOnly cookie, 7-day lifetime) — silent session renewal

### v2.6 — Business Hours Scheduler

- EventBridge Scheduler: start 9 AM ET / stop 6 PM ET, Mon–Fri recurring rules
- `setup-business-hours.sh` — idempotent install/update/remove
- Pre-commit hooks: ruff + file hygiene; CI: ruff lint + format + pytest
- 59 ruff errors resolved (52 auto-fixed, 7 manually)

### v2.5 — Performance & Reliability

- Lambda EC2+RDS status checks parallelised via `ThreadPoolExecutor` (~400ms vs ~1.3s)
- gzip compression on nginx for JS/CSS/JSON (~50% smaller payloads)
- `proxy_read_timeout` raised for long-running Groq requests
- Streamlit starts on `service_started` — ~10s earlier warm-up
- Wake page: polling with manual button fallback; RDS `stopping → stopped` auto-rewake

### v2.4 — Sub-90s Boot

- **Problem:** uvicorn waited for Alembic, which waited for RDS (~3–5 min startup time)
- **Fix:** Alembic runs as `asyncio.create_task()` background task — uvicorn starts immediately
- Added `@app.exception_handler(OperationalError)` returning 503 with `Retry-After: 30` during DB cold-start
- nginx HTTP `/health` location added — Lambda no longer waits for DNS round-trip during health polling

### v2.3 — Docker Health Checks

- Added health checks to all production containers (api, frontend, redis)
- nginx `depends_on: api: condition: service_healthy` — nginx only starts after FastAPI is ready
- Redis health check interval reduced from 10s to 5s

### v2.2 — Auto-sleep via EventBridge

- Every `/wake` call creates an EventBridge Scheduler one-time rule (90-min auto-stop)
- `handle_auto_stop()` Lambda handler stops EC2 + RDS
- Replaces earlier always-on cost model

### v2.1 — Production Hardening

- IAM least-privilege policies — scoped to named project resources
- EC2 IMDSv2 enforced — eliminates SSRF-based credential theft
- Daily billing alert configured in AWS Budgets
- TLS: Let's Encrypt via certbot DNS-01 + Route 53 plugin

### v2.0 — Wake on Visit Live

- S3/CloudFront wake splash page deployed
- Lambda `portfolio-wake-controller` deployed
- API Gateway → Lambda integrated
- Route 53 failover routing: EC2 health check + CloudFront failover record
- `install-boot-deploy.sh`: systemd service on EC2 (git pull + compose up on every boot)
