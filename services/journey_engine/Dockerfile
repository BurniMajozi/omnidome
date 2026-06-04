FROM python:3.12-slim

WORKDIR /app

COPY services/common/requirements.txt /tmp/common-requirements.txt
RUN pip install --no-cache-dir -r /tmp/common-requirements.txt

COPY services/common/requirements.txt /common/requirements.txt

COPY services/journey_engine/requirements.txt /tmp/journey-engine-requirements.txt
RUN pip install --no-cache-dir -r /tmp/journey-engine-requirements.txt

COPY services/common /app/services/common
COPY services/journey_engine /app/services/journey_engine

CMD ["uvicorn", "services.journey_engine.main:app", "--host", "0.0.0.0", "--port", "8017"]
