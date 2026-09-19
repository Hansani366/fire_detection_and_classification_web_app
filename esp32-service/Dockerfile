FROM python:3.11-slim

# curl so `docker compose exec esp32-service curl .../health` works
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

EXPOSE 8021

HEALTHCHECK --interval=15s --timeout=5s --start-period=5s \
  CMD curl -f http://localhost:8021/health || exit 1

# Must stay single-worker: the stream registry and the relayed-byte bookkeeping
# that /api/esp32/health reads are in-process singletons (see main.py).
# Do not add --workers > 1.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8021", "--workers", "1"]
