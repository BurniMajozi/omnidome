#!/usr/bin/env bash
# One-time setup: install the self-healing staggered-startup watchdog as a
# USER systemd service (no root/sudo needed) and enable it to survive across
# WSL boots via `loginctl enable-linger`.
#
# Run from the mirror checkout: cd ~/omnidome && bash scripts/install-local-autostart.sh
set -eu
cd "$(dirname "$0")/.." || exit 1

mkdir -p "$HOME/.config/systemd/user"
cp scripts/omnidome-watch.service "$HOME/.config/systemd/user/omnidome-watch.service"
chmod +x scripts/start-local.sh scripts/watch-and-start.sh

loginctl enable-linger "$(whoami)" || true

systemctl --user daemon-reload
systemctl --user enable --now omnidome-watch.service

echo "Installed. Status:"
systemctl --user status omnidome-watch.service --no-pager | head -10
