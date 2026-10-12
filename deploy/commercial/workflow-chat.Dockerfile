ARG BASE_IMAGE
FROM ${BASE_IMAGE}
COPY services/agent_orchestrator /app/services/agent_orchestrator
COPY services/common /app/services/common
