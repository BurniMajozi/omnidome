FROM python:3.11-slim

WORKDIR /app

COPY services/common/requirements.txt ./services/common/requirements.txt
COPY services/finance/requirements.txt ./services/finance/requirements.txt
ENV PIP_DEFAULT_TIMEOUT=300
ENV PIP_RETRIES=5
RUN pip install --no-cache-dir --trusted-host pypi.org --trusted-host pypi.python.org --trusted-host files.pythonhosted.org -r services/finance/requirements.txt

COPY services/finance/ ./services/finance/
COPY services/common/ ./services/common/

ENV PYTHONPATH=/app
EXPOSE 8015

CMD ["python", "services/finance/main.py"]
