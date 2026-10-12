#!/usr/bin/env bash
set -euo pipefail
cd /home/benedict/omnidome
source_root=/mnt/c/Users/Benedict/Desktop/OminiDome/omnidome
if [[ "${OD_KNOWLEDGE_ENV_READY:-}" != 1 ]]; then
  exec python3 "$source_root/deploy/commercial/preserve-knowledge-env.py" --deploy
fi
export COMPOSE_FILE="docker-compose.yaml:docker-compose.override.yml:docker-compose.local.yml:$source_root/deploy/commercial/shadow.yml"
mkdir -p /home/benedict/build_logs
exec 9>/home/benedict/platform-billing-deploy.lock
flock -n 9 || { echo 'A billing deployment is already running.'; exit 1; }
stamp=$(date -u +%Y%m%d%H%M%S)
services=(admin billing agent-orchestrator communication inventory hr finance call_center sales marketing journey_engine crm compliance tenant_memory portal-builder support fno_intelligence lifecycle portal rica web)
declare -A original target staged backup original_running
active_services=()
for service in "${services[@]}"; do
  original[$service]=$(docker inspect --format '{{.Image}}' "omnidome-$service-1")
  original_running[$service]=$(docker inspect --format '{{.State.Running}}' "omnidome-$service-1")
  [[ "${original_running[$service]}" != true ]] || active_services+=("$service")
  target[$service]=$(docker inspect --format '{{.Config.Image}}' "omnidome-$service-1")
  backup[$service]="omnidome-billing-$service:before-$stamp"
  staged[$service]="omnidome-billing-$service:staged-$stamp"
  docker tag "${original[$service]}" "${backup[$service]}"
done
for service in "${services[@]}"; do
  [[ "$service" != web ]] || continue
  recipe=deploy/commercial/shared-access.Dockerfile
  case "$service" in admin|billing|agent-orchestrator|communication) recipe=deploy/commercial/billing-service.Dockerfile;; esac
  tar -cf - -C "$source_root" "$recipe" services/common services/admin services/billing services/agent_orchestrator services/communication apps/web/lib/platform-pricing.json |
    DOCKER_BUILDKIT=0 docker build --build-arg "BASE_IMAGE=${original[$service]}" -f "$recipe" -t "${staged[$service]}" - > "/home/benedict/build_logs/platform-billing-$service.log" 2>&1
  echo "Built $service."
done
tar -cf - -C "$source_root" deploy/commercial/web.Dockerfile apps/web/components apps/web/lib apps/web/app apps/web/proxy.ts |
  DOCKER_BUILDKIT=0 docker build --memory=3g --cpu-period=100000 --cpu-quota=100000 --build-arg "BASE_IMAGE=${original[web]}" -f deploy/commercial/web.Dockerfile -t "${staged[web]}" - > /home/benedict/build_logs/platform-billing-web.log 2>&1
echo 'Built web.'
for service in "${services[@]}"; do
  current=$(docker inspect --format '{{.Image}}' "omnidome-$service-1")
  [[ "$current" == "${original[$service]}" ]] || { echo "$service changed during build; stopping to preserve concurrent deployment."; exit 1; }
  current_running=$(docker inspect --format '{{.State.Running}}' "omnidome-$service-1")
  [[ "$current_running" == "${original_running[$service]}" ]] || { echo "$service running state changed during build; stopping to preserve concurrent work."; exit 1; }
done
watcher_active=false
systemctl --user is-active --quiet omnidome-watch.service && watcher_active=true
activated=false
finished=false
restore() {
  set +e
  if [[ "$activated" == true && "$finished" != true ]]; then
    for service in "${services[@]}"; do docker tag "${backup[$service]}" "${target[$service]}"; done
    docker compose up -d --no-deps --no-build --force-recreate "${active_services[@]}" > /home/benedict/build_logs/platform-billing-rollback.log 2>&1
    echo "Rolled back images to before-$stamp."
  fi
  [[ "$watcher_active" != true ]] || systemctl --user start omnidome-watch.service
}
trap restore EXIT
[[ "$watcher_active" != true ]] || systemctl --user stop omnidome-watch.service
activated=true
for service in "${services[@]}"; do docker tag "${staged[$service]}" "${target[$service]}"; done
for service in common admin billing communication; do rsync -a "$source_root/services/$service/" "services/$service/"; done
rsync -a "$source_root/services/agent_orchestrator/" services/agent_orchestrator/
for part in components lib app; do rsync -a "$source_root/apps/web/$part/" "apps/web/$part/"; done
rsync -a "$source_root/apps/web/proxy.ts" apps/web/proxy.ts
for service in "${active_services[@]}"; do
  docker compose up -d --no-deps --no-build --force-recreate "$service" > "/home/benedict/build_logs/platform-billing-start-$service.log" 2>&1
  healthy=false
  for attempt in $(seq 1 35); do
    status=$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "omnidome-$service-1")
    if [[ "$status" == healthy || "$status" == running ]]; then healthy=true; break; fi
    sleep 2
  done
  [[ "$healthy" == true ]] || { echo "$service did not become healthy."; exit 1; }
  echo "Activated $service: $status."
done
docker exec -i omnidome-admin-1 python < "$source_root/deploy/commercial/check-platform-billing.py"
curl --fail --silent --output /dev/null http://127.0.0.1:3000/platform-billing
finished=true
echo "Platform billing deployed. Rollback images: before-$stamp. Credit pricing has not been changed."
