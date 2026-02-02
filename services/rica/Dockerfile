FROM python:3.11-slim

WORKDIR /app

COPY services/common/requirements.txt ./services/common/requirements.txt
COPY services/rica/requirements.txt ./services/rica/requirements.txt
RUN pip install --no-cache-dir -r services/rica/requirements.txt

COPY services/rica/ ./services/rica/
COPY services/common/ ./services/common/

ENV PYTHONPATH=/app

CMD ["python", "services/rica/main.py"]
