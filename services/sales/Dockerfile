FROM python:3.11-slim

WORKDIR /app

COPY services/common/requirements.txt ./services/common/requirements.txt
COPY services/sales/requirements.txt ./services/sales/requirements.txt
ENV PIP_DEFAULT_TIMEOUT=300
ENV PIP_RETRIES=5
RUN pip install --no-cache-dir --trusted-host pypi.org --trusted-host pypi.python.org --trusted-host files.pythonhosted.org -r services/sales/requirements.txt

COPY services/sales/ ./services/sales/
COPY services/common/ ./services/common/

ENV PYTHONPATH=/app

CMD ["python", "services/sales/main.py"]
