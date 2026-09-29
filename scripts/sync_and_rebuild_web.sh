#!/bin/bash
set -e

SRC="/mnt/c/Users/Benedict/Desktop/OminiDome/omnidome"

echo "=== 1. Syncing latest web app code and configs to WSL mirror ==="
cp "$SRC/apps/web/package.json" /home/benedict/omnidome/apps/web/package.json
cp "$SRC/apps/web/package-lock.json" /home/benedict/omnidome/apps/web/package-lock.json
rsync -av "$SRC/apps/web/lib/" /home/benedict/omnidome/apps/web/lib/
rsync -av "$SRC/apps/web/components/" /home/benedict/omnidome/apps/web/components/
rsync -av "$SRC/apps/web/app/" /home/benedict/omnidome/apps/web/app/
rsync -av "$SRC/services/marketing/" /home/benedict/omnidome/services/marketing/
rsync -av "$SRC/services/communication/" /home/benedict/omnidome/services/communication/ 2>/dev/null || true
rsync -av "$SRC/services/hr/" /home/benedict/omnidome/services/hr/
rsync -av "$SRC/services/agent_orchestrator/" /home/benedict/omnidome/services/agent_orchestrator/
rsync -av "$SRC/services/sales/" /home/benedict/omnidome/services/sales/
cp "$SRC/docker-compose.yaml" /home/benedict/omnidome/docker-compose.yaml
cp "$SRC/docker-compose.local.yml" /home/benedict/omnidome/docker-compose.local.yml

echo "=== 2. Rebuilding omnidome-web image ==="
mkdir -p /home/benedict/build_logs
/home/benedict/rebuild_web_getsession_fix.sh

echo "=== 3. Recreating web container ==="
cd /home/benedict/omnidome
export COMPOSE_FILE=docker-compose.yaml:docker-compose.override.yml:docker-compose.local.yml
docker compose up -d --no-deps web

echo "=== 4. Status ==="
docker ps | grep web
echo "=== WEB REBUILD AND RESTART COMPLETE ==="
