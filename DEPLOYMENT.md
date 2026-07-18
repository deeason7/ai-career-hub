# Deployment Guide — AI Career Hub

Two production targets from one codebase: a zero-cost free-tier deployment (Hugging Face Spaces + Streamlit Community Cloud) that serves live traffic, and the fully scripted AWS environment documented below, currently hibernated. Each target sits behind its own switch — see [Deploy Targets](#deploy-targets).

---

## Table of Contents

1. [Current State](#current-state)
2. [Deploy Targets](#deploy-targets)
3. [AWS Infrastructure](#aws-infrastructure)
4. [Standard Deploy](#standard-deploy)
5. [Business Hours Scheduler](#business-hours-scheduler)
6. [Wake on Visit](#wake-on-visit)
7. [TLS / HTTPS](#tls--https)
8. [Developer Tooling](#developer-tooling)
9. [Billing Controls](#billing-controls)
10. [Free-tier deployment (Hugging Face Spaces + Streamlit Community Cloud)](#free-tier-deployment-hugging-face-spaces--streamlit-community-cloud)

---

## Current State

| Component | Status | Notes |
|---|---|---|
| Free-tier stack | **Live** | HF Space (API) + Streamlit Cloud (frontend) + Neon + Upstash + Qdrant — deployed and health-verified by CI on every `main` push |
| EC2 stack | **Hibernated** | Deprovisioned to $0; recreated by `infra/scripts/` when re-arming |
| RDS PostgreSQL | **Hibernated** | Deleted to a final snapshot; restore when re-arming |
| Business Hours | **Hibernated** | EventBridge schedules removed; `setup-business-hours.sh` recreates them |
| Domain | **Parked** | `careerhub.deeason.com.np` records removed while hibernated; the hosted zone remains |
| TLS | **Scripted** | Let's Encrypt (certbot DNS-01) reissues on a recreated instance; nginx terminates SSL in Docker |
| Wake on Visit | **Hibernated** | `setup-wake-on-visit.sh` provisions the failover → splash → Lambda flow; `--teardown` removes it |
| Auto-Sleep | **Hibernated** | Recreated by `schedule-sleep.sh` when re-arming |
| Boot Deploy | **Scripted** | systemd service: `git pull + docker compose up` runs on every EC2 boot |
| CI | **Live** | GitHub Actions: ruff lint + format check + pytest on push to `main` / `develop` |
| CD | **Switchable** | Per-target deploys on push to `main` — see [Deploy Targets](#deploy-targets) |
| Pre-commit | **Live** | ruff lint + format + hygiene hooks — install with `pre-commit install` |

---

## Deploy Targets

One codebase, two production targets, each behind its own repository variable so
either can be paused without touching the workflow:

| Target | Switch (repo variable) | What a green `main` push does |
|---|---|---|
| AWS (EC2 + RDS + ECR) | `AWS_DEPLOY_ENABLED=true` | Build images → push to ECR → SSM deploy on EC2 → health check → auto-rollback on failure |
| Free tier (HF Space + Neon + Upstash + Qdrant) | `FREE_DEPLOY_ENABLED=true` | Mirror `backend/` to the Space → wait for the rebuild → require a healthy `/health/warm` |

- With `AWS_DEPLOY_ENABLED` unset the AWS deploy job simply skips. The AWS
  environment itself is currently **hibernated**: compute, database, and wake
  infrastructure are deprovisioned to $0/mo, with the database preserved as a
  final RDS snapshot. Re-arming = re-run the provisioning scripts in
  `infra/scripts/`, restore the snapshot, then set the variable to `true`.
- The Streamlit Community Cloud frontend redeploys itself from `main`; the
  free-tier job verifies the API side end-to-end (Space rebuilt, DB and vector
  store answering) so a broken image can't land silently.
- Need to redeploy the current `main` without a commit? Actions → Pipeline →
  *Run workflow* (`workflow_dispatch` re-runs CI, then the armed deploy jobs).

---

## AWS Infrastructure

### EC2

- **Instance type:** t3.small (Ubuntu 24.04 LTS)
- **Region:** us-east-1
- **Tag:** `Name=portfolio-server`
- **IAM role:** Scoped to SSM Parameter Store (`/portfolio/*` prefix) + ECR pull + CloudWatch logs write
- **Access:** AWS SSM Session Manager — no SSH keys, no port 22 open

```bash
# Connect to EC2 (no SSH key required)
INSTANCE_ID=$(aws ec2 describe-instances \
  --filters "Name=tag:Name,Values=portfolio-server" \
            "Name=instance-state-name,Values=running" \
  --query "Reservations[0].Instances[0].InstanceId" \
  --output text --region us-east-1)

aws ssm start-session --target "$INSTANCE_ID" --region us-east-1
# Then: sudo su - ubuntu
```

### RDS

- **Identifier:** `portfolio-db`
- **Engine:** PostgreSQL 16
- **Instance class:** db.t3.micro
- **Subnet:** Private VPC — no public endpoint
- **Credentials:** Stored in SSM Parameter Store, written to `.env.prod` at deploy time only

### ECR

Two repositories in `us-east-1`:
- `careerhub-backend` — FastAPI + Alembic image (linux/amd64)
- `careerhub-frontend` — Streamlit image (linux/amd64)

Images are built with `--platform linux/amd64` to target the x86_64 EC2 instance.
Always run `docker image prune -f` after pulling new images on EC2 to prevent disk exhaustion.

### Secrets (SSM Parameter Store)

All parameters under `/portfolio/careerhub/`. The EC2 instance role has read-only access to this prefix. `pull-secrets.sh` reads the entire prefix and writes `.env.prod` at deploy time.

```
/portfolio/careerhub/POSTGRES_SERVER
/portfolio/careerhub/POSTGRES_USER
/portfolio/careerhub/POSTGRES_PASSWORD     (SecureString)
/portfolio/careerhub/POSTGRES_DB
/portfolio/careerhub/POSTGRES_PORT
/portfolio/careerhub/SECRET_KEY            (SecureString)
/portfolio/careerhub/GROQ_API_KEY          (SecureString)
/portfolio/careerhub/ALLOWED_ORIGINS
/portfolio/careerhub/PRODUCTION
/portfolio/careerhub/ADMIN_SECRET          (SecureString — required for /admin/* lifecycle endpoints)
/portfolio/careerhub/SENTRY_DSN            (optional)
/portfolio/careerhub/N8N_WEBHOOK_URL       (optional)
/portfolio/careerhub/N8N_WEBHOOK_SECRET    (SecureString, optional)
```

### DNS

- **DNS hosted zone:** AWS Route 53 (`deeason.com.np`)
- **Record:** `careerhub.deeason.com.np` → EC2 elastic IP (type A, TTL 60)
- **Failover:** CloudFront distribution served when EC2 health check fails

### IAM

All roles and policies follow least-privilege — scoped to named project resources only. No wildcard actions, no cross-project access.

| Principal | Type | Purpose |
|---|---|---|
| `deeason-dev` | IAM user | Local development + deployments |
| `portfolio-developer` | Policy on user | EC2/RDS/SSM/ECR/Lambda/Route53 — project scope only |
| `portfolio-wake-lambda-role` | Lambda execution role | EC2/RDS start/stop, EventBridge Scheduler create/delete |
| `portfolio-wake-scheduler-role` | EventBridge Scheduler role | Invoke Lambda |
| EC2 instance profile | Instance role | SSM `/portfolio/*` read, ECR pull, CloudWatch logs |

MFA is enforced on root account and all developer IAM users. Root account has no access keys.

### Monitoring

- **CloudWatch:** All containers log to `/portfolio/careerhub-backend`, `/portfolio/careerhub-frontend`, `/portfolio/careerhub-nginx` with 30-day retention
- **Sentry:** Integrated in FastAPI — opt-in via `SENTRY_DSN` in SSM
- **Billing:** Daily spend alerting configured in AWS Budgets

---

## Standard Deploy

### Automated (preferred)

Push to `main` — GitHub Actions runs automatically:

1. Lint and test (Postgres service container in CI)
2. Build `linux/amd64` images for backend and frontend
3. Push to ECR tagged `:latest` and `:<git-sha>`
4. Start EC2 and RDS if stopped
5. Deploy to EC2 via SSM `send-command` (runs `deploy.sh`)
6. Health check: `GET https://careerhub.deeason.com.np/health` must return 200
7. Auto-rollback to previous SHA if health check fails

### Manual fallback

Use when GitHub Actions is unavailable or a hotfix must skip CI.

```bash
# Build and push images
export ECR_REGISTRY=$(aws sts get-caller-identity --query Account --output text).dkr.ecr.us-east-1.amazonaws.com
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin "$ECR_REGISTRY"

docker build --platform linux/amd64 -t "$ECR_REGISTRY/careerhub-backend:latest" ./backend
docker push "$ECR_REGISTRY/careerhub-backend:latest"

docker build --platform linux/amd64 -t "$ECR_REGISTRY/careerhub-frontend:latest" ./frontend
docker push "$ECR_REGISTRY/careerhub-frontend:latest"

# Connect and deploy
INSTANCE_ID=$(aws ec2 describe-instances \
  --filters "Name=tag:Name,Values=portfolio-server" \
            "Name=instance-state-name,Values=running" \
  --query "Reservations[0].Instances[0].InstanceId" \
  --output text --region us-east-1)

aws ssm start-session --target "$INSTANCE_ID" --region us-east-1
# On EC2:
sudo su - ubuntu && cd ~/ai-career-hub
git pull origin main
bash infra/scripts/deploy.sh
```

### Deploying wake-page updates (when `wake_controller.py` or `index.html` change)

```bash
# Lambda
cd infra/wake-page
zip -q wake_controller.zip wake_controller.py
aws lambda update-function-code \
  --function-name portfolio-wake-controller \
  --zip-file fileb://wake_controller.zip \
  --region us-east-1
rm wake_controller.zip
cd ../..

# S3 + CloudFront invalidation
aws s3 cp infra/wake-page/index.html \
  s3://careerhub-wake-page/index.html \
  --content-type "text/html" --cache-control "no-cache, max-age=0" \
  --region us-east-1

DIST_ID=$(aws cloudfront list-distributions \
  --query "DistributionList.Items[?Comment=='careerhub-wake-page'].Id" \
  --output text)
aws cloudfront create-invalidation \
  --distribution-id "$DIST_ID" --paths "/*" --region us-east-1
```

---

## Business Hours Scheduler

EC2 + RDS automatically start at 9 AM ET and stop at 6 PM ET, Mon–Fri — ensuring instant page loads during core hours without 24/7 running costs.

| Rule | Cron | Action |
|---|---|---|
| `portfolio-business-hours-start` | `cron(0 9 ? * MON-FRI *)` | `action:wake` → starts EC2 + RDS |
| `portfolio-business-hours-stop` | `cron(0 18 ? * MON-FRI *)` | `action:stop` → stops EC2 + RDS |

```bash
# Install / update schedules
bash infra/scripts/setup-business-hours.sh

# Verify
aws scheduler get-schedule --name portfolio-business-hours-start --region us-east-1
aws scheduler get-schedule --name portfolio-business-hours-stop  --region us-east-1

# Remove
bash infra/scripts/setup-business-hours.sh --remove
```

**Cost impact:** ~$7.50/month for business hours only vs ~$27/month for 24/7.

---

## Document Lifecycle Cleanup

Expired resumes and cover letters (15-day TTL) are deleted by calling the admin endpoint. Wire this to EC2 cron for nightly cleanup:

```bash
# Run on EC2 as ubuntu — add to crontab with: crontab -e
# Runs at 2 AM UTC every day
0 2 * * * curl -s -X POST http://localhost:8000/api/v1/admin/lifecycle/run \
  -H "X-Admin-Secret: $ADMIN_SECRET" \
  >> /var/log/lifecycle-cleanup.log 2>&1
```

The endpoint returns `{"status": "ok", "deleted_resumes": N, "deleted_cover_letters": N}`. All output is also written to CloudWatch via the container's `awslogs` driver.

> `ADMIN_SECRET` must be set in SSM and pulled into `.env.prod` at deploy time. If it is not set, all `/admin/*` requests will return 403.

---

## Wake on Visit

```
Visitor → careerhub.deeason.com.np
       → Route 53 health check
       ├─ EC2 healthy  → nginx → app (no wait)
       └─ EC2 sleeping → CloudFront → S3 wake page
                                   ↓
                         API Gateway → Lambda (portfolio-wake-controller)
                         Starts EC2 + RDS, schedules 90-min auto-stop
                                   ↓
                         ~90s boot → redirect to live app
                                   ↓
                         90 min later → EventBridge auto-stops EC2 + RDS
```

### Lambda routing

| Event | Handler | Notes |
|---|---|---|
| HTTP POST `/wake` | `handle_wake()` | Starts EC2+RDS, resets 90-min idle timer |
| HTTP GET `/status` | `handle_status()` | Returns `{ec2, rds, app}` — checked in parallel |
| `{action: "stop"}` | `handle_auto_stop()` | Stops EC2+RDS. Fired by idle timer or 6 PM EventBridge cron |
| `{action: "wake"}` | `handle_scheduled_wake()` | Starts EC2+RDS. Fired by 9 AM EventBridge cron. No idle timer |

### Key files

| File | Purpose |
|---|---|
| `infra/wake-page/index.html` | S3 splash page — animated status, auto-redirect |
| `infra/wake-page/wake_controller.py` | Lambda: wake, status, stop, scheduled-wake |
| `infra/scripts/setup-wake-on-visit.sh` | One-time AWS infrastructure provisioning |
| `infra/scripts/setup-business-hours.sh` | Install/update EventBridge Scheduler rules |
| `infra/scripts/install-boot-deploy.sh` | Install systemd boot-deploy service on EC2 |
| `infra/nginx/nginx.conf` | SSL termination, gzip, proxy routing |

---

## TLS / HTTPS

Let's Encrypt certificate issued via DNS-01 challenge (certbot + Route 53 plugin). Nginx inside Docker handles SSL termination.

- **Certificate path (on EC2):** `/etc/letsencrypt/live/careerhub.deeason.com.np/`
- **Nginx config:** `infra/nginx/nginx.conf` (mounted read-only into nginx container)
- **Renewal:** certbot systemd timer handles automatic renewal. After renewal:

```bash
sudo certbot renew
docker compose -f docker-compose.prod.yml restart nginx
curl -sk https://localhost/health
```

---

## Developer Tooling

### ruff (lint + format)

Configuration in `backend/ruff.toml`. Rules: E, F, W, I (isort), B (bugbear), UP (pyupgrade).

```bash
ruff check backend/          # check
ruff check --fix backend/    # auto-fix
ruff format backend/         # format
```

CI enforces both `ruff check` and `ruff format --check` on every push.

### pre-commit

Hooks configured in `.pre-commit-config.yaml`:
- `ruff` (lint + auto-fix) and `ruff-format` — backend Python only
- `trailing-whitespace`, `end-of-file-fixer`, `check-yaml`, `check-json`
- `check-merge-conflict`, `check-added-large-files` (500 KB limit)
- `mixed-line-ending` (enforces LF)

```bash
pip install -r backend/requirements.dev.txt
pre-commit install
pre-commit run --all-files   # run manually
pre-commit autoupdate        # update hook versions
```

---

## Billing Controls

Expected monthly cost:

| Component | Estimate |
|---|---|
| Business hours (9 AM–6 PM ET, Mon–Fri) | ~$7.00 |
| Off-hours Wake-on-Visit usage | ~$0.50 |
| Lambda + API Gateway + S3 + CloudFront | ~$0 (free tier) |
| Route 53 health check | ~$0.50 |
| **Total** | **~$8/month** |

Manual controls:

```bash
# Force stop
bash infra/scripts/stop.sh

# Force start
bash infra/scripts/start.sh

# Test wake Lambda
aws lambda invoke \
  --function-name portfolio-wake-controller \
  --payload '{"action":"wake"}' \
  --region us-east-1 /dev/stdout

# Test stop Lambda
aws lambda invoke \
  --function-name portfolio-wake-controller \
  --payload '{"action":"stop"}' \
  --region us-east-1 /dev/stdout
```

---

## Free-tier deployment (Hugging Face Spaces + Streamlit Community Cloud)

An alternative to the AWS stack above, for a $0/month deploy: the backend runs on a Hugging Face Space (Docker SDK), the frontend on Streamlit Community Cloud, and Postgres/Redis/the vector store move to their free managed equivalents (Neon/Upstash/Qdrant Cloud). Both app hosts sleep on inactivity and cold-start in seconds — no Wake-on-Visit machinery needed, but see [Keep-warm](#keep-warm) below. This is additive documentation; it does not change how the AWS path above works.

### Continuous deployment — one branch, two environments

Both targets deploy from `main`, from the **same commit**, via `pipeline.yml`. A push to `main` runs CI once, then two deploy jobs run in parallel, each scoped to its own GitHub Environment so AWS and free-tier secrets never mix:

| Job | Environment | Target |
|---|---|---|
| `deploy` | `production` | AWS (ECR → SSM → EC2) |
| `deploy-free` | `free-prod` | this HF Space (Streamlit redeploys itself from `main`) |

`deploy-free` mirrors `backend/` to the Space with `huggingface_hub`, which triggers the Space's own Docker build — nothing is built in CI for the free path. It is gated by the repository variable `FREE_DEPLOY_ENABLED`, so it stays dormant until you switch it on.

**One-time setup:** create a `free-prod` GitHub Environment (Settings → Environments) with an `HF_TOKEN` secret (an HF write token; add required reviewers there for an approval gate), then set repository variable `FREE_DEPLOY_ENABLED=true` (optionally `HF_SPACE` to override the default Space id). The manual `git subtree push` below is the by-hand equivalent, for a first or one-off deploy.

### Managed data services

| Service | Replaces | Notes |
|---|---|---|
| [Neon](https://neon.tech) | RDS PostgreSQL | Serverless Postgres, free tier. Set `POSTGRES_SERVER` / `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` to the Neon connection details, plus `DB_SSLMODE=require` |
| [Upstash](https://upstash.com) | Redis (Docker Compose) | Serverless Redis, free tier. Set `REDIS_HOST` / `REDIS_PORT` / `REDIS_PASSWORD` to the Upstash connection details, plus `REDIS_SSL=true` and `REDIS_DB_TASKS=0` / `REDIS_DB_DENYLIST=0` (Upstash supports only database 0) |
| [Qdrant Cloud](https://qdrant.tech) | ChromaDB | HF Spaces' free tier has no persistent disk, so the RAG vector store moves off local ChromaDB. Set `VECTOR_BACKEND=qdrant`, `QDRANT_URL`, `QDRANT_API_KEY`, `QDRANT_COLLECTION` |

### Backend on Hugging Face Spaces (Docker SDK)

The existing `backend/Dockerfile` is used **as-is** — no changes needed. It's already HF-shaped: `python:3.11-slim`, a single `uvicorn` process, a non-root user, `EXPOSE 8000`, the CPU-only torch pin, and Alembic migrations that run as a non-blocking background task in `main.py` instead of gating startup.

1. Create a new Space at [huggingface.co/new-space](https://huggingface.co/new-space) with **Docker** as the SDK.
2. A Space is its own git repository and expects its `Dockerfile` at the repo root — ours lives at `backend/Dockerfile`. Push just that subdirectory:
   ```bash
   git remote add hf-space https://huggingface.co/spaces/<user>/<space-name>
   git subtree push --prefix backend hf-space main
   ```
3. HF Spaces reads its config from YAML front matter in a `README.md` at the Space root. Ours is committed at `backend/README.md`, so the CD sync ships it automatically — reproduced here for reference:
   ```
   ---
   title: AI Career Hub API
   emoji: 🚀
   colorFrom: indigo
   colorTo: blue
   sdk: docker
   app_port: 8000
   ---
   ```
   HF defaults to port 7860 — `app_port: 8000` maps it to our uvicorn port.

### Secrets

Set these as **Space secrets** (Settings → Variables and secrets) — they become runtime environment variables, the same role `.env.prod` plays on the AWS path:

```
POSTGRES_SERVER / POSTGRES_USER / POSTGRES_PASSWORD / POSTGRES_DB    (Neon)
DB_SSLMODE=require
REDIS_HOST / REDIS_PORT / REDIS_PASSWORD                             (Upstash)
REDIS_SSL=true
REDIS_DB_TASKS=0 / REDIS_DB_DENYLIST=0     (Upstash supports only database 0)
VECTOR_BACKEND=qdrant
QDRANT_URL / QDRANT_API_KEY / QDRANT_COLLECTION
GROQ_API_KEY
SECRET_KEY                (must be ≥ 32 characters)
ADMIN_SECRET              (must be ≥ 32 characters — required for /admin/* lifecycle endpoints)
ALLOWED_ORIGINS           the frontend's *.streamlit.app URL
PRODUCTION=true
```

> Expect a first-boot crash-loop: `Settings()` in `config.py` fails fast on any missing required var (`SECRET_KEY`, `POSTGRES_*`, ...). Set all of the secrets above, then restart the Space from the UI.

### Frontend on Streamlit Community Cloud

1. Deploy from [share.streamlit.io](https://share.streamlit.io) pointing at this repo, with main file path `frontend/app.py`. `frontend/Dockerfile` isn't used here — Community Cloud runs the app from source.
2. Set one secret: `API_URL=https://<space>.hf.space/api/v1`. `frontend/api_client.py` already reads `API_URL` from the environment (it defaults to `http://api:8000/api/v1`, the Docker Compose service name, which doesn't apply here).
3. Pin the Python version — see below.
4. Back on the HF side, set `ALLOWED_ORIGINS` to this app's `*.streamlit.app` URL so the FastAPI CORS middleware accepts requests from it.

### Python version pin

Chose **not** to add a `.python-version` file at `frontend/` or the repo root. Streamlit Community Cloud's own docs describe the Python version as a choice made in the **Advanced settings** dialog at deploy time (changed later only by deleting and redeploying the app). Neither that page nor the recognized-dependency-file docs (`requirements.txt`, `pyproject.toml`, `environment.yml`, `Pipfile`, `uv.lock`) mention a `.python-version` or `runtime.txt` file controlling it. A committed file Streamlit silently ignores would be worse than no file at all. So: when deploying, open **Advanced settings** and choose **Python 3.12**.

### Keep-warm

An external scheduler should ping `GET /health/warm` roughly every 6 hours to keep both free tiers from cold-sleeping, and trigger the daily lifecycle cleanup on the same cadence as [Document Lifecycle Cleanup](#document-lifecycle-cleanup) above. The repo ships two interchangeable implementations:

- **`.github/workflows/keepwarm.yml` (default)** — GitHub Actions crons: a 6-hourly warm and the daily cleanup, with `ADMIN_SECRET` read from the `free-prod` environment; a failed run emails the repo owner. No extra accounts. Caveats: schedules only fire from the default branch, run with some jitter, and GitHub pauses them after ~60 days without repo activity (it emails a warning first).
- **`infra/keep-warm/` (alternative)** — an equivalent Cloudflare Worker (exact cron timing + optional Discord alerting) for when Actions scheduling isn't wanted — see its `README.md`.
