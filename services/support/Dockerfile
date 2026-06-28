FROM python:3.12-slim AS builder

WORKDIR /build

COPY services/common/requirements.txt ./services/common/requirements.txt
COPY services/support/requirements.txt ./services/support/requirements.txt
RUN pip install --no-cache-dir --user --trusted-host pypi.org --trusted-host files.pythonhosted.org -r services/support/requirements.txt

FROM python:3.12-slim

RUN groupadd -r appuser && useradd -r -g appuser -d /app -s /sbin/nologin appuser

WORKDIR /app

COPY --from=builder /root/.local /app/.local
ENV PATH=/app/.local/bin:$PATH

COPY services/support/ ./services/support/
COPY services/common/ ./services/common/

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

RUN chown -R appuser:appuser /app /home/appuser

USER appuser

EXPOSE 8008

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8008/health')" || exit 1

CMD ["uvicorn", "services.support.main:app", "--host", "0.0.0.0", "--port", "8008", "--workers", "2"]
