FROM python:3.11-slim

# No system libs needed – no OpenCV, no av, no WebRTC
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY server.py .
COPY static/ static/

# Optional: copy fire_alarm.mp3 if it exists next to the Dockerfile
# COPY fire_alarm.mp3 static/

EXPOSE 3000

HEALTHCHECK --interval=15s --timeout=5s --start-period=5s \
  CMD curl -f http://localhost:3000/ || exit 1

CMD ["uvicorn", "server:app", \
     "--host", "0.0.0.0", \
     "--port", "3000", \
     "--workers", "2"]