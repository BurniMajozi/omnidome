#!/usr/bin/env bash
set -euo pipefail
workspace_root=${HOME_DOME_WORKSPACE_ROOT:-/home/benedict/omnidome}
cd "$workspace_root"
source_root=${HOME_DOME_SOURCE_ROOT:-/mnt/c/Users/Benedict/Desktop/OminiDome/omnidome}
export COMPOSE_FILE="docker-compose.yaml:docker-compose.override.yml:docker-compose.local.yml:$source_root/deploy/commercial/shadow.yml"
exec 9>platform-billing-deploy.lock
flock -n 9 || { echo 'Another platform deployment is running.'; exit 1; }
host_available=$(df --output=avail -B1 /mnt/c | tail -1)
required_space=$((3 * 1024 * 1024 * 1024))
if [[ "${HOME_DOME_BACKEND_ONLY:-}" == 1 || ( "${HOME_DOME_ROOMS_ONLY:-}" == 1 && -n "${HOME_DOME_WEB_IMAGE:-}" ) ]]; then
  # This overlay reuses the running image and copies a few MiB of source; no pulls,
  # dependencies or web build. Keep a 512 MiB reserve plus eight source copies.
  source_bytes=$(du -sb "$source_root/services/iot" "$source_root/services/common" | awk '{sum += $1} END {print sum}')
  required_space=$((512 * 1024 * 1024 + 8 * source_bytes))
fi
if (( host_available < required_space )); then
  echo "Free $required_space bytes on Windows C: before rebuilding HomeDome (including reserve)." >&2
  exit 1
fi
mkdir -p "$workspace_root/build_logs"
services=(iot web agent-orchestrator)
[[ "${HOME_DOME_BACKEND_ONLY:-}" != 1 ]] || services=(iot)
[[ "${HOME_DOME_ROOMS_ONLY:-}" != 1 ]] || services=(iot web)
[[ "${HOME_DOME_WEB_ONLY:-}" != 1 ]] || services=(web)
declare -A original target staged
for service in "${services[@]}"; do
  original[$service]=$(docker inspect --format '{{.Image}}' "omnidome-$service-1")
  target[$service]=$(docker inspect --format '{{.Config.Image}}' "omnidome-$service-1")
done
if [[ -n "${original[iot]:-}" ]]; then
tar -cf - --exclude=__pycache__ --exclude=.pytest_cache -C "$source_root" deploy/commercial/homedome.Dockerfile services/iot services/common apps/web/lib/platform-pricing.json |
  DOCKER_BUILDKIT=0 docker build --build-arg "BASE_IMAGE=${original[iot]}" -f deploy/commercial/homedome.Dockerfile --iidfile "$workspace_root/build_logs/homedome-iot.iid" - > "$workspace_root/build_logs/homedome-iot.log" 2>&1
staged[iot]=$(cat "$workspace_root/build_logs/homedome-iot.iid")
echo 'Built HomeDome backend.'
fi
if [[ -n "${original[agent-orchestrator]:-}" ]]; then
tar -cf - --exclude=__pycache__ --exclude=.pytest_cache -C "$source_root" deploy/commercial/workflow-chat.Dockerfile services/agent_orchestrator services/common |
  DOCKER_BUILDKIT=0 docker build --build-arg "BASE_IMAGE=${original[agent-orchestrator]}" -f deploy/commercial/workflow-chat.Dockerfile --iidfile "$workspace_root/build_logs/homedome-orchestrator.iid" - > "$workspace_root/build_logs/homedome-orchestrator.log" 2>&1
staged[agent-orchestrator]=$(cat "$workspace_root/build_logs/homedome-orchestrator.iid")
fi
if [[ -n "${original[web]:-}" ]]; then
if [[ -n "${HOME_DOME_WEB_IMAGE:-}" ]]; then
  staged[web]=$(docker image inspect --format '{{.Id}}' "$HOME_DOME_WEB_IMAGE")
else
  tar -cf - -C "$source_root" deploy/commercial/web.Dockerfile apps/web/components apps/web/lib apps/web/app apps/web/proxy.ts |
    DOCKER_BUILDKIT=0 docker build --memory=3g --cpu-period=100000 --cpu-quota=100000 --build-arg "BASE_IMAGE=${original[web]}" -f deploy/commercial/web.Dockerfile --iidfile "$workspace_root/build_logs/homedome-web.iid" - > "$workspace_root/build_logs/homedome-web.log" 2>&1
  staged[web]=$(cat "$workspace_root/build_logs/homedome-web.iid")
fi
echo 'Prepared web image.'
else
  echo 'Keeping the running web and workflow images.'
fi
for service in "${services[@]}"; do
  [[ "${staged[$service]}" =~ ^sha256:[a-f0-9]{64}$ ]] || { echo 'Invalid staged image ID.'; exit 1; }
  [[ "$(docker inspect --format '{{.Image}}' "omnidome-$service-1")" == "${original[$service]}" ]] || { echo 'Concurrent deployment detected.'; exit 1; }
done
docker exec -i omnidome-admin-1 python < "$source_root/deploy/commercial/agent-work-deploy-ready.py"
# Metadata only: one bounded file, no historical image aliases. Keep these IDs
# available until validation finishes; do not prune images during deployment.
: > "$workspace_root/build_logs/homedome-rollback.images"
for service in "${services[@]}"; do
  printf '%s %s\n' "${target[$service]}" "${original[$service]}" >> "$workspace_root/build_logs/homedome-rollback.images"
done
watcher=false
systemctl --user is-active --quiet omnidome-watch.service && watcher=true
activated=false
finished=false
restore() {
  set +e
  if [[ "$activated" == true && "$finished" != true ]]; then
    for service in "${services[@]}"; do
      docker logs --tail 40 "omnidome-$service-1" > "$workspace_root/build_logs/homedome-failed-$service.log" 2>&1
      docker tag "${original[$service]}" "${target[$service]}"
    done
    docker compose up -d --no-deps --no-build --force-recreate "${services[@]}" > "$workspace_root/build_logs/homedome-rollback.log" 2>&1
    echo 'Rolled back to the original image IDs.'
  fi
  [[ "$watcher" != true ]] || systemctl --user start omnidome-watch.service
}
trap restore EXIT
[[ "$watcher" != true ]] || systemctl --user stop omnidome-watch.service
activated=true
for service in "${services[@]}"; do docker tag "${staged[$service]}" "${target[$service]}"; done
rsync -a "$source_root/services/iot/" services/iot/
rsync -a "$source_root/services/common/" services/common/
rsync -a "$source_root/services/agent_orchestrator/" services/agent_orchestrator/
for part in components app lib; do rsync -a "$source_root/apps/web/$part/" "apps/web/$part/"; done
docker compose up -d --no-deps --no-build --force-recreate "${services[@]}" > "$workspace_root/build_logs/homedome-start.log" 2>&1
for attempt in $(seq 1 90); do
  if docker exec omnidome-iot-1 python -c "import urllib.request; urllib.request.urlopen('http://localhost:8006/health', timeout=4)" >/dev/null 2>&1 &&
     docker exec omnidome-agent-orchestrator-1 python -c "import urllib.request; urllib.request.urlopen('http://localhost:8021/health', timeout=4)" >/dev/null 2>&1 &&
     curl --max-time 5 --fail --silent --output /dev/null http://127.0.0.1:3000/dashboard/home-dome; then
    finished=true; break
  fi
  sleep 2
done
[[ "$finished" == true ]]
echo "HomeDome deployed. Original image IDs: $workspace_root/build_logs/homedome-rollback.images"

