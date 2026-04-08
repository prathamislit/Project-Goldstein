FROM python:3.11-slim

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Python deps first (cache layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir flask-login

# Copy source — gcp_key.json and .env mounted at runtime, NOT baked in
COPY config.py gdelt_fetcher.py market_data.py preprocessor.py .
COPY garch_model.py scorer.py .
COPY dashboard.py analyze.py stationarity.py var_model.py .
COPY Run_All_regions.sh run_pipeline.sh .
RUN chmod +x Run_All_regions.sh run_pipeline.sh

# Directories the pipeline writes to
RUN mkdir -p data outputs logs

EXPOSE 8050

CMD ["python3", "dashboard.py"]
