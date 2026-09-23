FROM python:3.12-slim AS builder

WORKDIR /build

COPY services/common/requirements.txt ./services/common/requirements.txt
COPY services/journey_engine/requirements.txt ./services/journey_engine/requirements.txt
RUN pip install --no-cache-dir --trusted-host pypi.org --trusted-host files.pythonhosted.org --default-timeout=100 --retries 5 -r services/journey_engine/requirements.txt

FROM python:3.12-slim

WORKDIR /app

COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

COPY services/journey_engine/ ./services/journey_engine/
COPY services/common/ ./services/common/

# journey_engine/main.py directly imports services.network.models
# (NetworkService, NetworkDevice, FNOOrder) for the cancellation-workflow
# endpoint -- this Dockerfile never copied services/network/, so that
# endpoint 500ed on every request (ModuleNotFoundError), not just its
# background cancellation task. Found 2026-09-23 while auditing the
# BackgroundTasks-silently-never-runs bug across the fleet. Same pattern as
# services/crm/Dockerfile and services/fno_intelligence/Dockerfile.
COPY services/network/ ./services/network/

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Bind host: 0.0.0.0 (IPv4) for local Docker; :: (IPv6 dual-stack) for Railway private networking
ENV UVICORN_HOST=0.0.0.0

EXPOSE 8017

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8017/health')" || exit 1

CMD ["sh", "-c", "uvicorn services.journey_engine.main:app --host ${UVICORN_HOST} --port 8017 --workers 2"]
