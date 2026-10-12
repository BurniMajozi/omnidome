#!/usr/bin/env bash
set -euo pipefail
source_root=/mnt/c/Users/Benedict/Desktop/OminiDome/omnidome
docker run --rm -i --memory=1536m --cpus=2 -v omnidome_forecast_models:/models --entrypoint python omnidome-forecaster:chronos-verified - < "$source_root/deploy/commercial/check-chronos-runtime.py"
docker tag omnidome-forecaster:chronos-verified omnidome-forecaster:latest
cd /home/benedict/omnidome
export COMPOSE_FILE=docker-compose.yaml:docker-compose.override.yml:docker-compose.local.yml
docker compose --profile forecast run --rm --no-deps -T --entrypoint python forecaster - < "$source_root/deploy/commercial/check-chronos-runtime.py"
rsync -a "$source_root/services/forecaster/" services/forecaster/
mkdir -p /home/benedict/.config/systemd/user
ln -sf "$source_root/deploy/commercial/omnidome-forecast.service" /home/benedict/.config/systemd/user/omnidome-forecast.service
ln -sf "$source_root/deploy/commercial/omnidome-forecast.timer" /home/benedict/.config/systemd/user/omnidome-forecast.timer
systemctl --user daemon-reload
systemctl --user enable --now omnidome-forecast.timer
systemctl --user start omnidome-forecast.service
systemctl --user is-active omnidome-forecast.timer
