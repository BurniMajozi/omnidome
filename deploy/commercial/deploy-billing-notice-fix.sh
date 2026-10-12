#!/usr/bin/env bash
set -euo pipefail
cd /home/benedict/omnidome
source_root=/mnt/c/Users/Benedict/Desktop/OminiDome/omnidome
export COMPOSE_FILE=docker-compose.yaml:docker-compose.override.yml:docker-compose.local.yml:deploy/commercial/shadow.yml
current=$(docker inspect --format '{{.Image}}' omnidome-agent-orchestrator-1)
target=$(docker inspect --format '{{.Config.Image}}' omnidome-agent-orchestrator-1)
backup="omnidome-workflow-notice:before-$(date -u +%Y%m%d%H%M%S)"
docker tag "$current" "$backup"
tar -cf - -C "$source_root" deploy/commercial/billing-workflow-fix.Dockerfile services/agent_orchestrator/main.py services/agent_orchestrator/billing_workflows.py |
  DOCKER_BUILDKIT=0 docker build --build-arg "BASE_IMAGE=$current" -f deploy/commercial/billing-workflow-fix.Dockerfile -t omnidome-workflow-notice-fix - > /home/benedict/build_logs/billing-notice-fix.log 2>&1
[[ "$(docker inspect --format '{{.Image}}' omnidome-agent-orchestrator-1)" == "$current" ]] || { echo 'Concurrent orchestrator deployment detected; stopping.'; exit 1; }
restore() {
  docker tag "$current" "$target"
  docker compose up -d --no-deps --no-build --force-recreate agent-orchestrator > /home/benedict/build_logs/billing-notice-fix-rollback.log 2>&1
}
trap restore ERR
docker tag omnidome-workflow-notice-fix "$target"
docker compose up -d --no-deps --no-build --force-recreate agent-orchestrator > /home/benedict/build_logs/billing-notice-fix-start.log 2>&1
for attempt in $(seq 1 35); do
  if [[ "$(docker inspect --format '{{.State.Health.Status}}' omnidome-agent-orchestrator-1)" == healthy ]]; then
    echo 'Orchestrator healthy with notice deletion migration.'
    exit 0
  fi
  sleep 2
done
echo 'Orchestrator did not become healthy.'
false
