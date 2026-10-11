ARG BASE_IMAGE
FROM ${BASE_IMAGE}
COPY services/common /app/services/common
COPY apps/web/lib/platform-pricing.json /app/services/common/platform-pricing.json
COPY services/admin /app/services/admin
COPY services/billing /app/services/billing
COPY services/agent_orchestrator /app/services/agent_orchestrator
