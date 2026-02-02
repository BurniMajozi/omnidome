FROM python:3.11-slim

WORKDIR /app

COPY services/common/requirements.txt ./services/common/requirements.txt
COPY services/sales/requirements.txt ./services/sales/requirements.txt
RUN pip install --no-cache-dir -r services/sales/requirements.txt

COPY services/sales/ ./services/sales/
COPY services/common/ ./services/common/

ENV PYTHONPATH=/app

CMD ["python", "services/sales/main.py"]
