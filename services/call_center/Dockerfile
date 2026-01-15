FROM python:3.11-slim

WORKDIR /app

COPY services/call_center/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/call_center/main.py .

CMD ["python", "main.py"]
