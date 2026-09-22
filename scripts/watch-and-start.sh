#!/usr/bin/env bash
# Polling watchdog: every POLL_SECONDS, ensure the lean OmniDome stack is up,
# bringing back anything missing via the staggered start-local.sh (which is
# idempotent -- it skips services that are already running). This is how the
# stack recovers automatically after a dockerd crash/restart or a WSL reboot,
# without a storm of everything restarting in parallel at once (see
# docker-compose.local.yml for why that mattered on this host).
#
# Run as a user systemd service (scripts/omnidome-watch.service) so it needs
# no root and survives across WSL boots once `loginctl enable-linger` is set.

set -u
cd "$(dirname "$0")/.." || exit 1
POLL_SECONDS="${POLL_SECONDS:-20}"

# Let dockerd settle after its own (re)start before the first check.
sleep 10

while true; do
  if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
    bash scripts/start-local.sh >> /home/benedict/omnidome-watch.log 2>&1
  else
    echo "[watch] dockerd not reachable yet, waiting..." >> /home/benedict/omnidome-watch.log
  fi
  sleep "$POLL_SECONDS"
done
