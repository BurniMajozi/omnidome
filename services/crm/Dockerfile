FROM python:3.12-slim AS builder

WORKDIR /build

COPY services/common/requirements.txt ./services/common/requirements.txt
COPY services/crm/requirements.txt ./services/crm/requirements.txt
RUN pip install --no-cache-dir --trusted-host pypi.org --trusted-host files.pythonhosted.org --default-timeout=100 --retries 5 -r services/crm/requirements.txt
# customer_360.py reads models directly from these sibling services (shared Postgres) —
# pull in the one dependency among them not already covered by services/crm/requirements.txt.
RUN pip install --no-cache-dir --trusted-host pypi.org --trusted-host files.pythonhosted.org --default-timeout=100 --retries 5 scikit-learn==1.5.1 numpy==1.26.4

FROM python:3.12-slim

WORKDIR /app

COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

COPY services/crm/ ./services/crm/
COPY services/common/ ./services/common/
# customer_360.py and dashboard.py import models directly from these sibling
# services (all share the same Postgres) rather than calling them over HTTP.
COPY services/billing/ ./services/billing/
COPY services/customer_journey/ ./services/customer_journey/
COPY services/sales/ ./services/sales/
COPY services/support/ ./services/support/
COPY services/lifecycle/ ./services/lifecycle/
COPY services/retention/ ./services/retention/

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8001/health')" || exit 1

CMD ["uvicorn", "services.crm.main:app", "--host", "0.0.0.0", "--port", "8001", "--workers", "1"]
