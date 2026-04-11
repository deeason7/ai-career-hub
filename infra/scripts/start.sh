#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
#  start.sh  —  Start all portfolio compute and wait until app is live.
#  Usage:  bash infra/scripts/start.sh [--no-wait]
#
#  Without --no-wait: blocks until the health check endpoint returns 200
#                     then prints the live URL. Perfect for "demo ready" flow.
#  With    --no-wait: fires start signals and exits immediately.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

REGION="us-east-1"
RDS_ID="portfolio-db"
EC2_TAG="portfolio-server"
APP_URL="https://careerhub.deeason.com.np"
HEALTH_PATH="/health"
NO_WAIT=${1:-""}

# ── Colors ──────────────────────────────────────────────────────────────────
CYAN='\033[0;36m'; YELLOW='\033[1;33m'; GREEN='\033[0;32m'; RED='\033[0;31m'; NC='\033[0m'
info()    { echo -e "${CYAN}[→]${NC} $1"; }
success() { echo -e "${GREEN}[✓]${NC} $1"; }
warn()    { echo -e "${YELLOW}[!]${NC} $1"; }
error()   { echo -e "${RED}[✗]${NC} $1"; }

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "   AI Career Hub — STARTING STACK"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# ── Check current states ──────────────────────────────────────────────────
INSTANCE_ID=$(aws ec2 describe-instances \
  --filters "Name=tag:Name,Values=$EC2_TAG" \
  --query "Reservations[0].Instances[0].InstanceId" \
  --output text --region "$REGION")

EC2_STATE=$(aws ec2 describe-instances \
  --instance-ids "$INSTANCE_ID" \
  --query "Reservations[0].Instances[0].State.Name" \
  --output text --region "$REGION")

RDS_STATE=$(aws rds describe-db-instances \
  --db-instance-identifier "$RDS_ID" \
  --query "DBInstances[0].DBInstanceStatus" \
  --output text --region "$REGION" 2>/dev/null || echo "unknown")

# ── Start RDS first (takes longest — 3-4 min) ─────────────────────────────
if [[ "$RDS_STATE" == "stopped" ]]; then
  info "Starting RDS ($RDS_ID)... [takes ~3-4 min]"
  aws rds start-db-instance --db-instance-identifier "$RDS_ID" \
    --region "$REGION" > /dev/null
  success "RDS start signal sent."
elif [[ "$RDS_STATE" == "available" ]]; then
  success "RDS already running."
else
  warn "RDS state is '$RDS_STATE' — it may be starting already."
fi

# ── Start EC2 ──────────────────────────────────────────────────────────────
if [[ "$EC2_STATE" == "stopped" ]]; then
  info "Starting EC2 ($INSTANCE_ID)..."
  aws ec2 start-instances --instance-ids "$INSTANCE_ID" \
    --region "$REGION" > /dev/null
  success "EC2 start signal sent."
elif [[ "$EC2_STATE" == "running" ]]; then
  success "EC2 already running."
else
  warn "EC2 state is '$EC2_STATE' — it may be starting already."
fi

# ── Early exit if --no-wait ────────────────────────────────────────────────
if [[ "$NO_WAIT" == "--no-wait" ]]; then
  echo ""
  warn "Started without waiting. App will be ready in ~4-5 minutes."
  echo "  Check: curl -s $APP_URL$HEALTH_PATH"
  echo ""
  exit 0
fi

# ── Wait for EC2 to be reachable ──────────────────────────────────────────
echo ""
info "Waiting for EC2 to reach 'running' state..."
aws ec2 wait instance-running --instance-ids "$INSTANCE_ID" --region "$REGION"
success "EC2 is running."

PUBLIC_IP=$(aws ec2 describe-instances \
  --instance-ids "$INSTANCE_ID" \
  --query "Reservations[0].Instances[0].PublicIpAddress" \
  --output text --region "$REGION")
info "EC2 public IP: $PUBLIC_IP"

# ── Wait for app health check ─────────────────────────────────────────────
echo ""
info "Waiting for app to be healthy (polls every 10s, up to 5 min)..."
echo -e "  ${YELLOW}Note: Docker containers need ~60s after EC2 is running.${NC}"
echo ""

ELAPSED=0
MAX_WAIT=300
APP_READY=false

while [[ $ELAPSED -lt $MAX_WAIT ]]; do
  HTTP_CODE=$(curl -sk -o /dev/null -w "%{http_code}" \
    "$APP_URL$HEALTH_PATH" 2>/dev/null || echo "000")

  if [[ "$HTTP_CODE" == "200" ]]; then
    APP_READY=true
    break
  fi

  # Also try via raw IP in case DNS isn't propagated
  HTTP_CODE_IP=$(curl -sk -o /dev/null -w "%{http_code}" \
    "http://$PUBLIC_IP$HEALTH_PATH" 2>/dev/null || echo "000")

  if [[ "$HTTP_CODE_IP" == "200" ]]; then
    APP_READY=true
    break
  fi

  printf "  [%ds] HTTP %s — still starting..." "$ELAPSED" "$HTTP_CODE"
  sleep 10
  ELAPSED=$((ELAPSED + 10))
  printf "\r"
done

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if [[ "$APP_READY" == "true" ]]; then
  echo -e "${GREEN}  🚀 App is LIVE and healthy!${NC}"
  echo ""
  echo "  🌐 $APP_URL"
  echo "  📡 Direct IP: http://$PUBLIC_IP"
else
  error "App didn't respond in ${MAX_WAIT}s."
  echo "  Manually check: curl -s http://$PUBLIC_IP$HEALTH_PATH"
  echo "  Or SSM in:  aws ssm start-session --target $INSTANCE_ID --region $REGION"
fi
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
