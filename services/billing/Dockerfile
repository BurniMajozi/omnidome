FROM python:3.11-slim

WORKDIR /app

COPY services/common/requirements.txt ./services/common/requirements.txt
COPY services/billing/requirements.txt ./services/billing/requirements.txt
ENV PIP_DEFAULT_TIMEOUT=300
ENV PIP_RETRIES=5
RUN pip install --no-cache-dir --trusted-host pypi.org --trusted-host pypi.python.org --trusted-host files.pythonhosted.org -r services/billing/requirements.txt

COPY services/billing/ ./services/billing/
COPY services/common/ ./services/common/

ENV PYTHONPATH=/app
EXPOSE 8003

CMD ["python", "services/billing/main.py"]
