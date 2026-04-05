#!/usr/bin/env bash
# deploy.sh
#
# Single-command production deploy for AI Career Hub on EC2.
#
# Run from the repo root:
#   bash infra/scripts/deploy.sh
#
# What it does (in order):
#   1. Sets ECR_REGISTRY so docker compose image references resolve correctly
#   2. Authenticates Docker with ECR (uses EC2 instance role — no keys needed)
#   3. Pulls secrets from SSM Parameter Store → writes .env.prod
#   4. Pulls latest images from ECR
#   5. Starts the full stack (redis, api, frontend, nginx)
#   6. Prunes old/dangling images to keep disk usage low
#
# Re-run this script on every deployment — it is fully idempotent.

set -euo pipefail

# ── Config ────────────────────────────────────────────────────────────────────
REGION="us-east-1"
COMPOSE_FILE="docker-compose.prod.yml"

# Derive AWS account ID at runtime — never hardcode it in source control.
# This also makes the script portable: it works for any AWS account that deploys this repo.
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_REGISTRY="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"

export ECR_REGISTRY   # docker compose reads this for image: ${ECR_REGISTRY}/... substitution

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  AI Career Hub — Production Deploy"
echo "  ECR: ${ECR_REGISTRY}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ── Step 1: Authenticate Docker with ECR ─────────────────────────────────────
echo ""
echo "▶ [1/5] Authenticating Docker with ECR..."
aws ecr get-login-password --region "${REGION}" \
  | docker login --username AWS --password-stdin "${ECR_REGISTRY}"

# ── Step 2: Pull secrets from SSM → .env.prod ────────────────────────────────
echo ""
echo "▶ [2/5] Pulling secrets from SSM Parameter Store..."
bash "$(dirname "$0")/pull-secrets.sh"

# ── Step 3: Pull latest images from ECR ──────────────────────────────────────
echo ""
echo "▶ [3/5] Pulling latest Docker images from ECR..."
docker compose -f "${COMPOSE_FILE}" pull

# ── Step 4: Start (or restart) the stack ─────────────────────────────────────
echo ""
echo "▶ [4/5] Starting production stack..."
docker compose -f "${COMPOSE_FILE}" up -d --remove-orphans

# ── Step 5: Prune old images ──────────────────────────────────────────────────
echo ""
echo "▶ [5/5] Pruning dangling images..."
docker image prune -f

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  ✅  Deploy complete!"
echo ""
echo "  Check status:  docker compose -f ${COMPOSE_FILE} ps"
echo "  Tail logs:     docker compose -f ${COMPOSE_FILE} logs -f"
echo "  Health check:  curl -s https://careerhub.deeason.com.np/health"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
