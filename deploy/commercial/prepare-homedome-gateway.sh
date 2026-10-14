#!/usr/bin/env bash
set -euo pipefail
source_root=/mnt/c/Users/Benedict/Desktop/OminiDome/omnidome
compose_file="$source_root/deploy/commercial/homedome-gateway.yml"
# This is an independent project: do not stop or recreate the platform.
docker compose -f "$compose_file" config --quiet
if ! docker image inspect ghcr.io/home-assistant/home-assistant:2026.10.1 >/dev/null 2>&1; then
  host_available=$(df --output=avail -B1 /mnt/c | tail -1)
  if (( host_available < 8 * 1024 * 1024 * 1024 )); then
    echo 'Free at least 8 GiB on Windows C: before downloading and unpacking Home Assistant.' >&2
    exit 1
  fi
fi
docker compose -f "$compose_file" pull --quiet
docker compose -f "$compose_file" up -d
for attempt in {1..90}; do
  if curl --max-time 5 --fail --silent --output /dev/null http://127.0.0.1:8123/; then
    echo 'Home Assistant onboarding is ready at http://localhost:8123.'
    exit 0
  fi
  sleep 2
done
echo 'Gateway started but did not become ready. Inspect docker logs omnidome-home-gateway.' >&2
exit 1
