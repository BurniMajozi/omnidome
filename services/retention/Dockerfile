FROM python:3.11-slim

WORKDIR /app

COPY services/common/requirements.txt ./services/common/requirements.txt
COPY services/retention/requirements.txt ./services/retention/requirements.txt
RUN pip install --no-cache-dir -r services/retention/requirements.txt

COPY services/retention/ ./services/retention/
COPY services/common/ ./services/common/

ENV PYTHONPATH=/app

CMD ["python", "services/retention/main.py"]
