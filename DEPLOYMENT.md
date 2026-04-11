# Deployment Runbook

Production deployment for AI Career Hub on AWS. Last updated: 2026-04-06.

---

## Current State

| Component | Status | Notes |
|-----------|--------|-------|
| EC2 stack | **On-demand** | Sleeps when idle. Starts automatically when someone visits the domain (Wake on Visit) |
| RDS PostgreSQL | **On-demand** | Starts with EC2 via Lambda wake controller |
| Domain | **Live** | `careerhub.deeason.com.np` resolves correctly |
| TLS | **Live** | HTTPS via Let's Encrypt certbot DNS-01 |
| Wake on Visit | **Live** | Route 53 failover → CloudFront → S3 splash page → Lambda boots EC2+RDS |

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
- **Permissions:** EC2 start/stop, RDS start/stop/modify, SSM `/portfolio/*`, ECR careerhub repos, Route53 deeason.com.np zone, CloudTrail read
- **MFA:** Required on both root and `deeason-dev`
- **Root:** MFA enabled, no access keys — never used for daily operations

To update the policy (requires root console): IAM → Policies → `portfolio-developer` → Edit.

### Monitoring

- **CloudWatch:** All containers log to `/portfolio/careerhub-backend`, `/portfolio/careerhub-frontend`, `/portfolio/careerhub-nginx`
- **Billing:** Daily budget alert at $5/day + monthly alert at $40/month → `deeasonsitaula5@gmail.com`

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

## Pending: TLS Setup

Once `nslookup careerhub.deeason.com.np 8.8.8.8` returns `34.234.125.14`:

```bash
# On EC2 — as ubuntu
# Install certbot with Route53 DNS plugin (EC2 role already has Route53 permissions)
sudo apt-get install -y python3-certbot-dns-route53

# Issue cert via DNS-01 challenge (no port 80 needed, more reliable)
sudo certbot certonly --dns-route53 \
  --domain careerhub.deeason.com.np \
  --agree-tos \
  --email deeasonsitaula5@gmail.com \
  --non-interactive

# Restore the HTTPS nginx config and docker-compose from git
cd ~/ai-career-hub
git pull origin main
git checkout nginx/nginx.conf
git checkout docker-compose.prod.yml

# Restart the full stack with HTTPS config
ECR_REGISTRY=$(aws sts get-caller-identity --query Account --output text).dkr.ecr.us-east-1.amazonaws.com \
  docker compose -f docker-compose.prod.yml up -d --force-recreate --pull never

# Verify
curl -s https://careerhub.deeason.com.np/health
```

Certbot auto-renewal runs via systemd timer. After each renewal, nginx must reload:
```bash
sudo certbot renew && docker compose -f docker-compose.prod.yml restart nginx
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

```bash
# Stop all compute (run from local machine)
bash infra/scripts/stop.sh

# Start it back up
bash infra/scripts/start.sh
# Then SSM in and run deploy.sh
```

Expected costs:
- **On-demand** (Wake on Visit active, ~5 hrs/month actual use): **~$1–2/month**
  - Lambda + API GW + S3 + CloudFront: ~$0 (free tier)
  - Route 53 health check: ~$0.50
  - EC2/RDS only when running: ~$0.10–0.50
- Always-on (for reference): EC2 t3.small ~$15/mo + RDS db.t3.micro ~$12/mo

---

## Wake on Visit Setup

Run once to deploy the full Wake on Visit infrastructure:

```bash
# Ensure EC2 is running before setup (health check needs a live target)
bash infra/scripts/start.sh --no-wait

# Full setup (~15 min, mostly waiting for CloudFront deployment)
bash infra/scripts/setup-wake-on-visit.sh

# After setup, stop EC2/RDS — visitors will wake it automatically
bash infra/scripts/stop.sh
```

The setup script is **idempotent** — re-run it safely if anything fails. State is saved in `infra/wake-page/.state`.

To remove everything: `bash infra/scripts/setup-wake-on-visit.sh --teardown`

---

## Post-Setup Security Hardening

Run these **after** `setup-wake-on-visit.sh` completes successfully.

### Step 1 — Shrink IAM policy (console, root login)

The `WakeOnVisitSetup` permissions were only needed for provisioning.
Replace the entire `WakeOnVisitSetup` block with this minimal operate-only version:

```json
,{
  "Sid": "WakeOnVisitOperate",
  "Effect": "Allow",
  "Action": [
    "s3:PutObject",
    "s3:GetObject",
    "lambda:UpdateFunctionCode",
    "lambda:GetFunction"
  ],
  "Resource": [
    "arn:aws:s3:::careerhub-wake-page/*",
    "arn:aws:lambda:us-east-1:ACCOUNT_ID:function:portfolio-wake-controller"
  ]
}
```

**IAM → Policies → portfolio-developer → Edit → replace `WakeOnVisitSetup` → Save**

### Step 2 — Tighten daily budget to $2/day

Normal daily spend after Wake on Visit ≈ $0.05. Alert at $2 catches any abuse early:

```bash
aws budgets create-budget \
  --account-id $(aws sts get-caller-identity --query Account --output text) \
  --budget '{
    "BudgetName": "daily-tight-cap",
    "BudgetLimit": {"Amount": "2", "Unit": "USD"},
    "TimeUnit": "DAILY",
    "BudgetType": "COST"
  }' \
  --notifications-with-subscribers '[{
    "Notification": {
      "NotificationType": "ACTUAL",
      "ComparisonOperator": "GREATER_THAN",
      "Threshold": 80
    },
    "Subscribers": [{"SubscriptionType":"EMAIL","Address":"deeasonsitaula5@gmail.com"}]
  }]'
```

### Step 3 — Set up HTTPS (certbot) on EC2

DNS now resolves. Run this once while EC2 is running:

```bash
# SSM into EC2
INSTANCE_ID=$(aws ec2 describe-instances \
  --filters "Name=tag:Name,Values=portfolio-server" \
  --query "Reservations[0].Instances[0].InstanceId" \
  --output text --region us-east-1)
aws ssm start-session --target $INSTANCE_ID --region us-east-1

# Inside EC2 (as ubuntu)
sudo su - ubuntu
sudo apt-get install -y python3-certbot-dns-route53
sudo certbot certonly --dns-route53 \
  --domain careerhub.deeason.com.np \
  --agree-tos --email deeasonsitaula5@gmail.com --non-interactive
cd ~/ai-career-hub
docker compose -f docker-compose.prod.yml restart nginx
curl -s https://careerhub.deeason.com.np/health  # should return {"status":"ok"}
```

### Step 4 — Stop EC2/RDS (let wake-on-visit take over)

```bash
bash infra/scripts/stop.sh
```

Visitors to `https://careerhub.deeason.com.np` will now see the wake page and boot the app automatically.

### Step 5 — Commit and push final state

```bash
git add -A
git commit -m "docs: post-setup security hardening notes"
git push origin main
```

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
