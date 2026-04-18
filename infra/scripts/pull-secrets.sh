#!/usr/bin/env bash
set -euo pipefail

REGION="${AWS_REGION:-us-east-1}"
PREFIX="/portfolio/careerhub"
OUTPUT=".env.prod"

aws ssm get-parameters-by-path \
  --path "$PREFIX" \
  --with-decryption \
  --region "$REGION" \
  --query 'Parameters[*].[Name,Value]' \
  --output text \
| while IFS=$'\t' read -r name value; do
    key="${name##*/}"
    printf '%s=%s\n' "$key" "$value"
  done > "$OUTPUT"

chmod 600 "$OUTPUT"
