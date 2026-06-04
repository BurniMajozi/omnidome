FROM python:3.11-slim

WORKDIR /app

COPY services/common/requirements.txt ./services/common/requirements.txt
COPY services/inventory/requirements.txt ./services/inventory/requirements.txt
ENV PIP_DEFAULT_TIMEOUT=300
ENV PIP_RETRIES=5
RUN pip install --no-cache-dir --trusted-host pypi.org --trusted-host pypi.python.org --trusted-host files.pythonhosted.org -r services/inventory/requirements.txt

COPY services/inventory/ ./services/inventory/
COPY services/common/ ./services/common/

ENV PYTHONPATH=/app
EXPOSE 8010

CMD ["python", "services/inventory/main.py"]
