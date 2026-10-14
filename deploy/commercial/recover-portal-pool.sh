#!/usr/bin/env bash
set -euo pipefail
cd /home/benedict/omnidome
source_root=/mnt/c/Users/Benedict/Desktop/OminiDome/omnidome
export COMPOSE_FILE="docker-compose.yaml:docker-compose.override.yml:docker-compose.local.yml:$source_root/deploy/commercial/shadow.yml"
exec 9>/home/benedict/platform-billing-deploy.lock
flock -n 9 || { echo 'Another platform deployment is running.'; exit 1; }
watcher=false
systemctl --user is-active --quiet omnidome-watch.service && watcher=true
trap '[[ "$watcher" != true ]] || systemctl --user start omnidome-watch.service' EXIT
[[ "$watcher" != true ]] || systemctl --user stop omnidome-watch.service
docker compose up -d --no-deps --no-build --force-recreate portal-builder > /home/benedict/build_logs/portal-pool-recovery.log 2>&1
for attempt in $(seq 1 90); do
  if docker exec omnidome-portal-builder-1 python -c "import urllib.request; urllib.request.urlopen('http://localhost:8026/health', timeout=4)" >/dev/null 2>&1; then
    echo 'Portal Builder healthy with one worker and bounded database pools.'; exit 0
  fi
  sleep 2
done
docker logs --tail 30 omnidome-portal-builder-1 > /home/benedict/build_logs/portal-pool-failure.log 2>&1
echo 'Portal Builder has not become ready; see portal-pool-failure.log.'
exit 1
