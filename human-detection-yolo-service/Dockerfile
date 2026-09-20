FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    libglib2.0-0 libsm6 libxext6 libxrender-dev libgomp1 \
    libgl1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .

# Install CPU-only PyTorch FIRST to prevent ultralytics from pulling CUDA (~3GB of NVIDIA packages)
RUN pip install --no-cache-dir \
    torch torchvision \
    --index-url https://download.pytorch.org/whl/cpu

RUN pip install --no-cache-dir -r requirements.txt

# crowdhuman_yolo11s_best.pt from the human_detection_yolo_model repo,
# copied in as best.pt to match the fire detector's layout.
COPY best.pt .
COPY main.py .

EXPOSE 8001

HEALTHCHECK --interval=15s --timeout=5s --start-period=60s \
  CMD curl -f http://localhost:8001/health || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
