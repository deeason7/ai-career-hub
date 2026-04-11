#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
#  install-boot-deploy.sh
#
#  Installs a systemd service on EC2 that runs on every boot:
#    1. Pulls latest code from GitHub
#    2. Runs docker compose up -d with the correct ECR registry
#
#  Run this ONCE inside EC2 (via SSM as ubuntu):
#    bash infra/scripts/install-boot-deploy.sh
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

REGION="us-east-1"
REPO_DIR="/home/ubuntu/ai-career-hub"

echo "[→] Installing boot-deploy systemd service..."

# Derive ECR registry dynamically from instance metadata (no hardcoding)
ECR_REGISTRY=$(aws sts get-caller-identity --query Account --output text 2>/dev/null || echo "").dkr.ecr.${REGION}.amazonaws.com

sudo tee /etc/systemd/system/app-boot-deploy.service > /dev/null <<EOF
[Unit]
Description=AI Career Hub — Docker Compose deploy on boot
After=docker.service network-online.target
Wants=network-online.target
Requires=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
User=ubuntu
WorkingDirectory=${REPO_DIR}
Environment="HOME=/home/ubuntu"
Environment="ECR_REGISTRY=${ECR_REGISTRY}"
ExecStartPre=/usr/bin/git -C ${REPO_DIR} pull --ff-only origin main
ExecStart=/usr/bin/docker compose -f ${REPO_DIR}/docker-compose.prod.yml up -d --remove-orphans
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable app-boot-deploy.service
echo "[✓] Service installed and enabled."
echo ""
echo "  On every boot EC2 will now:"
echo "    1. git pull origin main"
echo "    2. docker compose up -d --remove-orphans"
echo ""
echo "  To test manually:  sudo systemctl start app-boot-deploy.service"
echo "  To check logs:     sudo journalctl -u app-boot-deploy.service -f"
