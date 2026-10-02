#!/usr/bin/env bash
# Run inside WSL. Each invocation performs one bounded deployment step.
set -euo pipefail
source_root=/mnt/c/Users/Benedict/Desktop/OminiDome/omnidome
runtime_root=/home/benedict/omnidome
cd "$runtime_root"
export COMPOSE_FILE=docker-compose.yaml:docker-compose.override.yml:docker-compose.local.yml
step=${1:?backup, mirror, backend SERVICE, or web}
if [[ "$step" == backup ]]; then
  backup=/home/benedict/rollback_codex_review
  mkdir -p "$backup"
  chmod 700 "$backup"
  test ! -e "$backup/services.tgz"
  tar -czf "$backup/services.tgz" services/common services/billing services/finance services/sales services/crm services/lifecycle services/communication services/iot services/support services/network services/call_center services/inventory docker-compose.yaml docker-compose.override.yml docker-compose.local.yml
  cp .env "$backup/runtime.env"
  chmod 600 "$backup/runtime.env"
  docker exec omnidome-db-1 sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$backup/database.dump"
  for service in billing finance sales crm lifecycle communication iot support network call_center inventory web; do
    docker tag "omnidome-$service:latest" "omnidome-$service:pre-codex-review"
  done
  echo 'Rollback code, environment, database and images saved.'
elif [[ "$step" == mirror ]]; then
  for service in common billing finance sales crm lifecycle communication iot support network call_center inventory; do
    cp -a "$source_root/services/$service/." "services/$service/"
    find "services/$service" -type d -name __pycache__ -prune -exec rm -rf {} +
  done
  for directory in app components lib; do
    cp -a "$source_root/apps/web/$directory/." "apps/web/$directory/"
  done
  cp "$source_root/apps/web/proxy.ts" apps/web/proxy.ts
  cp "$source_root/docker-compose.yaml" "$source_root/docker-compose.local.yml" .
  cp "$source_root/scripts/Dockerfile.review-layer" scripts/Dockerfile.review-layer
  echo 'Reviewed source mirrored.'
elif [[ "$step" == backend ]]; then
  service=${2:?service}
  case "$service" in billing|finance|sales|crm|lifecycle|communication|iot|support|network|call_center|inventory) ;; *) exit 2;; esac
  load=$(cut -d ' ' -f1 /proc/loadavg)
  awk -v current_load="$load" 'BEGIN {exit !(current_load < 8)}' || { echo "Load $load too high; retry later."; exit 3; }
  log=/home/benedict/rollback_codex_review/build-$service.log
  tar -cf - scripts/Dockerfile.review-layer services/common "services/$service" | DOCKER_BUILDKIT=0 docker build -f scripts/Dockerfile.review-layer --build-arg "BASE_IMAGE=omnidome-$service:pre-codex-review" --build-arg "SERVICE_NAME=$service" -t "omnidome-$service:latest" - > "$log" 2>&1
  docker compose up -d --no-deps --no-build --force-recreate "$service" > /home/benedict/rollback_codex_review/recreate-$service.log 2>&1
  for attempt in $(seq 1 18); do
    state=$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "omnidome-$service-1")
    if [[ "$state" == healthy ]]; then echo "$service healthy"; exit 0; fi
    if [[ "$state" == exited || "$state" == unhealthy ]]; then echo "$service $state; inspect local logs."; exit 1; fi
    sleep 5
  done
  echo "$service health did not settle; inspect local logs."
  exit 1
elif [[ "$step" == web ]]; then
  log=/home/benedict/rollback_codex_review/build-web.log
  DOCKER_BUILDKIT=0 docker compose build web > "$log" 2>&1
  docker compose up -d --no-deps --no-build --force-recreate web > /home/benedict/rollback_codex_review/recreate-web.log 2>&1
  for attempt in $(seq 1 18); do
    if curl -fsS --max-time 5 http://127.0.0.1:3000/auth > /dev/null; then echo 'web /auth 200'; exit 0; fi
    sleep 5
  done
  exit 1
else
  exit 2
fi
