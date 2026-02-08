FROM python:3.11-slim

WORKDIR /app

COPY services/common/requirements.txt ./services/common/requirements.txt
COPY services/admin/requirements.txt ./services/admin/requirements.txt
ENV PIP_DEFAULT_TIMEOUT=300
ENV PIP_RETRIES=5
RUN pip install --no-cache-dir --trusted-host pypi.org --trusted-host pypi.python.org --trusted-host files.pythonhosted.org -r services/admin/requirements.txt

COPY services/admin/ ./services/admin/
COPY services/common/ ./services/common/

ENV PYTHONPATH=/app

EXPOSE 8013

CMD ["python", "services/admin/main.py"]
