FROM omnidome-forecaster:chronos-verified
USER root
RUN pip install --no-cache-dir 'transformers==4.57.1' 'huggingface-hub==0.36.0'
COPY services/forecaster /app/services/forecaster
