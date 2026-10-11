#!/usr/bin/env bash
set -euo pipefail
cd /home/benedict/omnidome
source_root=/mnt/c/Users/Benedict/Desktop/OminiDome/omnidome
base_compose=docker-compose.yaml:docker-compose.override.yml:docker-compose.local.yml
export COMPOSE_FILE=$base_compose
mkdir -p /home/benedict/build_logs
mapfile -t running < <(docker compose ps --services --status running | grep -v -E '^(db|ollama)$')
images=(admin billing agent-orchestrator web)
backup_tag=pre-commercial-shadow
finished=false
restore() {
  set +e
  if [[ "$finished" != true ]]; then
    export COMPOSE_FILE=$base_compose
    for image in "${images[@]}"; do docker tag "omnidome-$image:$backup_tag" "omnidome-$image:latest"; done
  fi
  for service in "${running[@]}"; do docker compose up -d --no-deps --no-build "$service" > "/home/benedict/build_logs/restore-commercial-$service.log" 2>&1; done
  systemctl --user start omnidome-watch.service
  echo 'Services restored; watchdog enabled.'
}
for image in "${images[@]}"; do docker tag "omnidome-$image:latest" "omnidome-$image:$backup_tag"; done
trap restore EXIT
systemctl --user stop omnidome-watch.service
docker compose stop -t 10 "${running[@]}" > /home/benedict/build_logs/stop-commercial.log 2>&1
for image in admin billing agent-orchestrator; do
  tar -cf - -C "$source_root" deploy/commercial/service.Dockerfile services/common services/admin services/billing services/agent_orchestrator apps/web/lib/platform-pricing.json |
    DOCKER_BUILDKIT=0 docker build --build-arg "BASE_IMAGE=omnidome-$image:$backup_tag" -f deploy/commercial/service.Dockerfile -t "omnidome-$image:latest" - > "/home/benedict/build_logs/build-commercial-$image.log" 2>&1
  echo "Built $image."
done
tar -cf - -C "$source_root" deploy/commercial/web.Dockerfile apps/web/components apps/web/lib apps/web/app apps/web/proxy.ts |
  DOCKER_BUILDKIT=0 docker build --build-arg "BASE_IMAGE=omnidome-web:$backup_tag" -f deploy/commercial/web.Dockerfile -t omnidome-web:latest - > /home/benedict/build_logs/build-commercial-web.log 2>&1
echo 'Web build passed.'
for service in common admin billing agent_orchestrator; do rsync -a "$source_root/services/$service/" "services/$service/"; done
for part in components lib app; do rsync -a "$source_root/apps/web/$part/" "apps/web/$part/"; done
mkdir -p deploy/commercial
rsync -a "$source_root/deploy/commercial/" deploy/commercial/
cp "$source_root/apps/web/proxy.ts" apps/web/proxy.ts
export COMPOSE_FILE=$base_compose:deploy/commercial/shadow.yml
docker compose up -d --no-deps --no-build --force-recreate admin billing agent-orchestrator web > /home/benedict/build_logs/recreate-commercial.log 2>&1
finished=true
echo 'Commercial shadow metering deployed locally.'
