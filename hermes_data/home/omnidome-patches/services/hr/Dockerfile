FROM python:3.11-slim

WORKDIR /app

COPY services/common/requirements.txt ./services/common/requirements.txt
COPY services/hr/requirements.txt ./services/hr/requirements.txt
ENV PIP_DEFAULT_TIMEOUT=300
ENV PIP_RETRIES=5
RUN pip install --no-cache-dir --trusted-host pypi.org --trusted-host pypi.python.org --trusted-host files.pythonhosted.org -r services/hr/requirements.txt

COPY services/hr/ ./services/hr/
COPY services/common/ ./services/common/

ENV PYTHONPATH=/app
EXPOSE 8009

CMD ["python", "services/hr/main.py"]
