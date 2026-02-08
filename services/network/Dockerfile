FROM python:3.11-slim

# Playwright system deps commented out for now (uncomment when enabling browser adapters)
# RUN apt-get update && apt-get install -y \
#     libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
#     libxkbcommon0 libxcomposite1 libxdamage1 libxext6 libxfixes3 \
#     libxrandr2 libgbm1 libasound2 libpango-1.0-0 libcairo2 \
#     && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY services/common/requirements.txt ./services/common/requirements.txt
COPY services/network/requirements.txt ./services/network/requirements.txt
ENV PIP_DEFAULT_TIMEOUT=300
ENV PIP_RETRIES=5
RUN pip install --no-cache-dir --trusted-host pypi.org --trusted-host pypi.python.org --trusted-host files.pythonhosted.org -r services/network/requirements.txt
# RUN playwright install chromium --with-deps

COPY services/network/ ./services/network/
COPY services/common/ ./services/common/

ENV PYTHONPATH=/app
EXPOSE 8005

CMD ["python", "services/network/main.py"]
