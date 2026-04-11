# Deployment Runbook

Production deployment for AI Career Hub on AWS. Last updated: 2026-04-11 (v2.6.0).

---

## Current State

| Component | Status | Notes |
|-----------|--------|-------|
| EC2 stack | **On-demand** | Sleeps when idle. Boots automatically when someone visits (Wake-on-Visit, ~90s). Auto-stops after 90 min of inactivity |
| RDS PostgreSQL | **On-demand** | Starts/stops alongside EC2 via Lambda wake controller |
| Business Hours | **Live** | EC2 + RDS auto-start at 9 AM ET Mon–Fri; auto-stop at 6 PM ET (instant load for recruiters) |
| Domain | **Live** | `careerhub.deeason.com.np` |
| TLS | **Live** | HTTPS via Let's Encrypt certbot DNS-01, Docker Nginx SSL termination |
| Wake on Visit | **Live** | Route 53 failover → CloudFront → S3 splash page → Lambda boots EC2+RDS |
| Auto-Sleep | **Live** | EventBridge Scheduler stops EC2+RDS 90 min after each wake (off-hours) |
| Boot Deploy | **Live** | systemd service: `git pull + docker compose up` runs on every EC2 boot |
| CI | **Live** | GitHub Actions: ruff lint + pytest on push to `main`/`develop` |
| Pre-commit | **Live** | ruff lint+format + hygiene hooks — install with `pre-commit install` |

---

## AWS Infrastructure

### EC2

- **Instance type:** t3.small (Ubuntu 24.04 LTS)
- **Region:** us-east-1
- **Tag:** `Name=portfolio-server`
- **IAM role:** Scoped to SSM Parameter Store (`/portfolio/*` prefix) + ECR pull + CloudWatch logs
- **Access:** AWS SSM Session Manager — no SSH keys, no port 22

```bash
# Connect to EC2
INSTANCE_ID=$(aws ec2 describe-instances \
  --filters "Name=tag:Name,Values=portfolio-server" \
            "Name=instance-state-name,Values=running" \
  --query "Reservations[0].Instances[0].InstanceId" \
  --output text --region us-east-1)
aws ssm start-session --target $INSTANCE_ID --region us-east-1
# Switch to ubuntu user once inside
sudo su - ubuntu
```

### RDS

- **Identifier:** `portfolio-db`
- **Engine:** PostgreSQL 16
- **Instance class:** db.t3.micro
- **Subnet:** Private VPC — not publicly reachable
- **Credentials:** Stored in SSM, never in source code

### ECR

Two repositories in `us-east-1`:
- `careerhub-backend` — FastAPI + Alembic image (~3 GB uncompressed, `linux/amd64`)
- `careerhub-frontend` — Streamlit image (~180 MB, `linux/amd64`)

Images are built on the developer's Mac with `--platform linux/amd64` to target the x86_64 EC2.  
**Disk note:** Always run `docker image prune -f` after pulling new images on EC2 to prevent disk exhaustion.

### Secrets (SSM Parameter Store)

All parameters live under `/portfolio/careerhub/`. The EC2 instance role has read-only access. `pull-secrets.sh` reads the entire prefix and writes `.env.prod` at deploy time.

```
/portfolio/careerhub/POSTGRES_SERVER
/portfolio/careerhub/POSTGRES_USER
/portfolio/careerhub/POSTGRES_PASSWORD
/portfolio/careerhub/POSTGRES_DB
/portfolio/careerhub/POSTGRES_PORT
/portfolio/careerhub/SECRET_KEY
/portfolio/careerhub/GROQ_API_KEY
/portfolio/careerhub/ALLOWED_ORIGINS
/portfolio/careerhub/PRODUCTION
/portfolio/careerhub/SENTRY_DSN        # optional — add for Sentry error tracking
```

### DNS

