FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
COPY services/fno_intelligence/ /app/services/fno_intelligence/
COPY services/common/ /app/services/common/

EXPOSE 8024

CMD ["uvicorn", "services.fno_intelligence.main:app", "--host", "0.0.0.0", "--port", "8024"]
