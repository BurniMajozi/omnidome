#!/usr/bin/env bash
# Staggered, IDEMPOTENT local startup for the lean OmniDome stack.
#
# WHY THIS EXISTS: this host's CPU (Intel N150, 4 logical processors, 3 given
# to WSL) cannot absorb every service's cold-start (Python import + uvicorn
# boot, or Next.js boot) landing on the CPU at the same instant. Starting them
# all in parallel (`docker compose up -d <all>`) saturates all 3 vCPUs and can
# trip WSL2's VM heartbeat timeout, which resets the VM/dockerd -- which then
# restarts everything in parallel again (a feedback loop). This script starts
# missing services ONE AT A TIME with a gap, and SKIPS ones already running,
# so re-running it after a partial crash only restarts what's actually down.
#
# Usage: cd ~/omnidome && bash scripts/start-local.sh
# Invoked automatically by the omnidome-watch user service (see
# scripts/omnidome-watch.service / scripts/install-local-autostart.sh).

set -u
cd "$(dirname "$0")/.." || exit 1
export COMPOSE_FILE=docker-compose.yaml:docker-compose.override.yml:docker-compose.local.yml

STAGGER_SECONDS="${STAGGER_SECONDS:-8}"

is_up() {
  # "true" if a container for this compose service is Up (any health state).
  st=$(docker compose ps --format '{{.Service}} {{.State}}' 2>/dev/null | awk -v s="$1" '$1==s{print $2}')
  [ "$st" = "running" ]
}

# db first -- everything else depends on it being reachable.
if ! is_up db; then
  echo "[start-local] starting db..."
  docker compose up -d --no-deps db
  echo "[start-local] waiting for db to be healthy..."
  for i in $(seq 1 30); do
    status=$(docker inspect -f '{{.State.Health.Status}}' omnidome-db-1 2>/dev/null)
    [ "$status" = "healthy" ] && { echo "[start-local] db healthy"; break; }
    sleep 2
  done
else
  echo "[start-local] db already up, skipping"
fi

# The rest of the lean set, one at a time -- only the ones not already up.
SERVICES="gateway crm sales marketing iot web"

for s in $SERVICES; do
  if is_up "$s"; then
    echo "[start-local] $s already up, skipping"
    continue
  fi
  echo "[start-local] starting $s ..."
  docker compose up -d --no-deps "$s"
  sleep "$STAGGER_SECONDS"
done

echo "[start-local] done. Status:"
docker ps --format '{{.Names}}\t{{.Status}}' | sort