- **Registrar:** Mercantile (.np registry, Nepal)
- **DNS hosted zone:** AWS Route 53 (`deeason.com.np`)
- **Record:** `careerhub.deeason.com.np → 34.234.125.14` (type A, TTL 300)
- **Nameservers:** Delegated from Mercantile to Route 53

### IAM

- **Developer user:** `deeason-dev`
- **Policy:** `portfolio-developer` (least-privilege — scoped to `portfolio-*` resources only)
- **Permissions:** EC2 start/stop, RDS start/stop/modify, SSM `/portfolio/*`, ECR careerhub repos, Route53 deeason.com.np zone, CloudTrail read, Lambda code update
- **Additional policy:** `portfolio-scheduler-management` — `scheduler:CreateSchedule / UpdateSchedule / DeleteSchedule / GetSchedule` on the two named business-hours schedules + `iam:PassRole` on `portfolio-wake-scheduler-role`
- **MFA:** Required on both root and `deeason-dev`
- **Root:** MFA enabled, no access keys — never used for daily operations

Additional roles (created via root console):
- `portfolio-wake-lambda-role` — Lambda execution role. Inline policies: EC2/RDS start/stop, scheduler create/delete/describe
- `portfolio-wake-scheduler-role` — EventBridge Scheduler role. Inline policy: invoke `portfolio-wake-controller`

To add `portfolio-scheduler-management` to `deeason-dev` (run as root/admin):
```bash
aws iam put-user-policy \
  --user-name deeason-dev \
  --policy-name portfolio-scheduler-management \
  --policy-document '{"Version":"2012-10-17","Statement":[{"Sid":"ManageBusinessHoursSchedules","Effect":"Allow","Action":["scheduler:CreateSchedule","scheduler:UpdateSchedule","scheduler:DeleteSchedule","scheduler:GetSchedule"],"Resource":["arn:aws:scheduler:us-east-1:346657261080:schedule/default/portfolio-business-hours-start","arn:aws:scheduler:us-east-1:346657261080:schedule/default/portfolio-business-hours-stop"]},{"Sid":"PassSchedulerRole","Effect":"Allow","Action":"iam:PassRole","Resource":"arn:aws:iam::346657261080:role/portfolio-wake-scheduler-role","Condition":{"StringEquals":{"iam:PassedToService":"scheduler.amazonaws.com"}}}]}'
```

### Monitoring

- **CloudWatch:** All containers log to `/portfolio/careerhub-backend`, `/portfolio/careerhub-frontend`, `/portfolio/careerhub-nginx`
- **Billing:** Daily budget alert at $2/day → `deeasonsitaula5@gmail.com` (configured in AWS Budgets console)
- **Lambda logs:** `/aws/lambda/portfolio-wake-controller`

---

## Standard Deploy (after initial setup)

Run from your local machine when you have new code to deploy:

```bash
# 1. Build and push images (M-series Mac needs --platform linux/amd64)
export ECR_REGISTRY=$(aws sts get-caller-identity --query Account --output text).dkr.ecr.us-east-1.amazonaws.com
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin $ECR_REGISTRY

docker build --platform linux/amd64 -t $ECR_REGISTRY/careerhub-backend:latest ./backend
docker push $ECR_REGISTRY/careerhub-backend:latest

docker build --platform linux/amd64 -t $ECR_REGISTRY/careerhub-frontend:latest ./frontend
docker push $ECR_REGISTRY/careerhub-frontend:latest

# 2. Connect to EC2 and run deploy
INSTANCE_ID=$(aws ec2 describe-instances \
  --filters "Name=tag:Name,Values=portfolio-server" \
            "Name=instance-state-name,Values=running" \
  --query "Reservations[0].Instances[0].InstanceId" \
  --output text --region us-east-1)
aws ssm start-session --target $INSTANCE_ID --region us-east-1

# 3. On EC2 (as ubuntu user)
sudo su - ubuntu
cd ~/ai-career-hub && git pull origin main
bash infra/scripts/deploy.sh
```

