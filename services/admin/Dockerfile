FROM python:3.11-slim

WORKDIR /app

COPY services/common/requirements.txt ./services/common/requirements.txt
COPY services/admin/requirements.txt ./services/admin/requirements.txt
RUN pip install --no-cache-dir -r services/admin/requirements.txt

COPY services/admin/ ./services/admin/
COPY services/common/ ./services/common/

ENV PYTHONPATH=/app

CMD ["python", "services/admin/main.py"]
