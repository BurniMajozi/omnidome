ARG BASE_IMAGE
FROM ${BASE_IMAGE}
RUN pip install --no-cache-dir pytest
COPY services/common /app/services/common
COPY services/admin /app/services/admin
COPY services/billing /app/services/billing
COPY apps/web/lib/platform-pricing.json /app/services/common/platform-pricing.json
COPY deploy/commercial/test-platform-billing.py /app/test-platform-billing.py
CMD ["python", "/app/test-platform-billing.py"]
