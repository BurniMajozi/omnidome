FROM python:3.11-slim

WORKDIR /app

COPY services/common/requirements.txt /tmp/common-reqs.txt
RUN pip install --no-cache-dir -r /tmp/common-reqs.txt

COPY services/communication/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY services/common/ /app/services/common/
COPY services/communication/ /app/services/communication/

ENV PYTHONPATH=/app
ENV MODULE_ID=communication
ENV SERVICE_PORT=8020

EXPOSE 8020

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:8020/health || exit 1

CMD ["uvicorn", "services.communication.main:app", "--host", "0.0.0.0", "--port", "8020", "--workers", "2"]
