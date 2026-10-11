#!/usr/bin/env bash
set -euo pipefail
cd /home/benedict/omnidome
source_root=/mnt/c/Users/Benedict/Desktop/OminiDome/omnidome
export COMPOSE_FILE=docker-compose.yaml:docker-compose.override.yml:docker-compose.local.yml:deploy/commercial/shadow.yml
finished=false
for image in admin billing; do docker tag "omnidome-$image:latest" "omnidome-$image:pre-commercial-final"; done
restore() {
  if [[ "$finished" != true ]]; then
    for image in admin billing; do docker tag "omnidome-$image:pre-commercial-final" "omnidome-$image:latest"; done
    docker compose up -d --no-build --no-deps --force-recreate admin billing > /home/benedict/build_logs/rollback-commercial-final.log 2>&1
  fi
}
trap restore EXIT
for image in admin billing; do
  tar -cf - -C "$source_root" deploy/commercial/final.Dockerfile services/common/platform_usage.py services/admin/commercial.py |
    DOCKER_BUILDKIT=0 docker build --build-arg "BASE_IMAGE=omnidome-$image:pre-commercial-final" -f deploy/commercial/final.Dockerfile -t "omnidome-$image:latest" - > "/home/benedict/build_logs/final-commercial-$image.log" 2>&1
done
rsync -a "$source_root/services/common/platform_usage.py" services/common/platform_usage.py
rsync -a "$source_root/services/admin/commercial.py" services/admin/commercial.py
docker compose up -d --no-build --no-deps --force-recreate admin billing > /home/benedict/build_logs/recreate-commercial-final.log 2>&1
finished=true
echo 'Final policy schema and expiry checks deployed.'
