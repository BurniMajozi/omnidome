ARG BASE_IMAGE
FROM ${BASE_IMAGE}
COPY services/agent_orchestrator/main.py /app/services/agent_orchestrator/main.py
COPY services/agent_orchestrator/billing_workflows.py /app/services/agent_orchestrator/billing_workflows.py