### Deploy the wake-page Lambda + S3 (when wake_controller.py or index.html change)

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
aws cloudfront create-invalidation \
  --distribution-id E31DN2OV7E4KZ5 --paths "/*" --region us-east-1
```

---

## TLS / HTTPS ✅ Live

Let's Encrypt certificate issued via DNS-01 challenge (certbot + Route 53 plugin). Nginx inside Docker handles SSL termination.

- **Certificate path (on EC2):** `/etc/letsencrypt/live/careerhub.deeason.com.np/`
- **Nginx config:** `infra/nginx/nginx.conf` (mounted read-only into the nginx container)
- **Auto-renewal:** certbot systemd timer renews the cert. After renewal, run:

```bash
aws ssm start-session --target i-07709e34044f62ef4 --region us-east-1
sudo su - ubuntu
sudo certbot renew
docker compose -f docker-compose.prod.yml restart nginx
curl -sk https://localhost/health
```

---

## Business Hours Scheduler

EC2 + RDS automatically start at 9 AM ET and stop at 6 PM ET, Mon–Fri.  
This ensures instant page loads (no wake-page wait) during core recruiter hours.

**Schedule (America/New_York):**
| Rule | Cron | Action |
|------|------|--------|
| `portfolio-business-hours-start` | `cron(0 9 ? * MON-FRI *)` | `action:wake` → `handle_scheduled_wake()` |
| `portfolio-business-hours-stop` | `cron(0 18 ? * MON-FRI *)` | `action:stop` → `handle_auto_stop()` |

**IAM prerequisite:** Add `portfolio-scheduler-management` policy to `deeason-dev` (see IAM section above).

**Install / update schedules:**
```bash
bash infra/scripts/setup-business-hours.sh
```

**Verify:**
```bash
aws scheduler get-schedule --name portfolio-business-hours-start --region us-east-1
aws scheduler get-schedule --name portfolio-business-hours-stop  --region us-east-1
```

**Remove:**
```bash
bash infra/scripts/setup-business-hours.sh --remove
```

**Cost impact:** ~$7.50/month (9 hrs × 5 days × $0.021/hr EC2 + $0.016/hr RDS × ~4.3 weeks).  
Off-hours Wake-on-Visit adds ~$0 (free-tier Lambda/CF) + ~$0.05–0.20/day of actual off-hours use.

---

## Wake on Visit — Architecture ✅ Live

```
Visitor → careerhub.deeason.com.np
       → Route 53 health check
       ├─ EC2 healthy  → nginx → app (HTTPS)
       └─ EC2 sleeping → CloudFront → S3 wake page
                                   ↓
                         API Gateway → Lambda (portfolio-wake-controller)
                         (starts EC2 + RDS, schedules 90-min auto-stop)
                                   ↓
                         ~90s boot time → redirect to live app
                                   ↓
                         90 min later → EventBridge auto-stops EC2+RDS
