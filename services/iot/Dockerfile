FROM python:3.11-slim

WORKDIR /app

COPY services/common/requirements.txt ./services/common/requirements.txt
COPY services/iot/requirements.txt ./services/iot/requirements.txt
RUN pip install --no-cache-dir -r services/iot/requirements.txt

COPY services/iot/ ./services/iot/
COPY services/common/ ./services/common/

ENV PYTHONPATH=/app

CMD ["python", "services/iot/main.py"]
