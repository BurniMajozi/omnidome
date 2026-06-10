FROM python:3.12-slim AS builder

WORKDIR /app
COPY services/common/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

FROM python:3.12-slim

RUN groupadd -r appuser && useradd -r -g appuser appuser

WORKDIR /app
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

COPY services/compliance/ ./services/compliance/
COPY services/common/ ./services/common/

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

USER appuser

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8019/health')"

CMD ["uvicorn", "services.compliance.main:app", "--host", "0.0.0.0", "--port", "8019", "--workers", "2"]
