ARG BASE_IMAGE
FROM ${BASE_IMAGE}
COPY services/common/platform_usage.py /app/services/common/platform_usage.py
COPY services/admin/commercial.py /app/services/admin/commercial.py
