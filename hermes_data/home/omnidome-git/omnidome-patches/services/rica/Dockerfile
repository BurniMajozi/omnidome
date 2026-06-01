FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc && \
    rm -rf /var/lib/apt/lists/*

COPY services/common/requirements.txt /tmp/common-reqs.txt
RUN pip install --no-cache-dir -r /tmp/common-reqs.txt

COPY services/rica/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY services/common/ /app/services/common/
COPY services/rica/ /app/services/rica/

ENV PYTHONPATH=/app
ENV MODULE_ID=rica
ENV SERVICE_PORT=8004

EXPOSE 8004

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:8004/health || exit 1

CMD ["uvicorn", "services.rica.main:app", "--host", "0.0.0.0", "--port", "8004", "--workers", "2"]
