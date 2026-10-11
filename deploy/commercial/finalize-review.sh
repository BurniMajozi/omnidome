#!/usr/bin/env bash
set -euo pipefail
cd /home/benedict/omnidome
source_root=/mnt/c/Users/Benedict/Desktop/OminiDome/omnidome
export COMPOSE_FILE=docker-compose.yaml:docker-compose.override.yml:docker-compose.local.yml:deploy/commercial/shadow.yml
for service in admin billing agent-orchestrator; do
  image=$(docker inspect --format '{{.Config.Image}}' "omnidome-$service-1")
  docker tag "$image" "omnidome-review-$service:before-owner-proration"
  tar -cf - -C "$source_root" deploy/commercial/finalize-review.Dockerfile services/common services/admin/pricing.py services/admin/commercial.py services/billing/routes/platform_checkout.py services/agent_orchestrator/commercial_usage.py apps/web/lib/platform-pricing.json |
    DOCKER_BUILDKIT=0 docker build --build-arg "BASE_IMAGE=$image" -f deploy/commercial/finalize-review.Dockerfile -t "$image" - > "/home/benedict/build_logs/review-final-$service.log" 2>&1
  echo "Updated $service with owner proration and platform credit accounting."
done
rsync -a "$source_root/services/common/" services/common/
rsync -a "$source_root/services/admin/pricing.py" services/admin/pricing.py
rsync -a "$source_root/services/admin/commercial.py" services/admin/commercial.py
rsync -a "$source_root/services/billing/routes/platform_checkout.py" services/billing/routes/platform_checkout.py
rsync -a "$source_root/services/agent_orchestrator/commercial_usage.py" services/agent_orchestrator/commercial_usage.py
docker compose up -d --no-deps --no-build --force-recreate admin billing agent-orchestrator
echo "Backend overlay complete. Sync the reviewed frontend files and rebuild web separately; credit pricing remains unpublished until the Platform Owner enables it."
