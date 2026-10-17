#!/usr/bin/env bash
# Recovery: recreate knowledge_indexer then tenant_memory with working knowledge-DB settings when a recreate dropped them
# (KNOWLEDGE_DB_URL comes from the caller's shell, not from .env). Uses the knowledge_db OWNER password from its container,
# sets a NEW random password for the knowledge_app role (the indexer's ensure_schema applies it with ALTER ROLE), and passes
# everything in the child environment only: nothing is printed or written to disk.
set -euo pipefail
cd /home/benedict/omnidome
source_root=/mnt/c/Users/Benedict/Desktop/OminiDome/omnidome
export COMPOSE_FILE="docker-compose.yaml:docker-compose.override.yml:docker-compose.local.yml:$source_root/deploy/commercial/shadow.yml"
owner_pw=$(docker exec omnidome-knowledge_db-1 printenv POSTGRES_PASSWORD)
app_pw=$(python3 -c 'import secrets; print(secrets.token_hex(24))')
export KNOWLEDGE_DB_URL="postgresql://knowledge_app:${app_pw}@knowledge_db:5432/knowledge"
export KNOWLEDGE_DB_ADMIN_URL="postgresql://knowledge_owner:${owner_pw}@knowledge_db:5432/knowledge"
export KNOWLEDGE_APP_PASSWORD="$app_pw"
export KNOWLEDGE_ENABLED=true EMBEDDING_MODEL=nomic-embed-text EMBEDDING_DIM=768 KNOWLEDGE_OLLAMA_URL=http://ollama:11434
docker compose --profile knowledge up -d --no-deps --no-build --force-recreate knowledge_indexer
for i in $(seq 1 30); do
  [[ "$(docker inspect --format '{{.State.Status}}' omnidome-knowledge_indexer-1)" == running ]] && sleep 8 && break; sleep 2
done
docker compose up -d --no-deps --no-build --force-recreate tenant_memory
echo "knowledge env restored (new knowledge_app password applied)."
