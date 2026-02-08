FROM python:3.11-slim

WORKDIR /app

COPY services/common/requirements.txt ./services/common/requirements.txt
COPY services/crm/requirements.txt ./services/crm/requirements.txt
ENV PIP_DEFAULT_TIMEOUT=300
ENV PIP_RETRIES=5
RUN pip install --no-cache-dir --trusted-host pypi.org --trusted-host pypi.python.org --trusted-host files.pythonhosted.org -r services/crm/requirements.txt

COPY services/crm/ ./services/crm/
COPY services/common/ ./services/common/

ENV PYTHONPATH=/app
EXPOSE 8001

CMD ["python", "services/crm/main.py"]
