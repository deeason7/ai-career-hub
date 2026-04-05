#!/bin/bash
set -euo pipefail

REGION="us-east-1"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_REGISTRY="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"
export ECR_REGISTRY

echo "Logging into ECR..."
aws ecr get-login-password --region "$REGION" \
  | docker login --username AWS --password-stdin "$ECR_REGISTRY"

echo "Fetching secrets from SSM..."
bash "$(dirname "$0")/pull-secrets.sh"

echo "Pulling images..."
docker compose -f docker-compose.prod.yml pull

echo "Starting stack..."
docker compose -f docker-compose.prod.yml up -d --remove-orphans

docker image prune -f
echo "Deploy complete."
