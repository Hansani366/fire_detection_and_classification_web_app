# 🔥 FireWatch AI — Fire & Smoke Detection System

A real-time fire detection system using **YOLOv11** for object detection and **Gemini 2.5 Flash** for scene analysis, built on a modular microservices architecture.

---

## Architecture

```
Camera Feed (Browser)
       │
       ▼
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   Frontend      │────▶│  YOLO Service    │     │  VLM Service    │
│   (Streamlit)   │     │  Fire & Smoke    │────▶│  Scene Analysis │
│   port 3000     │     │  port 8000       │     │  port 8019      │
└─────────────────┘     └──────────────────┘     └─────────────────┘
```

**Flow:** Camera → YOLO detects fire/smoke (≥50% confidence) → VLM describes the scene → keyword match → 🚨 Alarm

---

## Project Structure

```
mid-demo-vision-system/
├── frontend/          # Streamlit dashboard (live feed + alarm UI)
├── yolo-service/      # YOLOv11 fire & smoke detection API
├── vlm-service/    # Gemini 2.5 Flash scene description API
├── .env               # Your API keys (never commit this)
├── sample.env         # Template for .env
└── docker-compose.yml
```

---

## Quick Start

```bash
# 1. Set up environment
cp sample.env .env
# Add your Google API key to .env

# 2. Place your YOLO model
cp your_model.pt yolo-service/best.pt

# 3. Build and run
docker compose up --build

# 4. Open in browser
open http://localhost:3000
```

> ⚠️ Allow camera access when the browser prompts.

---

## Tech Stack

| Component | Technology |
|-----------|------------|
| Object Detection | YOLOv11 |
| Scene Analysis | Gemini 2.5 Flash |
| Frontend | Streamlit + WebRTC |
| Deployment | Docker Compose |

---

## Health Checks

```bash
curl http://localhost:8000/health   # YOLO
curl http://localhost:8019/health   # VLM
```
