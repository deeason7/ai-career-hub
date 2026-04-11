#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
#  schedule-sleep.sh  —  Install AWS EventBridge rules to auto-stop at night
#                        and auto-start in the morning.
#
#  Schedule: Stop  at 11 PM CST (05:00 UTC)
#            Start at  8 AM CST (14:00 UTC)
#
#  This uses EventBridge + Lambda to stop/start EC2 & RDS automatically.
#  Run this ONCE from your local machine to set up the schedule.
#
#  Usage:  bash infra/scripts/schedule-sleep.sh [--remove]
#           --remove  deletes all created rules/functions
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

REGION="us-east-1"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ACTION=${1:-""}

GREEN='\033[0;32m'; CYAN='\033[0;36m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info()    { echo -e "${CYAN}[→]${NC} $1"; }
success() { echo -e "${GREEN}[✓]${NC} $1"; }
warn()    { echo -e "${YELLOW}[!]${NC} $1"; }

# ─── Remove mode ──────────────────────────────────────────────────────────
if [[ "$ACTION" == "--remove" ]]; then
  warn "Removing all sleep schedule resources..."
  aws events remove-targets --rule portfolio-stop-at-night --ids StopTarget --region "$REGION" 2>/dev/null || true
  aws events remove-targets --rule portfolio-start-in-morning --ids StartTarget --region "$REGION" 2>/dev/null || true
  aws events delete-rule --name portfolio-stop-at-night --region "$REGION" 2>/dev/null || true
  aws events delete-rule --name portfolio-start-in-morning --region "$REGION" 2>/dev/null || true
  aws lambda delete-function --function-name portfolio-scheduler-stop --region "$REGION" 2>/dev/null || true
  aws lambda delete-function --function-name portfolio-scheduler-start --region "$REGION" 2>/dev/null || true
  success "All schedule resources removed."
  exit 0
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "   Setting up Night Sleep Schedule"
echo "   Stop:  11 PM CST (05:00 UTC) every day"
echo "   Start:  8 AM CST (14:00 UTC) every day"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# ─── Step 1: Create/reuse IAM role for scheduler Lambdas ─────────────────
ROLE_NAME="portfolio-scheduler-lambda-role"
ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/${ROLE_NAME}"

if ! aws iam get-role --role-name "$ROLE_NAME" --region "$REGION" &>/dev/null; then
  info "Creating IAM role $ROLE_NAME..."
  aws iam create-role --role-name "$ROLE_NAME" \
    --assume-role-policy-document '{
      "Version": "2012-10-17",
      "Statement": [{
        "Effect": "Allow",
        "Principal": {"Service": "lambda.amazonaws.com"},
        "Action": "sts:AssumeRole"
      }]
    }' --region "$REGION" > /dev/null

  aws iam attach-role-policy --role-name "$ROLE_NAME" \
    --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole

  # Inline policy: EC2 + RDS start/stop
  aws iam put-role-policy --role-name "$ROLE_NAME" \
    --policy-name portfolio-scheduler-permissions \
    --policy-document '{
      "Version": "2012-10-17",
      "Statement": [
        {
          "Effect": "Allow",
          "Action": [
            "ec2:DescribeInstances",
            "ec2:StartInstances",
            "ec2:StopInstances",
            "rds:StartDBInstance",
            "rds:StopDBInstance",
            "rds:DescribeDBInstances"
          ],
          "Resource": "*"
        }
      ]
    }'
  success "IAM role created."
  sleep 10  # Wait for IAM propagation
else
  success "IAM role already exists — reusing."
fi

# ─── Step 2: Create Lambda zip packages inline ───────────────────────────
TMPDIR_LAMBDA=$(mktemp -d)
trap "rm -rf $TMPDIR_LAMBDA" EXIT

# Stop Lambda
cat > "$TMPDIR_LAMBDA/stop.py" << 'PYEOF'
import boto3, os
REGION = os.environ.get("REGION", "us-east-1")
EC2_TAG = os.environ.get("EC2_TAG", "portfolio-server")
RDS_ID = os.environ.get("RDS_ID", "portfolio-db")
ec2 = boto3.client("ec2", region_name=REGION)
rds = boto3.client("rds", region_name=REGION)

def lambda_handler(event, context):
    resp = ec2.describe_instances(Filters=[{"Name": "tag:Name", "Values": [EC2_TAG]}])
    instances = [i["InstanceId"] for r in resp["Reservations"] for i in r["Instances"]
                 if i["State"]["Name"] == "running"]
    if instances:
        ec2.stop_instances(InstanceIds=instances)
        print(f"Stopped EC2: {instances}")
    else:
        print("EC2 already stopped.")
    try:
        rds.stop_db_instance(DBInstanceIdentifier=RDS_ID)
        print(f"Stopped RDS: {RDS_ID}")
    except rds.exceptions.InvalidDBInstanceStateFault:
        print("RDS already stopped.")
    return {"status": "stopped"}
PYEOF

# Start Lambda
cat > "$TMPDIR_LAMBDA/start.py" << 'PYEOF'
import boto3, os
REGION = os.environ.get("REGION", "us-east-1")
EC2_TAG = os.environ.get("EC2_TAG", "portfolio-server")
RDS_ID = os.environ.get("RDS_ID", "portfolio-db")
ec2 = boto3.client("ec2", region_name=REGION)
rds = boto3.client("rds", region_name=REGION)

