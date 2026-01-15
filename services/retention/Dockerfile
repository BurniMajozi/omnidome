FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/retention/ ./services/retention/
COPY requirements.txt .

ENV PYTHONPATH=/app

CMD ["python", "services/retention/main.py"]
