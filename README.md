# 🔥 Fire Detection Vision System

## 📌 Project Description

This project is a demonstration of an integrated vision system for fire detection.  
It combines:

- **YOLO** for real-time object detection  
- **Vision-Language Model (VLM)** for image captioning and visual reasoning  

The system captures live camera input from a web interface, performs object detection using YOLO, and generates descriptive captions using a VLM model. Both outputs are displayed on the same web page.

---

## 🏗️ System Architecture

The project follows a modular, microservices-based architecture to ensure scalability, flexibility, and easier maintenance.

---

## 📁 Project Structure

- **`frontend/`**  
  Web-based user interface that:
  - Captures live camera feed  
  - Displays YOLO detection results (bounding boxes)  
  - Shows VLM-generated captions  

- **`yolo-service/`**  
  Backend service responsible for object detection.
  - Uses **YOLOv11** for detecting fire-related objects  
  - Returns bounding boxes and confidence scores  

- **`vlm-service/`**  
  Backend service responsible for visual reasoning.
  - Uses **Moondream VLM** for image captioning  
  - Generates descriptive insights about detected scenes  

---

## 🚀 Key Features

- Real-time webcam streaming  
- Fire-related object detection  
- AI-powered scene understanding  
- Modular service-based design  
- Dockerized deployment support  

---

## 🛠️ Technologies Used

- YOLOv11  
- Moondream VLM  
- Docker  
- Web frontend (live camera streaming)  

# 🔥 FireWatch AI — Smoke & Fire Detection System

A real-time computer vision system that uses **YOLOv11** for fire/smoke object detection and **Moondream VLM** for scene description, with a sleek **Streamlit** dashboard.

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                  Streamlit Frontend                  │
│  - Live camera feed (WebRTC)                        │
│  - Bounding box overlay                             │
│  - VLM analysis log                                 │
│  - 🚨 Fire Alarm indicator                          │
└──────────┬──────────────────────┬───────────────────┘
           │  POST /detect        │  POST /describe-image/
           ▼                      ▼
┌──────────────────┐   ┌──────────────────────────────┐
│  YOLO Service    │   │       VLM Service             │
│  (port 8000)     │   │  Moondream via Ollama         │
│  Fire & Smoke    │   │  (port 8019)                  │
│  Detection       │   │  Scene description            │
└──────────────────┘   └──────────────────────────────┘
```

## How It Works

1. Browser captures your laptop camera via WebRTC
2. Every 500ms, a frame is sent to **YOLO** for fire/smoke detection
3. If any detection has **≥50% confidence**, the frame is forwarded to **Moondream VLM**
4. VLM generates a natural-language scene description
5. If the description contains fire/smoke keywords → **🚨 FIRE ALARM ON**

## Quick Start

```bash
# 1. Place your trained YOLO model
cp your_model.pt yolo-service/best.pt

# 2. Build and start all services
docker-compose up --build

# 3. Open browser
open http://localhost:3000
```

> ⚠️ **Allow camera access** when your browser prompts.

## Services

| Service | URL | Description |
|---------|-----|-------------|
| Frontend (Streamlit) | http://localhost:3000 | Web dashboard |
| YOLO API | http://localhost:8000 | Detection endpoint |
| VLM API | http://localhost:8019 | Scene description |

## Health Checks

```bash
curl http://localhost:8000/health   # YOLO
curl http://localhost:8019/health   # VLM / Ollama
```

## Alarm Keywords

The system triggers the alarm if VLM output contains any of:
`fire`, `smoke`, `flame`, `flames`, `burning`, `blaze`, `wildfire`, `inferno`, `ember`, `combustion`

## Notes

- First startup of VLM service will pull the Moondream model (~1.7GB) — takes a few minutes
- For GPU acceleration, uncomment the `deploy` block in `docker-compose.yml`
- The VLM service requires `shm_size: 2gb` for Ollama model loading

# Supportive Repos Used When Writing This Framework

- https://github.com/Hansani366/streamlit_fastapi_webapp
- https://github.com/Hansani366/yolo_vlm_webapp
- https://github.com/Hansani366/vlm_or_mmllm_visual_reasoning

# Time Taken to Build with VLM only mode

| Stage                 | Approx. Time |
|-----------------------|--------------|
| YOLO Dependencies     | ~35 min      |
| Ollama Setup          | ~22 min      |
| Frontend Dependencies | ~5 min       |
| System Packages       | ~2–4 min     |
| **Total (First Build)** | **~40–45 min** |
| Subsequent Builds     | 1–5 min      |