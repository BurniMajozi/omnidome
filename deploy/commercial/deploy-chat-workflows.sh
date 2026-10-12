#!/usr/bin/env bash
set -euo pipefail
cd /home/benedict/omnidome
source_root=/mnt/c/Users/Benedict/Desktop/OminiDome/omnidome
export COMPOSE_FILE="docker-compose.yaml:docker-compose.override.yml:docker-compose.local.yml:$source_root/deploy/commercial/shadow.yml"
exec 9>/home/benedict/platform-billing-deploy.lock
flock -n 9 || { echo 'Another platform deployment is running.'; exit 1; }
stamp=$(date -u +%Y%m%d%H%M%S)
declare -A original target staged backup
services=(agent-orchestrator web)
[[ "${OD_CHAT_AGENT_ONLY:-}" != 1 ]] || services=(agent-orchestrator)
[[ "${OD_CHAT_PORTAL:-}" != 1 ]] || services+=(portal-builder)
for service in "${services[@]}"; do
  [[ "$(docker inspect --format '{{.State.Running}}' "omnidome-$service-1")" == true ]] || { echo "$service is stopped; deployment halted."; exit 1; }
  original[$service]=$(docker inspect --format '{{.Image}}' "omnidome-$service-1")
  target[$service]=$(docker inspect --format '{{.Config.Image}}' "omnidome-$service-1")
  backup[$service]="omnidome-chat-$service:before-$stamp"
  staged[$service]="omnidome-chat-$service:staged-$stamp"
  docker tag "${original[$service]}" "${backup[$service]}"
done
tar -cf - -C "$source_root" deploy/commercial/workflow-chat.Dockerfile services/agent_orchestrator services/common |
  DOCKER_BUILDKIT=0 docker build --build-arg "BASE_IMAGE=${original[agent-orchestrator]}" -f deploy/commercial/workflow-chat.Dockerfile -t "${staged[agent-orchestrator]}" - > /home/benedict/build_logs/chat-workflows-agent.log 2>&1
echo 'Built orchestrator.'
if [[ "${OD_CHAT_PORTAL:-}" == 1 ]]; then
  tar -cf - -C "$source_root" deploy/commercial/shared-access.Dockerfile services/common apps/web/lib/platform-pricing.json |
    DOCKER_BUILDKIT=0 docker build --build-arg "BASE_IMAGE=${original[portal-builder]}" -f deploy/commercial/shared-access.Dockerfile -t "${staged[portal-builder]}" - > /home/benedict/build_logs/llm-routing-portal.log 2>&1
  echo 'Built portal routing guard.'
fi
if [[ "${OD_CHAT_AGENT_ONLY:-}" == 1 ]]; then
  echo 'Keeping the deployed web image.'
elif [[ -n "${OD_CHAT_WEB_IMAGE:-}" ]]; then
  docker image inspect "$OD_CHAT_WEB_IMAGE" > /dev/null
  docker tag "$OD_CHAT_WEB_IMAGE" "${staged[web]}"
else
  tar -cf - -C "$source_root" deploy/commercial/web.Dockerfile apps/web/components apps/web/lib apps/web/app apps/web/proxy.ts |
    DOCKER_BUILDKIT=0 docker build --memory=3g --cpu-period=100000 --cpu-quota=100000 --build-arg "BASE_IMAGE=${original[web]}" -f deploy/commercial/web.Dockerfile -t "${staged[web]}" - > /home/benedict/build_logs/chat-workflows-web.log 2>&1
fi
echo 'Built web.'
for service in "${services[@]}"; do
  [[ "$(docker inspect --format '{{.Image}}' "omnidome-$service-1")" == "${original[$service]}" ]] || { echo 'Concurrent deployment detected; activation halted.'; exit 1; }
done
watcher=false
docker exec -i omnidome-admin-1 python < "$source_root/deploy/commercial/agent-work-deploy-ready.py"
systemctl --user is-active --quiet omnidome-watch.service && watcher=true
activated=false
finished=false
restore() {
  set +e
  if [[ "$activated" == true && "$finished" != true ]]; then
    for service in "${services[@]}"; do docker tag "${backup[$service]}" "${target[$service]}"; done
    docker compose up -d --no-deps --no-build --force-recreate "${services[@]}" > /home/benedict/build_logs/chat-workflows-rollback.log 2>&1
    echo "Rolled back images to before-$stamp."
  fi
  [[ "$watcher" != true ]] || systemctl --user start omnidome-watch.service
}
trap restore EXIT
[[ "$watcher" != true ]] || systemctl --user stop omnidome-watch.service
activated=true
for service in "${services[@]}"; do docker tag "${staged[$service]}" "${target[$service]}"; done
rsync -a "$source_root/services/agent_orchestrator/" services/agent_orchestrator/
rsync -a "$source_root/services/common/" services/common/
for part in components app lib; do rsync -a "$source_root/apps/web/$part/" "apps/web/$part/"; done
for service in "${services[@]}"; do
  docker compose up -d --no-deps --no-build --force-recreate "$service" > "/home/benedict/build_logs/chat-workflows-start-$service.log" 2>&1
  healthy=false
  for attempt in $(seq 1 40); do
    state=$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "omnidome-$service-1")
    if [[ "$state" == healthy || "$state" == running ]]; then
      if [[ "$service" != web ]] || curl --fail --silent --output /dev/null http://127.0.0.1:3000/dashboard/admin/workflows; then
        healthy=true; break
      fi
    fi
    sleep 2
  done
  [[ "$healthy" == true ]] || { echo "$service failed health check."; exit 1; }
  echo "$service healthy."
done
docker exec -i omnidome-admin-1 python < "$source_root/deploy/commercial/check-chat-workflows.py"
docker exec -i omnidome-admin-1 python < "$source_root/deploy/commercial/check-agent-work.py"
finished=true
echo "Chat workflows deployed. Rollback: before-$stamp."
