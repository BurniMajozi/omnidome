# Forecast batch job image. NOT a service: run with
#   docker compose --profile forecast run --rm forecaster
# Build arg WITH_CHRONOS=1 (default) adds CPU-only torch + chronos-forecasting (~1.5-2 GB image);
# WITH_CHRONOS=0 builds the small numpy-only image (~250 MB) that still produces baseline forecasts.
# Model weights are NOT baked in: they live on the `forecast_models` volume (see docs/forecasting.md).
FROM python:3.12-slim AS builder

ARG WITH_CHRONOS=1
WORKDIR /build
COPY services/forecaster/requirements.txt services/forecaster/requirements-chronos.txt ./
RUN pip install --no-cache-dir --default-timeout=100 --retries 5 --prefix=/install -r requirements.txt  && if [ "$WITH_CHRONOS" = "1" ]; then       pip install --no-cache-dir --default-timeout=100 --retries 5 --prefix=/install         --extra-index-url https://download.pytorch.org/whl/cpu torch       && pip install --no-cache-dir --default-timeout=100 --retries 5 --prefix=/install         --extra-index-url https://download.pytorch.org/whl/cpu -r requirements-chronos.txt ;     fi

FROM python:3.12-slim
WORKDIR /app
COPY --from=builder /install /usr/local

# Only what the job imports: the forecaster package, the dependency-free metric catalog, and services/common
# (internal_auth request signing). services/fno_intelligence has no __init__.py, so a single file is importable.
COPY services/forecaster/ ./services/forecaster/
COPY services/fno_intelligence/metric_catalog.py ./services/fno_intelligence/metric_catalog.py
COPY services/common/__init__.py services/common/internal_auth.py ./services/common/

RUN useradd --system --uid 10001 forecaster && mkdir -p /models && chown forecaster /models
USER forecaster

ENV PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    FORECAST_MODEL_DIR=/models \
    FORECAST_CHRONOS_MODEL=chronos-bolt-small \
    FORECAST_THREADS=2 \
    OMP_NUM_THREADS=2 \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1

# One-shot batch job; a bare `docker compose run` forecasts every tenant that has actual metric facts.
ENTRYPOINT ["python", "-m", "services.forecaster.run"]
