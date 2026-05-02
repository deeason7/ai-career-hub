# Deployment Guide — AI Career Hub

Production deployment on AWS. Platform version: **v3.0**.

---

## Table of Contents

1. [Current State](#current-state)
2. [AWS Infrastructure](#aws-infrastructure)
3. [Standard Deploy](#standard-deploy)
4. [Business Hours Scheduler](#business-hours-scheduler)
5. [Wake on Visit](#wake-on-visit)
6. [TLS / HTTPS](#tls--https)
7. [Developer Tooling](#developer-tooling)
8. [Billing Controls](#billing-controls)

---

## Current State

| Component | Status | Notes |
|---|---|---|
| EC2 stack | **On-demand** | Sleeps when idle. Boots automatically on visit (Wake-on-Visit, ~90s). Auto-stops after 90 min of inactivity |
| RDS PostgreSQL | **On-demand** | Starts and stops alongside EC2 via Lambda wake controller |
| Business Hours | **Live** | EC2 + RDS auto-start at 9 AM ET Mon–Fri; auto-stop at 6 PM ET |
| Domain | **Live** | `careerhub.deeason.com.np` |
| TLS | **Live** | HTTPS via Let's Encrypt (certbot DNS-01), nginx SSL termination in Docker |
| Wake on Visit | **Live** | Route 53 failover → CloudFront → S3 splash page → Lambda boots EC2 + RDS |
| Auto-Sleep | **Live** | EventBridge Scheduler stops EC2 + RDS 90 min after each wake (off-hours) |
| Boot Deploy | **Live** | systemd service: `git pull + docker compose up` runs on every EC2 boot |
| CI | **Live** | GitHub Actions: ruff lint + format check + pytest on push to `main` / `develop` |
| CD | **Live** | GitHub Actions: ECR build + push → EC2 SSM deploy on push to `main` |
| Pre-commit | **Live** | ruff lint + format + hygiene hooks — install with `pre-commit install` |

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
/portfolio/careerhub/SENTRY_DSN            (optional)
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
