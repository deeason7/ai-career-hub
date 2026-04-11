# AI Career Hub — Infrastructure & Change Log

> Last updated: 2026-04-11 | Region: `us-east-1` | Account: `346657261080`

---

## Table of Contents

1. [Current AWS Architecture](#aws-architecture)
2. [AWS Resources — Full Inventory](#aws-resources)
3. [Boot Sequence (How It Actually Works)](#boot-sequence)
4. [Wake-on-Visit Flow](#wake-on-visit-flow)
5. [Change History](#change-history)
6. [Key File Reference](#key-file-reference)
7. [Operational Commands](#operational-commands)

---

## AWS Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│  VISITOR                                                         │
│    └── careerhub.deeason.com.np                                  │
└──────────────────────────┬───────────────────────────────────────┘
                           │
                    ┌──────▼──────┐
                    │  Route 53   │  Health check on EC2 port 80 /health
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
    └─────────────────┘        │  - Poll /health       │
                               └──────────────────────┘
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
| Instance ID | `i-07709e34044f62ef4` |
| Instance type | `t3.small` (2 vCPU, 2 GB RAM) |
| AMI | Ubuntu 24.04 LTS |
| Region / AZ | `us-east-1` |
| Public IP | `34.234.125.14` (elastic) |
| Tag | `Name=portfolio-server` |
| IAM Role | EC2 instance profile with SSM, ECR pull, CloudWatch logs |
| Access | SSM Session Manager only — no port 22, no SSH keys |
| Containers | Redis, FastAPI (api), Streamlit (frontend), Nginx — all Docker Compose |

### RDS
| Field | Value |
|---|---|
| Identifier | `portfolio-db` |
| Engine | PostgreSQL 16 |
| Instance class | `db.t3.micro` |
| Subnet | Private VPC — no public endpoint |
| Credentials | SSM Parameter Store → `.env.prod` at deploy time |
| Cold-start time | ~3-4 minutes from stopped |
| Note | App starts WITHOUT waiting for RDS (async background migration) |

### ECR
| Repository | Image | Size |
|---|---|---|
| `careerhub-backend` | FastAPI + alembic | ~3 GB uncompressed |
| `careerhub-frontend` | Streamlit | ~180 MB |

Build with `--platform linux/amd64` from M-series Mac.

### Lambda
| Field | Value |
|---|---|
| Function name | `portfolio-wake-controller` |
| Runtime | Python 3.12 |
| Timeout | 30s |
| Handler | `wake_controller.lambda_handler` |
| Role | `portfolio-wake-lambda-role` |
| Trigger | API GW `GET /wake`, `GET /status`, EventBridge Scheduler (auto-stop) |

Environment variables on Lambda:
```
EC2_INSTANCE_ID     = i-07709e34044f62ef4
RDS_INSTANCE_ID     = portfolio-db
LAMBDA_ARN          = arn:aws:lambda:us-east-1:346657261080:function:portfolio-wake-controller
SCHEDULER_ROLE_ARN  = arn:aws:iam::346657261080:role/portfolio-wake-scheduler-role
AUTO_STOP_MINUTES   = 90
HEALTH_PORT         = 80
```

### API Gateway
- REST API → Lambda `portfolio-wake-controller`
- Routes: `GET /wake`, `GET /status`
- CORS enabled
- URL embedded in `infra/wake-page/index.html`

### CloudFront + S3
| Field | Value |
|---|---|
| S3 bucket | `portfolio-wake-page-346657261080` |
| Files served | `index.html` (wake splash page) |
| CloudFront distribution | Points to S3 bucket |
| OAC | S3 is private — CloudFront uses Origin Access Control |

### Route 53
| Field | Value |
|---|---|
| Hosted zone | `deeason.com.np` |
| A record | `careerhub.deeason.com.np` |
| Primary | EC2 `34.234.125.14` (with Route53 health check on `:80/health`) |
| Failover | CloudFront (served when EC2 health check fails) |
| TTL | 60s |
| Health check | HTTP on port 80, path `/health`, 30s interval |

### EventBridge Scheduler
- One-time schedule created on every `/wake` call
- Fires 90 minutes after wake
- Invokes Lambda with `{"action": "stop"}` payload
- Self-deletes after firing (`ActionAfterCompletion: DELETE`)
- Resetting: each new `/wake` deletes old schedule and creates a fresh 90-min one

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
ALLOWED_ORIGINS     CORS origins
PRODUCTION          "true"
```

### IAM
| Principal | Type | Purpose |
|---|---|---|
| `deeason-dev` | IAM user | Local development + deployments |
| `portfolio-developer` | Policy on user | Least-privilege EC2/RDS/SSM/ECR/Lambda/Route53 |
| `portfolio-wake-lambda-role` | Role (Lambda) | EC2/RDS start/stop, EventBridge Scheduler create/delete |
| `portfolio-wake-scheduler-role` | Role (EventBridge) | Invoke Lambda |
| EC2 instance profile | Role (EC2) | SSM `/portfolio/*` read, ECR pull, CloudWatch logs |

### CloudWatch Logs
| Log group | Source |
|---|---|
| `/portfolio/careerhub-backend` | FastAPI container (awslogs driver) |
| `/portfolio/careerhub-frontend` | Streamlit container (awslogs driver) |
| `/portfolio/careerhub-nginx` | Nginx container (awslogs driver) |
| `/aws/lambda/portfolio-wake-controller` | Lambda wake/sleep events |

### Billing
- Budget: **$2/day** alert → `deeasonsitaula5@gmail.com`
- Expected cost at normal use: **$1-2/month**
- EC2 + RDS only incur cost when running (~$0.05-0.20/day on use)

---

## Boot Sequence

### Cold Boot (EC2 + RDS both stopped) — **~51s to app healthy**

```
t=0         Lambda receives /wake → starts EC2 + RDS simultaneously
t=~30s      EC2 transitions stopped → running (OS fully booted)
t=~30s      Docker daemon starts (systemd)
t=~32s      unless-stopped containers restart from cached ECR images:
              Redis, FastAPI (api), Streamlit (frontend), Nginx
t=~33s      boot-deploy service starts:
              git pull origin main  (picks up latest nginx.conf / compose changes)
              docker compose up -d --remove-orphans  (recreates if config changed)
t=~35s      Redis: healthy (redis-cli ping)
t=~38s      FastAPI (uvicorn): starts immediately — NO alembic wait
              _run_migrations_when_db_ready() starts as async background task
t=~40s      GET http://{EC2_IP}:80/health → nginx → FastAPI → {"status":"ok"}
t=~50s      Wake page Lambda poll detects healthy
t=~55s      Wake page shows "App is Live!" → user redirected

Background (non-blocking):
t=+3-4 min  RDS becomes available
t=+3-4 min  Background task connects to RDS, runs alembic upgrade head
t=+3-4 min  All DB-dependent features (login, resumes, etc.) now work

If user tries login before DB ready:
  FastAPI returns 503 {"detail": "Database is starting up. Please try again in 30 seconds."}
  Streamlit shows: "⏳ Database is still warming up — please try again in ~30 seconds."
```

### Before Optimization (for reference)
```
t=0         Lambda starts EC2 + RDS
t=~60s      EC2 running, Docker starts containers
t=~65s      boot-deploy: git pull (20-40s delay)
t=~105s     docker compose up starts
t=~110s     api container starts: alembic upgrade head → BLOCKS → polls RDS every 5s
t=~240s     RDS available → alembic connects → schema checked → uvicorn starts
t=~245s     /health → 200 (via nginx 301 → Route53 → 15-20s DNS delay) 
t=~265s     Wake page detects healthy

Total: ~4-5 minutes
```

---

## Wake-on-Visit Flow

### User journey (app sleeping)
1. Visitor hits `careerhub.deeason.com.np`
2. Route 53 health check on EC2 is failing (EC2 stopped) → failover to CloudFront
3. CloudFront serves S3 `index.html` (wake splash page)
4. Splash page JS calls `GET /status` (API GW → Lambda) to check state
5. Lambda returns `{ec2: "stopped", app: "down"}`
6. Splash page shows "Click to Wake" button
7. User clicks → `GET /wake` (API GW → Lambda)
8. Lambda: starts EC2 + RDS, schedules 90-min auto-stop, returns immediately
9. Splash page polls `GET /status` every 4-8 seconds
10. Once wake Lambda detects `http://{EC2_IP}/health` → 200, splash returns `{app: "healthy"}`
11. Splash page shows "App is Live!" → JavaScript redirects to `https://careerhub.deeason.com.np`

### User journey (app already running)
1. Visitor hits `careerhub.deeason.com.np`
2. Route 53 health check on EC2 passes → A record → EC2 nginx → Streamlit app directly
3. No wake page, no redirect delay

### Auto-sleep
- On every `/wake` call, Lambda creates/updates an EventBridge Scheduler one-time rule
- Rule fires 90 minutes after most recent wake
- Invokes Lambda `{"action": "stop"}` → stops EC2 + RDS
- Schedule self-deletes (`ActionAfterCompletion: DELETE`)
- Recruiter re-visits within 90 min → `/wake` resets the timer (idempotent)

---

## Change History

### v2.4.1 — 2026-04-11 — nginx HTTP /health fix (15-20s boot saving)

**Problem:** nginx HTTP server block (port 80) had no `/health` location.
Every Lambda health check hit `location /` → `301 → https://careerhub.deeason.com.np/health`
→ Route 53 DNS resolution → CloudFront (during EC2 warmup) → 404.
This added 15-20s of Route53/DNS delay before detection.

**Fix:** Added `location /health` to the HTTP (port 80) server block.
Lambda now gets `{"status":"ok"}` directly from FastAPI without redirect/DNS.

**File:** `infra/nginx/nginx.conf`
```diff
 server {
     listen 80;
-    server_name careerhub.deeason.com.np;
+    server_name careerhub.deeason.com.np _;

     location /.well-known/acme-challenge/ { root /var/www/certbot; }

+    # Health check — direct to FastAPI, no redirect, no DNS round-trip
+    location /health {
+        proxy_pass http://api:8000;
+        proxy_set_header Host            $host;
+        proxy_set_header X-Real-IP       $remote_addr;
+        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
+    }
+
     location / { return 301 https://$host$request_uri; }
 }
```

---

### v2.4.0 — 2026-04-11 — Sub-90s boot: async alembic + graceful 503 (3-5 min saving)

**Root cause:** `CMD ["sh", "-c", "until alembic upgrade head; do sleep 5; done && uvicorn"]`
— uvicorn never started until alembic connected to RDS. RDS takes 3-4 min from stopped.
FastAPI's `/health` was unreachable for the entire RDS coldstart window.

**Changes:**

#### `backend/Dockerfile`
```diff
-CMD ["sh", "-c", "until alembic upgrade head; do sleep 5; done && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]
+# Migrations run as async background task in main.py (_run_migrations_when_db_ready)
+CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

#### `backend/app/main.py`
- Added `_run_migrations_when_db_ready()`: async task that polls DB every 5s,
  runs `alembic upgrade head` via thread executor once RDS is reachable.
- Added `@app.exception_handler(OperationalError)` and `@app.exception_handler(InterfaceError)`:
  converts SQLAlchemy connection errors to `503 {"detail": "Database is starting up..."}`.
- Lifespan updated: production calls `asyncio.create_task(_run_migrations_when_db_ready())`.

#### `docker-compose.prod.yml`
```diff
-      start_period: 25s  # was sized for alembic wait
+      start_period: 10s  # uvicorn starts in <5s, 10s is generous
```

#### `frontend/app.py`
- Login form: added `elif resp.status_code == 503:` → shows "⏳ Database warming up" warning.
- Register form: same 503 handling.

---

### v2.3.0 — 2026-04-11 — Docker health checks + faster redis interval

**Changes:**

#### `docker-compose.prod.yml`
- `api`: added `healthcheck` (interval 5s, start_period 25s) using Python urllib
  (curl not in python:3.11-slim image).
- `frontend`: added `healthcheck` (interval 8s, start_period 35s) on `/_stcore/health`.
- `nginx`: `depends_on: api: condition: service_healthy` — nginx only starts after FastAPI ready.
- `frontend`: `depends_on: api: condition: service_healthy` — Streamlit waits for FastAPI.
- `redis`: interval reduced from 10s to 5s.

#### `backend/Dockerfile` (later partially replaced by v2.4.0)
- CMD: added alembic retry loop to prevent Docker exponential backoff crash cycles.

---

### v2.2.0 — 2026-04-11 — Auto-sleep via EventBridge Scheduler

**Change:** `infra/wake-page/wake_controller.py`
- `_schedule_auto_stop()`: on every `/wake` call, creates/updates a one-time
  EventBridge Scheduler rule to stop EC2 + RDS 90 minutes later.
- `handle_auto_stop()`: new Lambda entry point called by the scheduler.

---

### v2.1.0 — 2026-04-06 — Production hardening

- IAM `WakeOnVisitSetup` → replaced with minimal `WakeOnVisitOperate` (least-privilege)
- EC2 IMDSv2 enforced
- Daily billing alert ($2/day) configured in AWS Budgets
- TLS: Let's Encrypt via certbot DNS-01 + Route53 plugin
- `infra/scripts/stop.sh`: EC2 + RDS stop in one command

---

### v2.0.0 — 2026-04-05 — Wake on Visit live

- S3/CloudFront wake splash page deployed
- Lambda `portfolio-wake-controller` deployed
- API GW → Lambda integrated
- Route 53 failover: EC2 health check + CloudFront failover record
- `infra/scripts/install-boot-deploy.sh`: systemd service on EC2 (git pull + compose up)

---

## Key File Reference

```
ai-career-hub/
├── backend/
│   ├── Dockerfile                         CMD: uvicorn only (alembic is async background)
│   ├── app/
│   │   ├── main.py                        FastAPI app, lifespan, async alembic task, 503 handler
│   │   ├── core/
│   │   │   ├── config.py                  Settings (reads .env.prod in prod)
│   │   │   ├── db.py                      SQLAlchemy async + sync engines (lazy connect)
│   │   │   └── limiter.py                 SlowAPI rate limiter
│   │   ├── api/v1/                        Route handlers: auth, resumes, cover-letters, ai, jobs
│   │   └── services/
│   │       └── ats_scorer.py              ML scoring (lazy lru_cache model load)
│   ├── alembic.ini                        Migration config (/app/alembic.ini in container)
│   └── migrations/                        Alembic migration scripts
├── frontend/
│   ├── Dockerfile                         Streamlit image
│   └── app.py                             Full Streamlit UI (auth, resumes, AI tools, tracker)
├── docker-compose.prod.yml                Production compose (health checks, logging, deps)
├── infra/
│   ├── nginx/
│   │   └── nginx.conf                     SSL termination + /health on port 80 + 443
│   ├── wake-page/
│   │   ├── index.html                     S3/CloudFront wake splash page
│   │   └── wake_controller.py             Lambda: start/stop/status/auto-sleep
│   └── scripts/
│       ├── start.sh                       Start EC2+RDS, wait for health
│       ├── stop.sh                        Stop EC2+RDS
│       ├── deploy.sh                      Build+push images + force-recreate on EC2
│       ├── pull-secrets.sh                SSM → .env.prod on EC2
│       ├── install-boot-deploy.sh         Install systemd boot service on EC2
│       └── setup-wake-on-visit.sh         One-time AWS infra provisioning
└── DEPLOYMENT.md                          Operational runbook
```

---

## Operational Commands

### Start / Stop

```bash
# Full cold start (waits for app healthy, times it)
bash infra/scripts/start.sh

# Start without waiting (background boot)
bash infra/scripts/start.sh --no-wait

# Stop both EC2 + RDS
bash infra/scripts/stop.sh
```

### SSM Connect

```bash
aws ssm start-session --target i-07709e34044f62ef4 --region us-east-1
# Inside:
sudo su - ubuntu
cd ~/ai-career-hub
```

### Deploy New Code

```bash
# 1. Build + push from Mac
export ECR_REGISTRY=$(aws sts get-caller-identity --query Account --output text).dkr.ecr.us-east-1.amazonaws.com
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin $ECR_REGISTRY

docker build --platform linux/amd64 -t $ECR_REGISTRY/careerhub-backend:latest ./backend
docker push $ECR_REGISTRY/careerhub-backend:latest

docker build --platform linux/amd64 -t $ECR_REGISTRY/careerhub-frontend:latest ./frontend
docker push $ECR_REGISTRY/careerhub-frontend:latest

# 2. On EC2 (via SSM): pull new images and recreate
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin 346657261080.dkr.ecr.us-east-1.amazonaws.com
export ECR_REGISTRY=346657261080.dkr.ecr.us-east-1.amazonaws.com
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d --force-recreate
```

### Run Alembic Migrations (schema changes only)

```bash
# On EC2 — only needed after actual schema changes, NOT on normal boots
export ECR_REGISTRY=346657261080.dkr.ecr.us-east-1.amazonaws.com
docker compose -f docker-compose.prod.yml run --rm api alembic upgrade head
```

### View Logs

```bash
# On EC2
docker compose -f docker-compose.prod.yml logs -f api     # FastAPI logs (incl DB migration status)
docker compose -f docker-compose.prod.yml logs -f nginx    # nginx access logs
sudo journalctl -u app-boot-deploy.service -f              # boot-deploy logs

# From Mac (CloudWatch)
aws logs tail /portfolio/careerhub-backend --follow --region us-east-1
aws logs tail /aws/lambda/portfolio-wake-controller --follow --region us-east-1
```

### Health Checks

```bash
# From Mac
curl -sk https://careerhub.deeason.com.np/health

# From EC2 — HTTP direct (bypasses Route53, no DNS)
curl -s http://localhost/health        # should return {"status":"ok"}
curl -sk https://localhost/health      # HTTPS via nginx

# Container health state
docker compose -f docker-compose.prod.yml ps
```

### nginx Reload (after config change, no rebuild needed)

```bash
# git pull the new nginx.conf, then:
docker compose -f docker-compose.prod.yml exec nginx nginx -t      # test config
docker compose -f docker-compose.prod.yml exec nginx nginx -s reload
```

### Update Lambda Code

```bash
cd infra/wake-page
zip -q wake_controller.zip wake_controller.py
aws lambda update-function-code \
  --function-name portfolio-wake-controller \
  --zip-file fileb://wake_controller.zip --region us-east-1
rm wake_controller.zip
```
