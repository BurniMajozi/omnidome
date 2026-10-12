#!/usr/bin/env bash
set -euo pipefail
exec 9>/home/benedict/platform-billing-deploy.lock
flock -n 9 || { echo 'A deployment is running; recovery will not interfere.'; exit 1; }
watcher=false
systemctl --user is-active --quiet omnidome-watch.service && watcher=true
[[ "$watcher" != true ]] || systemctl --user stop omnidome-watch.service
restore_watch() { [[ "$watcher" != true ]] || systemctl --user start omnidome-watch.service; }
trap restore_watch EXIT
for attempt in $(seq 1 30); do
  [[ "$(docker inspect --format '{{.State.Health.Status}}' omnidome-db-1)" != healthy ]] || break
  sleep 2
done
[[ "$(docker inspect --format '{{.State.Health.Status}}' omnidome-db-1)" == healthy ]]
for service in web communication billing agent-orchestrator tenant_memory admin crm sales inventory hr finance call_center marketing journey_engine compliance portal-builder support gateway fno_intelligence lifecycle rica; do
  container="omnidome-$service-1"
  state=$(docker inspect --format '{{.State.Status}} {{.State.ExitCode}}' "$container")
  if [[ "$state" == running* ]]; then echo "$service already running."; continue; fi
  # WSL termination marks affected containers 255. Do not revive services which
  # had already been deliberately stopped (Autumn, network, voicebox, IoT, etc.).
  [[ "$state" == 'exited 255' ]] || { echo "$service left in its earlier stopped state."; continue; }
  for attempt in $(seq 1 18); do
    read -r load _ < /proc/loadavg
    awk -v value="$load" 'BEGIN {exit !(value<6)}' && break
    sleep 5
  done
  docker start "$container" >/dev/null
  echo "Started $service."
  sleep 10
done
curl --fail --silent --max-time 30 --output /dev/null http://127.0.0.1:3000/
echo 'Localhost web is responding.'
