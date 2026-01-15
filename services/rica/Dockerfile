FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/rica/ ./services/rica/
COPY requirements.txt .

ENV PYTHONPATH=/app

CMD ["python", "services/rica/main.py"]
