# 🔥 FireWatch AI — Fire & Smoke Detection System

A real-time fire detection system using **YOLOv11** for object detection and **Gemini 2.5 Flash** for scene confirmation, built on a modular microservices architecture behind an **nginx HTTPS proxy**.

---

## Architecture

```
Browser ──HTTPS──▶ nginx (443/80) ──▶ Frontend (3000) ──┬─▶ YOLO Service (8000)
                                                         └─▶ VLM Service  (8019)
```

**Flow:** Camera → YOLO detects fire/smoke (≥35% confidence) → VLM confirms the scene → 🚨 Alarm only when **both agree**

> Only nginx publishes ports to the host. The frontend, YOLO, and VLM services
> are reachable only on the internal Docker network. HTTPS is required because
> browsers only grant camera access (`getUserMedia`) on secure origins.

---

## Project Structure

```
mid-demo-vision-system/
├── frontend/          # FastAPI server + static HTML/CSS/JS dashboard
├── yolo-service/      # YOLOv11 fire & smoke detection API
├── vlm-service/       # Gemini 2.5 Flash scene confirmation API
├── nginx/             # HTTPS reverse proxy (self-signed cert)
├── .env               # Your API keys (never commit this)
├── sample.env         # Template for .env
└── docker-compose.yml
```

---

## Quick Start

```bash
# 1. Set up environment
cp sample.env .env
# Add your Google API key (GOOGLE_API_KEY) to .env

# 2. Place your YOLO model
cp your_model.pt yolo-service/best.pt

# 3. Build and run (nginx generates a self-signed cert at build time)
docker compose up --build

# 4. Open in browser
open https://localhost
```

> ⚠️ The self-signed cert triggers a browser warning — click through to proceed.
> Allow camera access when the browser prompts.

---

## Tech Stack

| Component | Technology |
|-----------|------------|
| Object Detection | YOLOv11 (Ultralytics) |
| Scene Confirmation | Gemini 2.5 Flash (via LangChain) |
| Frontend | HTML / CSS / vanilla JS + FastAPI |
| Reverse Proxy | nginx (HTTPS) |
| Deployment | Docker Compose |

---

## Health Checks

Services are internal-only, so hit them through the running containers:

```bash
docker compose exec yolo-service curl -s http://localhost:8000/health   # YOLO
docker compose exec vlm-service  curl -s http://localhost:8019/health   # VLM
```
