#!/usr/bin/env bash
set -euo pipefail
base=$(docker inspect --format '{{.Image}}' omnidome-fno_intelligence-1)
tar -cf - -C /mnt/c/Users/Benedict/Desktop/OminiDome/omnidome deploy/commercial/chronos-local.Dockerfile services/forecaster services/fno_intelligence/metric_catalog.py |
 docker build --memory=2g --cpu-period=100000 --cpu-quota=100000 --build-arg "BASE_IMAGE=$base" -f deploy/commercial/chronos-local.Dockerfile -t omnidome-forecaster:chronos-verified - > /home/benedict/build_logs/chronos-build.log 2>&1
