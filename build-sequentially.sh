#!/bin/bash
cd ~/omnidome
SERVICES=(
  db
  crm
  sales
  billing
  finance
  rica
  network
  iot
  call_center
  retention
  marketing
  admin
  gateway
  journey_engine
  web_analytics
  lifecycle
  web
  portal
)

for service in "${SERVICES[@]}"; do
  echo "========================================="
  echo "Building and starting: $service"
  echo "========================================="
  docker compose build "$service"
  docker compose up -d "$service"
done
echo "========================================="
echo "All services built and started successfully!"
echo "========================================="
