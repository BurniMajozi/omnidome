FROM python:3.12-slim

WORKDIR /app

COPY services/common/requirements.txt /tmp/common-requirements.txt
RUN pip install --no-cache-dir -r /tmp/common-requirements.txt

COPY services/lifecycle/requirements.txt /tmp/lifecycle-requirements.txt
RUN pip install --no-cache-dir -r /tmp/lifecycle-requirements.txt

COPY services/common /app/services/common
COPY services/lifecycle /app/services/lifecycle

CMD ["uvicorn", "services.lifecycle.main:app", "--host", "0.0.0.0", "--port", "8018"]
