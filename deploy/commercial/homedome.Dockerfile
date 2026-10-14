ARG BASE_IMAGE
FROM ${BASE_IMAGE}
COPY services/iot /app/services/iot
COPY services/common /app/services/common
COPY apps/web/lib/platform-pricing.json /app/apps/web/lib/platform-pricing.json
RUN python -c "from zoneinfo import ZoneInfo; ZoneInfo('Africa/Johannesburg'); import cryptography, websockets"
