FROM python:3.11-slim

WORKDIR /app

COPY services/common/requirements.txt ./services/common/requirements.txt
COPY services/billing/requirements.txt ./services/billing/requirements.txt
RUN pip install --no-cache-dir -r services/billing/requirements.txt

COPY services/billing/ ./services/billing/
COPY services/common/ ./services/common/

ENV PYTHONPATH=/app

CMD ["python", "services/billing/main.py"]
