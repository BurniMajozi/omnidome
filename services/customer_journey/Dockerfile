FROM python:3.11-slim

WORKDIR /app

COPY services/customer_journey/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/common/ services/common/
COPY services/customer_journey/ services/customer_journey/

EXPOSE 8022

CMD ["uvicorn", "services.customer_journey.main:app", "--host", "0.0.0.0", "--port", "8022"]
