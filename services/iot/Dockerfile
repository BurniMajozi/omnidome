FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt* ./
RUN pip install --no-cache-dir --default-timeout=100 --retries 5 -r requirements.txt 2>/dev/null || \
    pip install --no-cache-dir --default-timeout=100 --retries 5 fastapi uvicorn sqlalchemy asyncpg httpx websockets pyjwt cryptography

# Copy shared modules
COPY services/common/ ./services/common/

# Copy service code
COPY services/iot/ ./services/iot/

# Create non-root user
RUN groupadd -r appuser && useradd -r -g appuser appuser
# Skip chown on Windows/Docker Desktop - runs as root for compatibility
# RUN chown -R appuser:appuser /app
# USER appuser

EXPOSE 8006

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8006/health')" || exit 1

CMD ["uvicorn", "services.iot.main:app", "--host", "0.0.0.0", "--port", "8006", "--workers", "1"]
