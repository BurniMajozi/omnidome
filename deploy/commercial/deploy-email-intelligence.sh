#!/usr/bin/env bash
# Deploys the AgentMail email-intelligence change (docs/email-intelligence.md) as small overlays on the running images:
# communication, tenant_memory, knowledge_indexer, agent-orchestrator. Only the listed files are copied, so other sessions'
# uncommitted edits in the same folders are never shipped. Each image is backed up first; a failed health check rolls back.
set -euo pipefail
cd /home/benedict/omnidome
source_root=/mnt/c/Users/Benedict/Desktop/OminiDome/omnidome
export COMPOSE_FILE="docker-compose.yaml:docker-compose.override.yml:docker-compose.local.yml:$source_root/deploy/commercial/shadow.yml"
exec 9>/home/benedict/email-intelligence-deploy.lock
flock -n 9 || { echo 'Another email-intelligence deployment is running.'; exit 1; }
stamp=$(date -u +%Y%m%d%H%M%S)

common=(services/common/email_safety.py services/common/agentmail.py)
declare -A files
files[communication]="${common[*]} services/communication/mail_state.py services/communication/routes/mail.py services/communication/routes/mail_threads.py services/communication/main.py"
files[tenant_memory]="${common[*]} services/tenant_memory/knowledge/kdata.py services/tenant_memory/knowledge/store_pg.py services/tenant_memory/knowledge/store_memory.py services/tenant_memory/knowledge/retrieval.py services/tenant_memory/knowledge/cards/sources.py services/tenant_memory/knowledge/cards/sources_email.py services/tenant_memory/knowledge/cards/builders_capabilities.py"
files[knowledge_indexer]="${files[tenant_memory]}"
files[agent-orchestrator]="services/common/email_safety.py services/agent_orchestrator/tools.py services/agent_orchestrator/knowledge_client.py services/agent_orchestrator/llm.py services/agent_orchestrator/workflow_catalog.py"
order=(${OD_EMAIL_SERVICES:-communication tenant_memory knowledge_indexer agent-orchestrator})

# Compose takes the knowledge DB settings from the caller's shell, not .env: carry the running values over, or the
# recreated tenant_memory / knowledge_indexer start with the knowledge layer switched off.
for key in KNOWLEDGE_DB_URL KNOWLEDGE_DB_ADMIN_URL KNOWLEDGE_APP_PASSWORD; do
  for c in tenant_memory knowledge_indexer; do
    v=$(docker exec "omnidome-$c-1" printenv "$key" 2>/dev/null || true)
    if [[ -n "$v" ]]; then export "$key=$v"; break; fi
  done
done
[[ -n "${KNOWLEDGE_DB_URL:-}" ]] || { echo 'No running knowledge configuration found; run deploy/commercial/restore-knowledge-env.sh first.'; exit 1; }
export KNOWLEDGE_ENABLED=true EMBEDDING_MODEL=nomic-embed-text EMBEDDING_DIM=768 KNOWLEDGE_OLLAMA_URL=http://ollama:11434

declare -A original target staged backup
for service in "${order[@]}"; do
  [[ "$(docker inspect --format '{{.State.Running}}' "omnidome-$service-1")" == true ]] || { echo "$service is stopped; deployment halted."; exit 1; }
  original[$service]=$(docker inspect --format '{{.Image}}' "omnidome-$service-1")
  target[$service]=$(docker inspect --format '{{.Config.Image}}' "omnidome-$service-1")
  backup[$service]="omnidome-email-$service:before-$stamp"
  staged[$service]="omnidome-email-$service:staged-$stamp"
  docker tag "${original[$service]}" "${backup[$service]}"
  # shellcheck disable=SC2086
  tar -cf - -C "$source_root" deploy/commercial/email-intelligence.Dockerfile ${files[$service]} |
    DOCKER_BUILDKIT=0 docker build --build-arg "BASE_IMAGE=${original[$service]}" -f deploy/commercial/email-intelligence.Dockerfile -t "${staged[$service]}" - > "/home/benedict/build_logs/email-$service.log" 2>&1
  echo "Built $service."
done

watcher=false
systemctl --user is-active --quiet omnidome-watch.service && watcher=true || true
activated=false; finished=false
restore() {
  set +e
  if [[ "$activated" == true && "$finished" != true ]]; then
    for service in "${order[@]}"; do docker tag "${backup[$service]}" "${target[$service]}"; done
    docker compose up -d --no-deps --no-build --force-recreate "${order[@]}" > /home/benedict/build_logs/email-rollback.log 2>&1
    echo "Rolled back images to before-$stamp."
  fi
  [[ "$watcher" != true ]] || systemctl --user start omnidome-watch.service
}
trap restore EXIT
[[ "$watcher" != true ]] || systemctl --user stop omnidome-watch.service
activated=true
for service in "${order[@]}"; do
  docker tag "${staged[$service]}" "${target[$service]}"
  # keep the compose project copy in step so a later `up --build` does not revert the change
  # shellcheck disable=SC2086
  (cd "$source_root" && cp --parents ${files[$service]} /home/benedict/omnidome/)
  docker compose up -d --no-deps --no-build --force-recreate "$service" > "/home/benedict/build_logs/email-start-$service.log" 2>&1
  healthy=false
  for attempt in $(seq 1 45); do
    state=$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "omnidome-$service-1")
    if [[ "$state" == healthy || "$state" == running ]]; then healthy=true; break; fi
    sleep 2
  done
  [[ "$healthy" == true ]] || { echo "$service failed health check."; exit 1; }
  echo "$service healthy."
done
finished=true
echo "Email intelligence deployed. Rollback tag: before-$stamp."
