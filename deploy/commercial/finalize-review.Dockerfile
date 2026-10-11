ARG BASE_IMAGE
FROM ${BASE_IMAGE}
COPY services/common /app/services/common
COPY apps/web/lib/platform-pricing.json /app/services/common/platform-pricing.json
COPY services/admin/pricing.py /app/services/admin/pricing.py
COPY services/admin/commercial.py /app/services/admin/commercial.py
COPY services/billing/routes/platform_checkout.py /app/services/billing/routes/platform_checkout.py
COPY services/agent_orchestrator/commercial_usage.py /app/services/agent_orchestrator/commercial_usage.py
