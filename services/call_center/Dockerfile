FROM python:3.11-slim

WORKDIR /app

COPY services/common/requirements.txt ./services/common/requirements.txt
COPY services/call_center/requirements.txt ./services/call_center/requirements.txt
RUN pip install --no-cache-dir -r services/call_center/requirements.txt

COPY services/call_center/main.py .
COPY services/common/ ./services/common/

ENV PYTHONPATH=/app

CMD ["python", "main.py"]
