# Deployment Runbook

Production deployment for AI Career Hub on AWS. Last updated: 2026-04-11.

---

## Current State

| Component | Status | Notes |
|-----------|--------|-------|
| EC2 stack | **On-demand** | Sleeps when idle. Auto-starts when someone visits (Wake on Visit). Auto-stops after 90 min |
| RDS PostgreSQL | **On-demand** | Starts alongside EC2 via Lambda wake controller. Auto-stopped with EC2 |
| Domain | **Live** | `careerhub.deeason.com.np` |
| TLS | **Live** | HTTPS via Let's Encrypt certbot DNS-01, Docker Nginx SSL termination |
| Wake on Visit | **Live** | Route 53 failover → CloudFront → S3 splash page → Lambda boots EC2+RDS |
| Auto-Sleep | **Live** | EventBridge Scheduler stops EC2+RDS 90 min after each wake — zero manual intervention |
| Boot Deploy | **Live** | systemd service: `git pull + docker compose up` runs on every EC2 boot |

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
- **MFA:** Required on both root and `deeason-dev`
- **Root:** MFA enabled, no access keys — never used for daily operations

Additional roles (created via root console):
- `portfolio-wake-lambda-role` — Lambda execution role. Inline policies: EC2/RDS start/stop, scheduler create/delete
- `portfolio-wake-scheduler-role` — EventBridge Scheduler role. Inline policy: invoke `portfolio-wake-controller`

To update policies: IAM → Roles → select role → Add permissions → Create inline policy.

### Monitoring

- **CloudWatch:** All containers log to `/portfolio/careerhub-backend`, `/portfolio/careerhub-frontend`, `/portfolio/careerhub-nginx`
- **Billing:** Daily budget alert at $2/day → `deeasonsitaula5@gmail.com` (configured in AWS Budgets console)
- **Auto-sleep logs:** Lambda CloudWatch log group `/aws/lambda/portfolio-wake-controller`

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
export ECR_REGISTRY=$(aws sts get-caller-identity --query Account --output text).dkr.ecr.us-east-1.amazonaws.com
docker compose -f docker-compose.prod.yml restart nginx
curl -sk https://localhost/health
```

---

## Credential Rotation

Rotate all secrets when a leak is suspected or on a scheduled basis (every 90 days recommended).

### Rotate RDS password + SSM

```bash
# Generate new password (alphanumeric, 32 chars)
NEW_PASS=$(python3 -c "import secrets, string; print(''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(32)))")

# Apply to RDS (takes ~2 min to propagate)
aws rds modify-db-instance \
  --db-instance-identifier portfolio-db \
  --master-user-password "$NEW_PASS" \
  --apply-immediately --region us-east-1

# Update SSM immediately
aws ssm put-parameter \
  --name "/portfolio/careerhub/POSTGRES_PASSWORD" \
  --value "$NEW_PASS" --type SecureString --overwrite --region us-east-1

# Wait 3 min for RDS to fully apply, then pull secrets and FORCE-RECREATE the container
# WARNING: `docker compose restart` does NOT re-read env_file.
# You MUST use --force-recreate to apply new credentials.
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
2. Update SSM: `aws ssm put-parameter --name "/portfolio/careerhub/GROQ_API_KEY" --value "NEW_KEY" --type SecureString --overwrite --region us-east-1`
3. Force-recreate api container

### Rotate IAM access keys

```bash
# Create new key, update ~/.aws/credentials, then delete old key
aws iam create-access-key --user-name deeason-dev
aws configure set aws_access_key_id NEW_KEY_ID
aws configure set aws_secret_access_key NEW_SECRET
aws iam delete-access-key --user-name deeason-dev --access-key-id OLD_KEY_ID
```

Do this rotation in a terminal session NOT connected to any AI assistant to avoid credential exposure.

---

## Billing Controls

The stack is **fully self-managing**:
- A visitor hitting `https://careerhub.deeason.com.np` triggers the wake flow automatically.
- After **90 minutes** of uptime, EventBridge Scheduler auto-stops EC2+RDS with no manual intervention.
- The nightly cron (EventBridge rule, 11 PM–8 AM UTC) provides an additional safety net.

Manual overrides if ever needed:

```bash
# Force stop immediately
bash infra/scripts/stop.sh

# Force start (for maintenance/SSM access)
bash infra/scripts/start.sh --no-wait
aws ssm start-session --target i-07709e34044f62ef4 --region us-east-1
```

