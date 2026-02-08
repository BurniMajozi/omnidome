FROM python:3.11-slim

WORKDIR /app

COPY services/common/requirements.txt ./services/common/requirements.txt
COPY services/gateway/requirements.txt ./services/gateway/requirements.txt
ENV PIP_DEFAULT_TIMEOUT=300
ENV PIP_RETRIES=5
RUN pip install --no-cache-dir --trusted-host pypi.org --trusted-host pypi.python.org --trusted-host files.pythonhosted.org -r services/gateway/requirements.txt

COPY services/gateway/ ./services/gateway/
COPY services/common/ ./services/common/

ENV PYTHONPATH=/app

EXPOSE 8000

CMD ["python", "services/gateway/main.py"]
