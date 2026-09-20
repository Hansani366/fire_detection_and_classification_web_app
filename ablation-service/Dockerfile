FROM python:3.11-slim

# libgomp1 is XGBoost's OpenMP runtime -- without it `import xgboost` fails on
# slim. curl so `docker compose exec ablation-service curl .../health` works,
# the way sensor-service and esp32-service do.
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
COPY data/ data/
COPY *.py ./

EXPOSE 8023

HEALTHCHECK --interval=15s --timeout=5s --start-period=40s \
  CMD curl -f http://localhost:8023/api/ablation/health || exit 1

# Must stay single-worker: live sessions hold a per-experiment sequence buffer
# and batch runs hold a job registry, both in-process. A second worker would
# serve half the sessions and report the rest as missing -- the same reason
# alert-service, esp32-service and sensor-service are pinned to one worker.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8023", "--workers", "1"]