```

**Key files:**
| File | Purpose |
|------|---------|
| `infra/wake-page/index.html` | S3 splash page — animated status, RDS auto-rewake, DNS confirmation without blind redirect |
| `infra/wake-page/wake_controller.py` | Lambda: handles `/wake`, `/status`, `action:stop`, `action:wake` |
| `infra/scripts/setup-wake-on-visit.sh` | One-time provisioning (S3, Lambda, API GW, CF, R53) |
| `infra/scripts/setup-business-hours.sh` | Install/update business-hours recurring EventBridge Scheduler rules |
| `infra/scripts/install-boot-deploy.sh` | Installs systemd service on EC2 for auto git pull + compose up |
| `infra/nginx/nginx.conf` | Docker nginx: SSL termination, gzip compression, 300s proxy timeout |

### Lambda routing

`portfolio-wake-controller` dispatches based on the event shape:

| Event | Handler | Notes |
|-------|---------|-------|
| HTTP POST `/wake` | `handle_wake()` | Starts EC2+RDS, resets 90-min idle auto-stop timer |
| HTTP GET `/status` | `handle_status()` | Returns `{ec2, rds, app}` — EC2+RDS checked in parallel |
| `{action: "stop"}` | `handle_auto_stop()` | Stops EC2+RDS. Fired by idle timer OR 6 PM ET EventBridge cron |
| `{action: "wake"}` | `handle_scheduled_wake()` | Starts EC2+RDS. Fired by 9 AM ET EventBridge cron. Does NOT set idle timer |

### Auto-Sleep (EventBridge Scheduler)

Every HTTP `/wake` call schedules a one-time EventBridge Scheduler rule:
- **Timer:** 90 minutes from last wake call
- **Action:** Lambda stops EC2 + RDS (`action: stop` payload)
- **Reset:** each new `/wake` resets the timer (recruiter re-visits = 90 more minutes)
- **Self-deletes:** the schedule is removed after it fires (`ActionAfterCompletion: DELETE`)

Required Lambda env vars:
```
LAMBDA_ARN         = arn:aws:lambda:us-east-1:346657261080:function:portfolio-wake-controller
SCHEDULER_ROLE_ARN = arn:aws:iam::346657261080:role/portfolio-wake-scheduler-role
AUTO_STOP_MINUTES  = 90
```

### Boot Deploy Service

Installed on EC2 as `app-boot-deploy.service` (systemd oneshot). On every EC2 start:
1. `git pull origin main` — picks up latest config/code changes
2. `docker compose -f docker-compose.prod.yml up -d --remove-orphans` — recreates containers
3. `docker image prune -f` — prevents disk exhaustion on the 30 GB EC2 root volume

To install/re-install on a new EC2:
```bash
aws ssm start-session --target i-07709e34044f62ef4 --region us-east-1
sudo su - ubuntu && cd ~/ai-career-hub
bash infra/scripts/install-boot-deploy.sh
```

---

## Developer Tooling

### ruff (lint + format)

`ruff.toml` is in `backend/`. Rules: E, F, W, I (isort), B (bugbear), UP (pyupgrade).

```bash
# Check
ruff check backend/

# Auto-fix (UP007=Optional→X|None, UP017=timezone.utc→datetime.UTC, UP035=typing→collections.abc, I=isort)
ruff check --fix backend/

# Format (black-compatible)
ruff format backend/
```

CI runs `ruff check backend/` on every push. Failing ruff = failing CI.

### pre-commit

`.pre-commit-config.yaml` at repo root. Hooks:
- `ruff` (lint + auto-fix) and `ruff-format` — backend Python only
- `trailing-whitespace`, `end-of-file-fixer`, `check-yaml`, `check-json`
- `check-merge-conflict`, `check-added-large-files` (500 KB limit)
- `mixed-line-ending` (enforces LF)

```bash
# Install once
pip install -r backend/requirements.dev.txt
pre-commit install

# Run manually against all files
pre-commit run --all-files

# Update hook versions
pre-commit autoupdate
```

---

## Billing Controls

Expected costs with current setup:

| Mode | Monthly estimate |
|------|-----------------|
| Business hours (9 AM–6 PM ET, Mon–Fri) | ~$7.00 |
| Off-hours Wake-on-Visit overhead | ~$0.50 |
| Lambda + API GW + S3 + CloudFront | ~$0 (free tier) |
| Route 53 health check | ~$0.50 |
| **Total** | **~$8/month** |

Manual overrides when needed:

```bash
# Force stop immediately
bash infra/scripts/stop.sh

# Force start (for maintenance/SSM access)
bash infra/scripts/start.sh
aws ssm start-session --target i-07709e34044f62ef4 --region us-east-1

# Test business-hours Lambda (wake)
aws lambda invoke --function-name portfolio-wake-controller \
  --payload '{"action":"wake"}' --region us-east-1 /dev/stdout

