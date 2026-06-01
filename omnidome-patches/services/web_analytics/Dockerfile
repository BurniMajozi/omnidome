FROM python:3.12-slim

WORKDIR /app

COPY services/common/requirements.txt /tmp/common-requirements.txt
RUN pip install --no-cache-dir -r /tmp/common-requirements.txt

COPY services/web_analytics/requirements.txt /tmp/web-analytics-requirements.txt
RUN pip install --no-cache-dir -r /tmp/web-analytics-requirements.txt

COPY services/common /app/services/common
COPY services/web_analytics /app/services/web_analytics

CMD ["uvicorn", "services.web_analytics.main:app", "--host", "0.0.0.0", "--port", "8016"]
