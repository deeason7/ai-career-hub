# Deployment Runbook

Production deployment for AI Career Hub on AWS. Last deployed: 2026-04-05.

---

## Current State

| Component | Status | Notes |
|-----------|--------|-------|
| EC2 stack | **Live** | All 4 containers running |
| RDS PostgreSQL | **Live** | 4 migrations applied |
| Domain | **Pending** | DNS propagating for `.np` — ETA 12-24h |
| TLS | **Pending** | Waiting on DNS before certbot |
| HTTP access | **Working** | `http://34.234.125.14` reachable now |

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
# On EC2 — as ubuntu (or with sudo)
sudo certbot certonly --standalone \
  --domain careerhub.deeason.com.np \
  --agree-tos \
  --email deeasonsitaula5@gmail.com \
  --non-interactive

# Restore the HTTPS nginx config from git
cd ~/ai-career-hub
git checkout nginx/nginx.conf
git checkout docker-compose.prod.yml

# Also update API_URL back to https in docker-compose.prod.yml
# Then restart nginx to load the certs
docker compose -f docker-compose.prod.yml restart nginx

# Verify
curl -s https://careerhub.deeason.com.np/health
```

Certbot auto-renewal is set up by default (systemd timer). After renewal, restart nginx:
```bash
sudo certbot renew && docker compose -f docker-compose.prod.yml restart nginx
```

---

## Billing Controls

```bash
# Stop all compute (run from local machine)
bash infra/scripts/stop.sh

# Start it back up
bash infra/scripts/start.sh
# Then SSM in and run deploy.sh
```

Expected costs at rest:
- EC2 t3.small: ~$0.50/day
- RDS db.t3.micro: ~$0.41/day
- Storage + misc: ~$0.10/day
- **Total: ~$1/day, ~$30/month**

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
