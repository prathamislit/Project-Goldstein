#!/bin/bash
# ── Project Goldstein — DigitalOcean Deploy Script ───────────────────────────
# Run once on a fresh $12/mo Droplet (Ubuntu 22.04, 2 vCPU / 2GB RAM)
# Usage: bash deploy.sh
# ─────────────────────────────────────────────────────────────────────────────

set -e

echo "== Project Goldstein Deploy =="
echo "Droplet: $(hostname)"
echo "Date:    $(date)"

# 1. Install Docker
if ! command -v docker &>/dev/null; then
    echo "[1/6] Installing Docker..."
    curl -fsSL https://get.docker.com | sh
    usermod -aG docker $USER
else
    echo "[1/6] Docker already installed."
fi

# 2. Install Docker Compose
if ! command -v docker-compose &>/dev/null; then
    echo "[2/6] Installing Docker Compose..."
    curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" \
         -o /usr/local/bin/docker-compose
    chmod +x /usr/local/bin/docker-compose
else
    echo "[2/6] Docker Compose already installed."
fi

# 3. Clone repo
echo "[3/6] Cloning repository..."
if [ ! -d "/opt/goldstein" ]; then
    git clone https://github.com/prathamislit/Project-Goldstein.git /opt/goldstein
else
    cd /opt/goldstein && git pull
fi
cd /opt/goldstein

# 4. Check required secrets
echo "[4/6] Checking secrets..."
if [ ! -f ".env" ]; then
    echo "ERROR: .env file not found. Upload it with:"
    echo "  scp .env root@YOUR_DROPLET_IP:/opt/goldstein/.env"
    exit 1
fi
if [ ! -f "gcp_key.json" ]; then
    echo "ERROR: gcp_key.json not found. Upload it with:"
    echo "  scp gcp_key.json root@YOUR_DROPLET_IP:/opt/goldstein/gcp_key.json"
    exit 1
fi

# 5. Build and start dashboard
echo "[5/6] Building Docker image..."
docker-compose build dashboard

echo "[6/6] Starting dashboard..."
docker-compose up -d dashboard

# 6. Set up daily pipeline cron (6 AM UTC)
echo "Setting up daily pipeline cron..."
CRON_CMD="0 6 * * * cd /opt/goldstein && docker-compose run --rm pipeline >> /opt/goldstein/logs/cron.log 2>&1"
(crontab -l 2>/dev/null | grep -v "goldstein"; echo "$CRON_CMD") | crontab -

echo ""
echo "========================================"
echo "Deploy complete."
echo "Dashboard: http://$(curl -s ifconfig.me):8050"
echo "Pipeline runs daily at 6 AM UTC."
echo ""
echo "To run pipeline manually:"
echo "  cd /opt/goldstein && docker-compose run --rm pipeline"
echo ""
echo "To add a buyer:"
echo "  Edit .env -> GOLDSTEIN_USERS=buyer1:key_abc,buyer2:key_xyz"
echo "  docker-compose restart dashboard"
echo "========================================"
