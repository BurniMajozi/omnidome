FROM python:3.11-slim

WORKDIR /app

COPY services/common/requirements.txt ./services/common/requirements.txt
COPY services/crm/requirements.txt ./services/crm/requirements.txt
RUN pip install --no-cache-dir -r services/crm/requirements.txt

COPY services/crm/ ./services/crm/
COPY services/common/ ./services/common/

ENV PYTHONPATH=/app

CMD ["python", "services/crm/main.py"]
