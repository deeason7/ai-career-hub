#!/bin/bash
# Nightly document lifecycle cleanup.
# Installed on EC2 via: crontab -e
#   0 2 * * * /home/ec2-user/careerhub/infra/scripts/lifecycle_cleanup.sh >> /var/log/careerhub-lifecycle.log 2>&1
#
# Calls the protected /admin/lifecycle/run endpoint.
# Requires ADMIN_SECRET and API_BASE_URL to be set in /etc/careerhub.env.

set -euo pipefail

ENV_FILE="/etc/careerhub.env"
if [[ -f "$ENV_FILE" ]]; then
    # shellcheck disable=SC1090
    source "$ENV_FILE"
fi

: "${ADMIN_SECRET:?ADMIN_SECRET must be set in $ENV_FILE}"
: "${API_BASE_URL:=http://localhost:8000}"

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Running lifecycle cleanup..."

response=$(curl -sf -X POST \
    "${API_BASE_URL}/api/v1/admin/lifecycle/run" \
    -H "X-Admin-Secret: ${ADMIN_SECRET}" \
    -H "Content-Type: application/json" \
    --max-time 30)

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Done: ${response}"
