FROM python:3.11-slim

# libgomp1 is XGBoost's OpenMP runtime -- without it `import xgboost` fails on
# slim. curl so `docker compose exec fire-classification-service curl
# .../health` works, the way the ESP32 bridges do.
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Models before code: they change far less often, so the layer stays cached
# across edits to main.py.
COPY model/ model/
COPY *.py ./

EXPOSE 8024

HEALTHCHECK --interval=15s --timeout=5s --start-period=40s \
  CMD curl -f http://localhost:8024/api/classify/health || exit 1

# Must stay single-worker: live sessions hold a per-zone sequence buffer, a VLM
# sample-and-hold and a sensor baseline, all in-process. A second worker would
# serve half the sessions and report the rest as missing -- the same reason
# alert-service, esp32-cam-service and esp32-sensor-service are pinned to one
# worker.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8024", "--workers", "1"]
