FROM python:3.11-slim

WORKDIR /app

COPY services/common/requirements.txt ./services/common/requirements.txt
COPY services/gateway/requirements.txt ./services/gateway/requirements.txt
RUN pip install --no-cache-dir -r services/gateway/requirements.txt

COPY services/gateway/ ./services/gateway/
COPY services/common/ ./services/common/

ENV PYTHONPATH=/app

CMD ["python", "services/gateway/main.py"]
