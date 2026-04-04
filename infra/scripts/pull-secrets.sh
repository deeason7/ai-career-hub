#!/usr/bin/env bash
# pull-secrets.sh
#
# Reads all parameters under /portfolio/careerhub from SSM Parameter Store
# and writes them to .env.prod in the current directory.
#
# Run this before `docker compose -f docker-compose.prod.yml up -d`.
# The EC2 instance role has read access scoped to /portfolio/* only.

set -euo pipefail

PREFIX="/portfolio/careerhub"
OUTPUT=".env.prod"

echo "Pulling secrets from SSM (${PREFIX})..."

aws ssm get-parameters-by-path \
  --path "$PREFIX" \
  --with-decryption \
  --region us-east-1 \
  --query 'Parameters[*].[Name,Value]' \
  --output text \
| while IFS=$'\t' read -r name value; do
    key="${name##*/}"    # strip /portfolio/careerhub/ prefix, keep key name
    printf '%s=%s\n' "$key" "$value"
  done > "$OUTPUT"

echo "Written ${OUTPUT} ($(wc -l < "$OUTPUT") variables)"
