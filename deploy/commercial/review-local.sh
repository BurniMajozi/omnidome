#!/usr/bin/env bash
set -euo pipefail
cd /home/benedict/omnidome
source_root=/mnt/c/Users/Benedict/Desktop/OminiDome/omnidome
export COMPOSE_FILE=docker-compose.yaml:docker-compose.override.yml:docker-compose.local.yml:deploy/commercial/shadow.yml
services=(admin billing agent-orchestrator fno_intelligence gateway journey_engine compliance iot network support hr call_center inventory portal-builder marketing finance communication sales crm lifecycle tenant_memory)
declare -A image
mkdir -p /home/benedict/build_logs
for service in "${services[@]}" web; do
  image[$service]=$(docker inspect --format '{{.Config.Image}}' "omnidome-$service-1")
  docker tag "${image[$service]}" "omnidome-review-$service:backup"
done
finished=false
restore() {
  set +e
  if [[ "$finished" != true ]]; then
    for service in "${services[@]}" web; do docker tag "omnidome-review-$service:backup" "${image[$service]}"; done
  fi
  docker compose up -d --no-deps --no-build "${services[@]}" web > /home/benedict/build_logs/restore-pricing-review.log 2>&1
  systemctl --user start omnidome-watch.service
  echo 'Core services restored; optional Autumn remains stopped.'
}
trap restore EXIT
systemctl --user stop omnidome-watch.service
docker compose stop -t 3 "${services[@]}" web > /home/benedict/build_logs/stop-pricing-review.log 2>&1
for service in admin billing agent-orchestrator; do
  tar -cf - -C "$source_root" deploy/commercial/service.Dockerfile services/common services/admin services/billing services/agent_orchestrator apps/web/lib/platform-pricing.json |
    DOCKER_BUILDKIT=0 docker build --build-arg "BASE_IMAGE=omnidome-review-$service:backup" -f deploy/commercial/service.Dockerfile -t "${image[$service]}" - > "/home/benedict/build_logs/review-$service.log" 2>&1
  echo "Updated $service."
done
tar -cf - -C "$source_root" deploy/commercial/web.Dockerfile apps/web/components apps/web/lib apps/web/app apps/web/proxy.ts |
  DOCKER_BUILDKIT=0 docker build --build-arg BASE_IMAGE=omnidome-review-web:backup -f deploy/commercial/web.Dockerfile -t "${image[web]}" - > /home/benedict/build_logs/review-web.log 2>&1
echo 'Pricing web build passed.'
for service in "${services[@]}"; do
  tar -cf - -C "$source_root" deploy/commercial/pool.Dockerfile services/common/db.py |
    DOCKER_BUILDKIT=0 docker build --build-arg "BASE_IMAGE=${image[$service]}" -f deploy/commercial/pool.Dockerfile -t "${image[$service]}" - > "/home/benedict/build_logs/review-pool-$service.log" 2>&1
done
for service in common admin billing agent_orchestrator; do rsync -a "$source_root/services/$service/" "services/$service/"; done
for part in components lib app; do rsync -a "$source_root/apps/web/$part/" "apps/web/$part/"; done
rsync -a "$source_root/deploy/commercial/" deploy/commercial/
docker compose up -d --no-deps --no-build --force-recreate "${services[@]}" web > /home/benedict/build_logs/start-pricing-review.log 2>&1
finished=true
echo 'All four bundles deployed; local database pools bounded and Autumn optional.'
