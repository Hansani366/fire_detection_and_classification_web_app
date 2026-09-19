FROM python:3.11-slim

# curl so `docker compose exec sensor-service curl .../health` works
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

EXPOSE 8022

HEALTHCHECK --interval=15s --timeout=5s --start-period=5s \
  CMD curl -f http://localhost:8022/health || exit 1

# Must stay single-worker: NODES (latest reading + history ring buffer per
# node) is an in-process dict, so a second worker would serve half the nodes
# and report the rest as missing. Do not add --workers > 1.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8022", "--workers", "1"]
