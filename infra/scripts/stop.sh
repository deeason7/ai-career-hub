#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
#  stop.sh  —  Stop all portfolio compute in one command.
#  Usage:  bash infra/scripts/stop.sh
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

REGION="us-east-1"
RDS_ID="portfolio-db"
EC2_TAG="portfolio-server"

# ── Colors ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'; YELLOW='\033[1;33m'; GREEN='\033[0;32m'; NC='\033[0m'
info()    { echo -e "${YELLOW}[→]${NC} $1"; }
success() { echo -e "${GREEN}[✓]${NC} $1"; }
warn()    { echo -e "${RED}[!]${NC} $1"; }

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "   AI Career Hub — STOPPING STACK"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# ── Resolve EC2 instance ──────────────────────────────────────────────────
INSTANCE_ID=$(aws ec2 describe-instances \
  --filters "Name=tag:Name,Values=$EC2_TAG" \
  --query "Reservations[0].Instances[0].InstanceId" \
  --output text --region "$REGION" 2>/dev/null || echo "None")

EC2_STATE=$(aws ec2 describe-instances \
  --filters "Name=tag:Name,Values=$EC2_TAG" \
  --query "Reservations[0].Instances[0].State.Name" \
  --output text --region "$REGION" 2>/dev/null || echo "unknown")

# ── Stop EC2 ──────────────────────────────────────────────────────────────
if [[ "$EC2_STATE" == "running" ]]; then
  info "Stopping EC2 ($INSTANCE_ID)..."
  aws ec2 stop-instances --instance-ids "$INSTANCE_ID" --region "$REGION" > /dev/null
  success "EC2 stop signal sent."
elif [[ "$EC2_STATE" == "stopped" ]]; then
  success "EC2 already stopped."
else
  warn "EC2 state is '$EC2_STATE' — skipping."
fi

# ── Stop RDS ──────────────────────────────────────────────────────────────
RDS_STATE=$(aws rds describe-db-instances \
  --db-instance-identifier "$RDS_ID" \
  --query "DBInstances[0].DBInstanceStatus" \
  --output text --region "$REGION" 2>/dev/null || echo "unknown")

if [[ "$RDS_STATE" == "available" ]]; then
  info "Stopping RDS ($RDS_ID)..."
  aws rds stop-db-instance --db-instance-identifier "$RDS_ID" \
    --region "$REGION" > /dev/null
  success "RDS stop signal sent."
elif [[ "$RDS_STATE" == "stopped" ]]; then
  success "RDS already stopped."
else
  warn "RDS state is '$RDS_STATE' — skipping (may already be stopping)."
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e "${GREEN}  Stack is stopping. ~30s to fully off.${NC}"
echo "  💸 Saving ~\$0.029/hr while stopped."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
