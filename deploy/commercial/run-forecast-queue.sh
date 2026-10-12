#!/usr/bin/env bash
set -euo pipefail
cd /home/benedict/omnidome
exec 9>/home/benedict/forecast-queue.lock
flock -n 9 || exit 0
export COMPOSE_FILE=docker-compose.yaml:docker-compose.override.yml:docker-compose.local.yml
docker compose --profile forecast run --rm --no-deps --pull never forecaster --pending
