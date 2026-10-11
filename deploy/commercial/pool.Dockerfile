ARG BASE_IMAGE
FROM ${BASE_IMAGE}
COPY services/common/db.py /app/services/common/db.py
ENV DB_POOL_SIZE=1 DB_MAX_OVERFLOW=1
