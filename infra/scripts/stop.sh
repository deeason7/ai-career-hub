#!/bin/bash
set -euo pipefail

REGION="us-east-1"

INSTANCE_ID=$(aws ec2 describe-instances \
  --filters "Name=tag:Name,Values=portfolio-server" \
            "Name=instance-state-name,Values=running" \
  --query "Reservations[0].Instances[0].InstanceId" \
  --output text --region "$REGION")

echo "Stopping EC2 ($INSTANCE_ID)..."
aws ec2 stop-instances --instance-ids "$INSTANCE_ID" --region "$REGION" > /dev/null

echo "Stopping RDS..."
aws rds stop-db-instance --db-instance-identifier portfolio-db \
  --region "$REGION" > /dev/null

echo "Done. Compute stopped — storage billing continues."
