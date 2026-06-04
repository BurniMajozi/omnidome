FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
COPY services/billing_collections/ /app/services/billing_collections/
COPY services/common/ /app/services/common/

EXPOSE 8023

CMD ["uvicorn", "services.billing_collections.main:app", "--host", "0.0.0.0", "--port", "8023"]
