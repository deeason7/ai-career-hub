#!/bin/bash
set -euo pipefail

PREV_SHA="${1:?Usage: rollback.sh <previous-git-sha>}"
REGION="${AWS_REGION:-us-east-1}"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text 2>/dev/null)
ECR_REGISTRY="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"

aws ecr get-login-password --region "$REGION" \
  | docker login --username AWS --password-stdin "$ECR_REGISTRY" 2>/dev/null

docker pull "${ECR_REGISTRY}/careerhub-backend:${PREV_SHA}"
docker pull "${ECR_REGISTRY}/careerhub-frontend:${PREV_SHA}"

docker tag "${ECR_REGISTRY}/careerhub-backend:${PREV_SHA}"  "${ECR_REGISTRY}/careerhub-backend:latest"
docker tag "${ECR_REGISTRY}/careerhub-frontend:${PREV_SHA}" "${ECR_REGISTRY}/careerhub-frontend:latest"

export ECR_REGISTRY
docker compose -f docker-compose.prod.yml up -d --force-recreate api frontend