# Test business-hours Lambda (stop)
aws lambda invoke --function-name portfolio-wake-controller \
  --payload '{"action":"stop"}' --region us-east-1 /dev/stdout
```

---

## Credential Rotation

Rotate all secrets when a leak is suspected or on a scheduled basis (every 90 days recommended).

### Rotate RDS password + SSM

```bash
NEW_PASS=$(python3 -c "import secrets, string; print(''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(32)))")

aws rds modify-db-instance \
  --db-instance-identifier portfolio-db \
  --master-user-password "$NEW_PASS" \
  --apply-immediately --region us-east-1

aws ssm put-parameter \
  --name "/portfolio/careerhub/POSTGRES_PASSWORD" \
  --value "$NEW_PASS" --type SecureString --overwrite --region us-east-1

# Wait 3 min for RDS to fully apply, then force-recreate (restart does NOT re-read env_file)
sleep 180
bash infra/scripts/pull-secrets.sh
ECR_REGISTRY=$(aws sts get-caller-identity --query Account --output text).dkr.ecr.us-east-1.amazonaws.com \
  docker compose -f docker-compose.prod.yml up -d --force-recreate --pull never api
```

### Rotate JWT secret key

```bash
NEW_SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
aws ssm put-parameter \
  --name "/portfolio/careerhub/SECRET_KEY" \
  --value "$NEW_SECRET" --type SecureString --overwrite --region us-east-1
# Note: rotating SECRET_KEY invalidates all active user sessions.
# Force-recreate api container after updating SSM.
```

### Rotate Groq API key

1. Go to console.groq.com → API Keys → create new → delete old
2. `aws ssm put-parameter --name "/portfolio/careerhub/GROQ_API_KEY" --value "NEW_KEY" --type SecureString --overwrite --region us-east-1`
3. Force-recreate api container

### Rotate IAM access keys

```bash
aws iam create-access-key --user-name deeason-dev
aws configure set aws_access_key_id NEW_KEY_ID
aws configure set aws_secret_access_key NEW_SECRET
aws iam delete-access-key --user-name deeason-dev --access-key-id OLD_KEY_ID
```

Do this in a terminal session NOT connected to any AI assistant to avoid credential exposure.

---

## Post-Setup Security Hardening — ✅ Completed

| Step | Status | Details |
|------|--------|---------|
| IAM least-privilege | ✅ | `portfolio-developer` + `portfolio-scheduler-management` — scoped to named resources |
| Daily budget | ✅ | $2/day alert → `deeasonsitaula5@gmail.com` (AWS Budgets console) |
| HTTPS / TLS | ✅ | Certbot DNS-01, Docker nginx SSL, `infra/nginx/nginx.conf` |
| Boot deploy service | ✅ | `app-boot-deploy.service` installed on EC2 |
| Auto-sleep (idle) | ✅ | EventBridge Scheduler stops EC2+RDS 90 min after wake |
| Business hours | ✅ | EventBridge Scheduler start 9 AM / stop 6 PM ET, Mon–Fri |
| Ruff CI | ✅ | GitHub Actions runs `ruff check backend/` on every push |
| Pre-commit | ✅ | `.pre-commit-config.yaml` — ruff + hygiene hooks |

---

## Smoke Tests

```bash
# Health check (through nginx)
curl -sk https://careerhub.deeason.com.np/health

# Health check (direct EC2 IP, bypasses Route 53 DNS)
curl -sk http://34.234.125.14/health

# Container status
docker compose -f docker-compose.prod.yml ps

# Tail logs
docker compose -f docker-compose.prod.yml logs -f --tail 50

# Lambda status check
curl -s https://$(aws apigatewayv2 get-apis --region us-east-1 \
  --query 'Items[?Name==`portfolio-wake-api`].ApiEndpoint' --output text)/status
```
