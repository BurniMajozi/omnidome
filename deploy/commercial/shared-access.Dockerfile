ARG BASE_IMAGE
FROM ${BASE_IMAGE}
COPY services/common /app/services/common
COPY apps/web/lib/platform-pricing.json /app/services/common/platform-pricing.json
