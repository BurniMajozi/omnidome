#!/usr/bin/env bash
# Start (or recreate) the knowledge indexer with its database credentials.
#
# The indexer needs the knowledge DB OWNER url to run migrations; the app role cannot create tables. Those values are
# not kept in .env, so read them from the running containers at start time. Nothing is printed or written to disk.
set -euo pipefail
cd "$(dirname "$0")/.."
export COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yaml:docker-compose.override.yml:docker-compose.local.yml}"

owner_pw=$(docker exec omnidome-knowledge_db-1 printenv POSTGRES_PASSWORD)
app_url=$(docker exec omnidome-tenant_memory-1 printenv KNOWLEDGE_DB_URL)
app_pw=$(APP_URL="$app_url" python3 -c 'import os; from urllib.parse import urlsplit, unquote; print(unquote(urlsplit(os.environ["APP_URL"]).password or ""))')

export KNOWLEDGE_DB_URL="$app_url"
export KNOWLEDGE_DB_ADMIN_URL="postgresql://knowledge_owner:${owner_pw}@knowledge_db:5432/knowledge"
export KNOWLEDGE_APP_PASSWORD="$app_pw"

docker compose --profile knowledge up -d --no-deps knowledge_indexer