def lambda_handler(event, context):
    resp = ec2.describe_instances(Filters=[{"Name": "tag:Name", "Values": [EC2_TAG]}])
    instances = [i["InstanceId"] for r in resp["Reservations"] for i in r["Instances"]
                 if i["State"]["Name"] == "stopped"]
    if instances:
        ec2.start_instances(InstanceIds=instances)
        print(f"Started EC2: {instances}")
    else:
        print("EC2 already running.")
    try:
        rds.start_db_instance(DBInstanceIdentifier=RDS_ID)
        print(f"Started RDS: {RDS_ID}")
    except rds.exceptions.InvalidDBInstanceStateFault:
        print("RDS already running.")
    return {"status": "started"}
PYEOF

cd "$TMPDIR_LAMBDA"
zip stop.zip stop.py > /dev/null
zip start.zip start.py > /dev/null
cd - > /dev/null

# ─── Step 3: Deploy Lambda functions ─────────────────────────────────────
ENV_VARS="Variables={REGION=$REGION,EC2_TAG=portfolio-server,RDS_ID=portfolio-db}"

deploy_lambda() {
  local name=$1 zipfile=$2 handler=$3
  if aws lambda get-function --function-name "$name" --region "$REGION" &>/dev/null; then
    info "Updating Lambda $name..."
    aws lambda update-function-code \
      --function-name "$name" \
      --zip-file "fileb://${zipfile}" \
      --region "$REGION" > /dev/null
  else
    info "Creating Lambda $name..."
    aws lambda create-function \
      --function-name "$name" \
      --runtime python3.12 \
      --handler "$handler" \
      --role "$ROLE_ARN" \
      --zip-file "fileb://${zipfile}" \
      --timeout 30 \
      --environment "$ENV_VARS" \
      --region "$REGION" > /dev/null
  fi
  success "$name deployed."
}

deploy_lambda "portfolio-scheduler-stop"  "$TMPDIR_LAMBDA/stop.zip"  "stop.lambda_handler"
deploy_lambda "portfolio-scheduler-start" "$TMPDIR_LAMBDA/start.zip" "start.lambda_handler"

STOP_ARN="arn:aws:lambda:${REGION}:${ACCOUNT_ID}:function:portfolio-scheduler-stop"
START_ARN="arn:aws:lambda:${REGION}:${ACCOUNT_ID}:function:portfolio-scheduler-start"

# ─── Step 4: EventBridge rules ───────────────────────────────────────────
info "Creating EventBridge rule: stop at 11 PM CST (05:00 UTC)..."
aws events put-rule \
  --name portfolio-stop-at-night \
  --schedule-expression "cron(0 5 * * ? *)" \
  --description "Stop AI Career Hub at 11 PM CST (cost saving)" \
  --state ENABLED \
  --region "$REGION" > /dev/null

info "Creating EventBridge rule: start at 8 AM CST (14:00 UTC)..."
aws events put-rule \
  --name portfolio-start-in-morning \
  --schedule-expression "cron(0 14 * * ? *)" \
  --description "Start AI Career Hub at 8 AM CST (business hours)" \
  --state ENABLED \
  --region "$REGION" > /dev/null

# Grant EventBridge permission to invoke Lambdas
aws lambda add-permission \
  --function-name portfolio-scheduler-stop \
  --statement-id AllowEventBridgeStop \
  --action lambda:InvokeFunction \
  --principal events.amazonaws.com \
  --source-arn "arn:aws:events:${REGION}:${ACCOUNT_ID}:rule/portfolio-stop-at-night" \
  --region "$REGION" > /dev/null 2>&1 || true

aws lambda add-permission \
  --function-name portfolio-scheduler-start \
  --statement-id AllowEventBridgeStart \
  --action lambda:InvokeFunction \
  --principal events.amazonaws.com \
  --source-arn "arn:aws:events:${REGION}:${ACCOUNT_ID}:rule/portfolio-start-in-morning" \
  --region "$REGION" > /dev/null 2>&1 || true

# Wire targets
aws events put-targets \
  --rule portfolio-stop-at-night \
  --targets "Id=StopTarget,Arn=$STOP_ARN" \
  --region "$REGION" > /dev/null

aws events put-targets \
  --rule portfolio-start-in-morning \
  --targets "Id=StartTarget,Arn=$START_ARN" \
  --region "$REGION" > /dev/null

success "EventBridge rules wired."

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e "${GREEN}  ✅ Night sleep schedule installed!${NC}"
echo ""
echo "  🌙 Stops  at : 11 PM CST  (05:00 UTC)"
echo "  ☀️  Starts at :  8 AM CST  (14:00 UTC)"
echo "  💸 Uptime   :  9 hrs/day → saves ~62%"
echo ""
echo "  To test immediately:"
echo "    aws lambda invoke --function-name portfolio-scheduler-stop \\"
echo "      --region $REGION /dev/null"
echo ""
echo "  To remove the schedule:"
echo "    bash infra/scripts/schedule-sleep.sh --remove"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
