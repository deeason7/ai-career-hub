#!/bin/bash
set -euo pipefail

REGION="us-east-1"

INSTANCE_ID=$(aws ec2 describe-instances \
  --filters "Name=tag:Name,Values=careerhub-server" \
            "Name=instance-state-name,Values=stopped" \
  --query "Reservations[0].Instances[0].InstanceId" \
  --output text --region "$REGION")

echo "Starting RDS (takes a few minutes)..."
aws rds start-db-instance --db-instance-identifier portfolio-db \
  --region "$REGION" > /dev/null 2>&1 || true

echo "Starting EC2 ($INSTANCE_ID)..."
aws ec2 start-instances --instance-ids "$INSTANCE_ID" \
  --region "$REGION" > /dev/null

echo "Up. Wait ~3 min, then SSM in and run deploy.sh."
