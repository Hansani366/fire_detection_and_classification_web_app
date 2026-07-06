# 🔥 FireWatch AI — Fire & Smoke Detection System

A real-time fire detection system using **YOLOv11** for object detection and **Gemini 2.5 Flash** for scene confirmation, built on a modular microservices architecture behind an **nginx HTTPS proxy**. Confirmed fires are recorded and pushed to a companion **mobile app** through a dedicated alert service (Firebase Cloud Messaging).

---

## Architecture

```
Browser ──HTTPS──▶ nginx (443/80) ──▶ Frontend (3000) ──┬─▶ YOLO Service  (8000)
                                                         ├─▶ VLM Service   (8019)
                                                         └─▶ Alert Service (8090) ──FCM──▶ 📱 Mobile App
```

**Flow:** Camera → YOLO detects fire/smoke (≥35% confidence) → VLM confirms the scene → 🚨 Alarm when **both agree** → Alert Service records the incident and pushes an FCM notification to the mobile app.

> nginx publishes 80/443; the frontend, YOLO, and VLM services stay on the internal
> Docker network. The **alert service** additionally publishes `8090` to the host so the
> mobile app can reach it over plain HTTP on the LAN — sidestepping the self-signed-cert
> dance a native client would hit through nginx. HTTPS is still required for the browser
> dashboard because cameras (`getUserMedia`) are only granted on secure origins.

---

## Project Structure

```
mid-demo-vision-system/
├── frontend/          # FastAPI server + static HTML/CSS/JS dashboard
├── yolo-service/      # YOLOv11 fire & smoke detection API
├── vlm-service/       # Gemini 2.5 Flash scene confirmation API
├── alert-service/     # Mobile alert backend — FCM push + zones/incidents/history (SQLite)
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

# 3. (optional) Enable mobile push notifications
#    Drop a Firebase service-account key at:
#      alert-service/secrets/firebase-sa.json
#    Without it the alert service still runs — push is simply skipped.

# 4. Build and run (nginx generates a self-signed cert at build time)
docker compose up --build

# 5. Open in browser
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
| Alert Backend | FastAPI + SQLite |
| Mobile Push | Firebase Cloud Messaging (FCM) |
| Reverse Proxy | nginx (HTTPS) |
| Deployment | Docker Compose |

---

## Mobile Alert Service

The `alert-service` is the backend for the companion mobile app. When YOLO and the VLM
agree on a fire, the dashboard posts the confirmed event to it; the service records the
incident, tracks per-zone state and history in SQLite, and pushes a Firebase Cloud
Messaging (FCM) notification to registered devices. A background watchdog auto-clears an
incident once fire events stop arriving.

Unlike the other services it publishes **`8090`** directly to the host, so a phone on the
same LAN can reach it over plain HTTP without the self-signed-cert dance.

| Method & Path | Purpose |
|---------------|---------|
| `GET  /health` | Liveness + whether FCM is configured |
| `POST /api/devices` | Register a device's FCM token |
| `GET  /api/state` | Current zones + the active incident |
| `GET  /api/incidents/{id}` | Fetch a single incident |
| `POST /api/incidents/{id}/ack` | Acknowledge / bump the muster count |
| `GET  /api/history` | Resolved incidents |
| `POST /api/events/fire` | Report a confirmed-fire event (from the dashboard) |
| `POST /api/events/clear` | Clear a zone |
| `POST /api/test-alert` | Trigger a synthetic alert for testing |

**Configuration** (set in `docker-compose.yml`):

| Env var | Default | Meaning |
|---------|---------|---------|
| `FIREBASE_CREDENTIALS` | `/secrets/firebase-sa.json` | Service-account key; enables push |
| `DB_PATH` | `/data/alert.db` | SQLite location (persisted in a Docker volume) |
| `SITE_NAME` | `Unit 7` | Site label shown in the app |
| `COOLDOWN_SECONDS` | `120` | Min seconds between separate incidents in one zone |
| `CLEAR_AFTER_SECONDS` | `30` | No fire event for this long → auto-clear the incident |

> Push is optional: without `alert-service/secrets/firebase-sa.json` the service runs
> normally and simply skips notifications.

---

## Health Checks

The alert service is published on the host, so hit it directly. YOLO and VLM are
internal-only, so reach them through their containers:

```bash
curl -s http://localhost:8090/health                                     # Alert service
docker compose exec yolo-service curl -s http://localhost:8000/health    # YOLO
docker compose exec vlm-service  curl -s http://localhost:8019/health    # VLM
```
