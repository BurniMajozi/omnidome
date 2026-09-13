FROM python:3.12-slim AS builder

WORKDIR /build

COPY services/common/requirements.txt ./services/common/requirements.txt
COPY services/marketing/requirements.txt ./services/marketing/requirements.txt
COPY services/analytics_worker/requirements.txt ./services/analytics_worker/requirements.txt
RUN pip install --no-cache-dir --trusted-host pypi.org --trusted-host files.pythonhosted.org --default-timeout=100 --retries 5 -r services/analytics_worker/requirements.txt

FROM python:3.12-slim

WORKDIR /app

COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

COPY services/marketing/ ./services/marketing/
COPY services/common/ ./services/common/
COPY services/analytics_worker/ ./services/analytics_worker/

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# No HTTP port — this is a background worker driven by an internal scheduler.
CMD ["python", "-m", "services.analytics_worker.worker"]
