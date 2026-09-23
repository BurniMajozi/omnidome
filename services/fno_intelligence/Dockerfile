FROM python:3.12-slim AS builder

WORKDIR /build

COPY services/common/requirements.txt ./services/common/requirements.txt
COPY services/fno_intelligence/requirements.txt ./services/fno_intelligence/requirements.txt
RUN pip install --no-cache-dir --trusted-host pypi.org --trusted-host files.pythonhosted.org --default-timeout=100 --retries 5 -r services/fno_intelligence/requirements.txt

FROM python:3.12-slim

WORKDIR /app

COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

COPY services/fno_intelligence/ ./services/fno_intelligence/
COPY services/common/ ./services/common/

# fno_intelligence directly imports these services' SQLAlchemy models for
# cross-service reads against the shared DB (all services point at the same
# Postgres instance -- see docker-compose.yaml) instead of an HTTP hop, same
# pattern services/crm/Dockerfile already uses for its own cross-imports.
# Needed by: _notify_affected_customers (network fault notifications --
# this import was already present in routes.py but this Dockerfile never
# copied services/network/, so it would ModuleNotFoundError; found while
# testing Ticket 3, which hits the identical gap for services/sales/) and
# suppression.py's Ticket 3 customer-suppression check (sales.Contact,
# network.NetworkService). Their own requirements (sqlalchemy, psycopg2-binary,
# httpx, pydantic) are already covered by this image's requirements.txt.
COPY services/sales/ ./services/sales/
COPY services/network/ ./services/network/

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Bind host: 0.0.0.0 (IPv4) for local Docker; :: (IPv6 dual-stack) for Railway private networking
ENV UVICORN_HOST=0.0.0.0

EXPOSE 8024

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8024/health')" || exit 1

CMD ["sh", "-c", "uvicorn services.fno_intelligence.main:app --host ${UVICORN_HOST} --port 8024 --workers 2"]
