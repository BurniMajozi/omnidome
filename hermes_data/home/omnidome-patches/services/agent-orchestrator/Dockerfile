FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc && \
    rm -rf /var/lib/apt/lists/*

COPY services/common/requirements.txt /tmp/common-reqs.txt
RUN pip install --no-cache-dir -r /tmp/common-reqs.txt

COPY services/agent-orchestrator/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY services/common/ /app/services/common/
COPY services/agent-orchestrator/ /app/services/agent-orchestrator/

ENV PYTHONPATH=/app
ENV MODULE_ID=agents
ENV SERVICE_PORT=8021
ENV OLLAMA_BASE_URL=http://ollama:11434
ENV REDIS_URL=redis://redis:6379

EXPOSE 8021

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:8021/health || exit 1

CMD ["uvicorn", "services.agent_orchestrator.main:app", "--host", "0.0.0.0", "--port", "8021", "--workers", "2"]
