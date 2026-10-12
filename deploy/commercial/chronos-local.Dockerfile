ARG BASE_IMAGE
FROM ${BASE_IMAGE}
USER root
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu 'torch==2.6.0+cpu'
RUN pip install --no-cache-dir 'chronos-forecasting==2.3.2' 'transformers==4.57.1' 'huggingface-hub==0.36.0'
COPY services/forecaster /app/services/forecaster
COPY services/fno_intelligence/metric_catalog.py /app/services/fno_intelligence/metric_catalog.py
RUN mkdir -p /models && chmod 755 /models
ENV FORECAST_MODEL_DIR=/models FORECAST_CHRONOS_MODEL=chronos-bolt-small FORECAST_THREADS=2 OMP_NUM_THREADS=2 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
ENTRYPOINT ["python","-m","services.forecaster.run"]
CMD []