Expected costs:
- **Normal operation** (Wake on Visit + auto-sleep): **~$1–2/month**
  - Lambda + API GW + S3 + CloudFront: ~$0 (free tier)
  - Route 53 health check: ~$0.50/month
  - EC2/RDS only when running: ~$0.05–0.20/day of actual use
- Always-on (for reference): EC2 t3.small ~$15/mo + RDS db.t3.micro ~$12/mo

---

## Wake on Visit — Architecture ✅ Live

```
Visitor → careerhub.deeason.com.np
       → Route 53 health check
       ├─ EC2 healthy  → nginx → app (HTTPS)
       └─ EC2 sleeping → CloudFront → S3 wake page
                                   ↓
                         API Gateway → Lambda
                         (starts EC2 + RDS, schedules 90-min auto-stop)
                                   ↓
                         ~90s boot time → redirect to live app
                                   ↓
                         90 min later → EventBridge auto-stops EC2+RDS
```

**Key files:**
| File | Purpose |
|------|---------|
| `infra/wake-page/index.html` | S3 splash page served by CloudFront |
| `infra/wake-page/wake_controller.py` | Lambda: start EC2+RDS, schedule auto-stop, poll health |
| `infra/scripts/setup-wake-on-visit.sh` | One-time provisioning (S3, Lambda, API GW, CF, R53) |
| `infra/scripts/schedule-sleep.sh` | Night-time EventBridge cron (11 PM–8 AM) |
| `infra/scripts/install-boot-deploy.sh` | Installs systemd service on EC2 for auto git pull + compose up |
| `infra/nginx/nginx.conf` | Docker nginx config with SSL termination |

**To re-provision from scratch:**
```bash
bash infra/scripts/start.sh --no-wait
bash infra/scripts/setup-wake-on-visit.sh
bash infra/scripts/stop.sh
```

The setup script is **idempotent** — safe to re-run. State saved in `infra/wake-page/.state`.

**To teardown:** `bash infra/scripts/setup-wake-on-visit.sh --teardown`

### Auto-Sleep (EventBridge Scheduler)

Every `/wake` API call schedules a one-time EventBridge Scheduler rule:
- **Timer:** 90 minutes from last wake call
- **Action:** Lambda stops EC2 + RDS (`action: stop` payload)
- **Reset:** each new `/wake` resets the timer (recruiter re-visits = 90 more minutes)
- **Self-deletes:** the schedule is removed after it fires (`ActionAfterCompletion: DELETE`)

Required Lambda env vars (set in AWS Console → Lambda → Configuration → Environment variables):
```
LAMBDA_ARN         = arn:aws:lambda:us-east-1:346657261080:function:portfolio-wake-controller
SCHEDULER_ROLE_ARN = arn:aws:iam::346657261080:role/portfolio-wake-scheduler-role
AUTO_STOP_MINUTES  = 90
```

### Boot Deploy Service

Installed on EC2 as `app-boot-deploy.service` (systemd oneshot). On every EC2 start:
1. `git pull origin main` — picks up latest config/code changes
2. `docker compose -f docker-compose.prod.yml up -d --remove-orphans` — recreates containers with new config

To install/re-install on a new EC2:
```bash
aws ssm start-session --target i-07709e34044f62ef4 --region us-east-1
sudo su - ubuntu && cd ~/ai-career-hub
bash infra/scripts/install-boot-deploy.sh
```

---

## Post-Setup Security Hardening — ✅ Completed (2026-04-11)

| Step | Status | Details |
|------|--------|---------|
| IAM least-privilege | ✅ | `WakeOnVisitSetup` replaced with minimal `WakeOnVisitOperate` policy |
| Daily budget | ✅ | $2/day alert → `deeasonsitaula5@gmail.com` (AWS Budgets console) |
| HTTPS / TLS | ✅ | Certbot DNS-01, Docker nginx SSL, `infra/nginx/nginx.conf` |
| Boot deploy service | ✅ | `app-boot-deploy.service` installed on EC2 |
| Auto-sleep | ✅ | EventBridge Scheduler stops EC2+RDS 90 min after wake |

---

## Smoke Tests

```bash
# Health check (through nginx)
curl -s http://localhost/health

# API docs reachable (should return 200 in dev, 404 in prod when PRODUCTION=true)
curl -s -o /dev/null -w "%{http_code}" http://localhost/api/v1/docs

# Container status
docker compose -f docker-compose.prod.yml ps

# Tail logs
docker compose -f docker-compose.prod.yml logs -f --tail 50
```
