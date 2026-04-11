#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
#  setup-business-hours.sh
#
#  Installs recurring EventBridge Scheduler rules that keep EC2 + RDS alive
#  during business hours (Mon–Fri, 9 AM – 6 PM America/New_York).
#
#  Uses the EXISTING portfolio-wake-controller Lambda — no new IAM roles or
#  Lambda functions are created.
#
#  Money:  ~$7.50/mo  vs  $27/mo always-on  vs  $1-2/mo wake-on-visit
#  UX:     instant page load during 9-6 ET weekdays (recruiters / interviews)
#          Wake-on-Visit (60-90s) handles evening / weekend visits
#
#  ── IAM prerequisites for deeason-dev (add via console / root ONCE) ─────────
#  These are narrowly scoped (least-privilege) to the two named schedules:
#
#   {
#     "Effect": "Allow",
#     "Action": [
#       "scheduler:CreateSchedule",
#       "scheduler:UpdateSchedule",
#       "scheduler:DeleteSchedule",
#       "scheduler:GetSchedule"
#     ],
#     "Resource": [
#       "arn:aws:scheduler:us-east-1:346657261080:schedule/default/portfolio-business-hours-start",
#       "arn:aws:scheduler:us-east-1:346657261080:schedule/default/portfolio-business-hours-stop"
#     ]
#   },
#   {
#     "Effect": "Allow",
#     "Action": "iam:PassRole",
#     "Resource": "arn:aws:iam::346657261080:role/portfolio-wake-scheduler-role",
#     "Condition": {
#       "StringEquals": { "iam:PassedToService": "scheduler.amazonaws.com" }
#     }
#   }
#
#  Usage:
#    bash infra/scripts/setup-business-hours.sh           # install / update
#    bash infra/scripts/setup-business-hours.sh --remove  # uninstall
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

REGION="us-east-1"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
LAMBDA_ARN="arn:aws:lambda:${REGION}:${ACCOUNT_ID}:function:portfolio-wake-controller"
SCHEDULER_ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/portfolio-wake-scheduler-role"

START_SCHEDULE="portfolio-business-hours-start"
STOP_SCHEDULE="portfolio-business-hours-stop"
ACTION=${1:-""}

GREEN='\033[0;32m'; CYAN='\033[0;36m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()    { echo -e "${CYAN}[→]${NC} $1"; }
success() { echo -e "${GREEN}[✓]${NC} $1"; }
warn()    { echo -e "${YELLOW}[!]${NC} $1"; }

# ── Remove mode ────────────────────────────────────────────────────────────────
if [[ "$ACTION" == "--remove" ]]; then
  warn "Removing business-hours schedules..."
  aws scheduler delete-schedule --name "$START_SCHEDULE" --region "$REGION" 2>/dev/null \
    && success "$START_SCHEDULE deleted." \
    || warn "$START_SCHEDULE not found (already removed?)."
  aws scheduler delete-schedule --name "$STOP_SCHEDULE" --region "$REGION" 2>/dev/null \
    && success "$STOP_SCHEDULE deleted." \
    || warn "$STOP_SCHEDULE not found (already removed?)."
  echo ""
  echo "  Wake-on-Visit is still active for all off-hours visits."
  exit 0
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "   AI Career Hub — Business Hours Scheduler"
echo "   Start: 9:00 AM ET, Mon–Fri  (instant load for recruiters)"
echo "   Stop:  6:00 PM ET, Mon–Fri  (Wake-on-Visit takes over)"
echo "   Cost:  ~\$7.50/mo vs \$27/mo always-on"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# ── Upsert helper: update if exists, create if not ────────────────────────────
upsert_schedule() {
  local name=$1 cron=$2 action=$3

  # Build target JSON via a heredoc → temp file.
  # WHY: printf in bash converts \" → " (strips backslashes), producing invalid
  # JSON when the Input field contains nested JSON.  A heredoc writes \" literally
  # so the file contains the properly-escaped JSON the AWS CLI expects:
  #   "Input":"{\"action\":\"wake\"}"
  # AWS CLI reads it via file:// and parses it as a JSON-encoded string.
  local tmpfile
  tmpfile=$(mktemp)   # no template — works on both macOS and Linux
  # shellcheck disable=SC2064
  trap "rm -f $tmpfile" RETURN

  cat > "$tmpfile" << TARGETJSON
{"Arn":"${LAMBDA_ARN}","RoleArn":"${SCHEDULER_ROLE_ARN}","Input":"{\"action\":\"${action}\"}"}
TARGETJSON

  if aws scheduler get-schedule --name "$name" --region "$REGION" &>/dev/null; then
    info "Updating existing schedule: $name ..."
    aws scheduler update-schedule \
      --name                         "$name" \
      --schedule-expression          "cron($cron)" \
      --schedule-expression-timezone "America/New_York" \
      --target                       "file://$tmpfile" \
      --flexible-time-window         '{"Mode":"OFF"}' \
      --state                        ENABLED \
      --region                       "$REGION" > /dev/null
  else
    info "Creating schedule: $name ..."
    aws scheduler create-schedule \
      --name                         "$name" \
      --schedule-expression          "cron($cron)" \
      --schedule-expression-timezone "America/New_York" \
      --target                       "file://$tmpfile" \
      --flexible-time-window         '{"Mode":"OFF"}' \
      --state                        ENABLED \
      --region                       "$REGION" > /dev/null
  fi
  success "$name  ->  action:${action}  at  cron($cron) ET"
}

# ── Install schedules ──────────────────────────────────────────────────────────
# 9:00 AM ET Mon-Fri  →  wake_controller.lambda_handler({action:"wake"})
#                     →  handle_scheduled_wake() starts EC2 + RDS
upsert_schedule "$START_SCHEDULE" "0 9 ? * MON-FRI *" "wake"

# 6:00 PM ET Mon-Fri  →  wake_controller.lambda_handler({action:"stop"})
#                     →  handle_auto_stop() stops EC2 + RDS
upsert_schedule "$STOP_SCHEDULE"  "0 18 ? * MON-FRI *" "stop"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e "${GREEN}  ✅ Business Hours Scheduler Installed${NC}"
echo ""
echo "  ☀️  EC2 + RDS start :  9:00 AM ET  Mon–Fri"
echo "  🌙  EC2 + RDS stop  :  6:00 PM ET  Mon–Fri"
echo "  🔔  Off-hours       :  Wake-on-Visit (60-90s cold boot on demand)"
echo "  💸  Monthly cost    :  ~\$7.50  (was \$1-2 WoV / \$27 always-on)"
echo ""
echo "  To verify schedules:"
echo "    aws scheduler get-schedule --name $START_SCHEDULE --region $REGION"
echo "    aws scheduler get-schedule --name $STOP_SCHEDULE  --region $REGION"
echo ""
echo "  To remove:"
echo "    bash infra/scripts/setup-business-hours.sh --remove"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
