#!/usr/bin/env bash
# Standalone Hermes container (NOT part of docker-compose -- kept separate
# from the app stack's staggered start/watchdog since it's a single container
# and already self-restarts). Run from the mirror: bash scripts/run-hermes.sh
#
# Re-run this any time env vars (Telegram token, API key, etc.) change --
# it removes and recreates the container so the new env takes effect.
set -u
REPO=/mnt/c/Users/Benedict/Desktop/OminiDome/omnidome
ENVF="$REPO/.env"
val() { grep -E "^$1=" "$ENVF" | head -1 | cut -d= -f2- | tr -d '\r'; }

# SQLite in hermes_data needs a real (ext4) fs -- keep a synced ext4 copy
# rather than binding the /mnt/c path directly (9p breaks SQLite locking).
if [ ! -d ~/hermes_data ]; then
  echo "copying hermes_data -> ext4 (~/hermes_data)"
  cp -a "$REPO/hermes_data" ~/hermes_data
fi

OPENROUTER=$(val OPENROUTER_API_KEY)
TG_TOKEN=$(val TELEGRAM_BOT_TOKEN)
TG_USERS=$(val TELEGRAM_ALLOWED_USERS)
HKEY=$(val HERMES_API_KEY)
echo "openrouter_len=${#OPENROUTER} telegram_token_len=${#TG_TOKEN} hermeskey_len=${#HKEY}"

docker rm -f hermes-agent >/dev/null 2>&1
docker run -d --name hermes-agent --restart unless-stopped \
  -p 8642:8642 \
  -v /home/benedict/hermes_data:/opt/data \
  -v /mnt/c/Users/Benedict/Desktop/OminiDome:/opt/data/workspace \
  -e OPENROUTER_API_KEY="$OPENROUTER" \
  -e TELEGRAM_BOT_TOKEN="$TG_TOKEN" \
  -e TELEGRAM_ALLOWED_USERS="$TG_USERS" \
  -e OBSIDIAN_VAULT_PATH=/opt/data/workspace/omnidome/Hermes-Obsidian \
  -e API_SERVER_ENABLED=true \
  -e API_SERVER_KEY="$HKEY" \
  -e API_SERVER_HOST=0.0.0.0 \
  nousresearch/hermes-agent:latest gateway run
echo "RUN_EXIT=$?"
sleep 8
echo "=== status ==="
docker ps -a --format "{{.Names}} {{.Status}}" | grep hermes-agent || echo "NOT RUNNING"
echo "=== recent logs ==="
docker logs hermes-agent 2>&1 | tail -30
