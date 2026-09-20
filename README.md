# 🔥 FireWatch AI — Fire & Smoke Detection System

A real-time fire detection system using **YOLOv11** for object detection and **Gemini 2.5 Flash** for scene confirmation, built on a modular microservices architecture behind an **nginx HTTPS proxy**. A second YOLO11s model counts **people in the scene**, so a confirmed fire carries a live head-count. Confirmed fires are recorded and pushed to a companion **mobile app** through a dedicated alert service (Firebase Cloud Messaging).

---

## Architecture

```
Browser ──HTTPS──▶ nginx (443/80) ──▶ Frontend (3000) ──┬─▶ Fire Detection YOLO  (8000)
                                                         ├─▶ Human Detection YOLO (8001)
                                                         ├─▶ VLM Service   (8019)
                                                         └─▶ Alert Service (8090) ──FCM──▶ 📱 Mobile App
                                    ├─▶ ESP32 Bridge (8021) ──HTTP──▶ 📷 ESP32-CAM (on your LAN)
                                    └─▶ Sensor Bridge (8022) ◀──HTTP── 🌡️ ESP32 sensor nodes (push)
```

**Flow:** Camera (laptop webcam **or** ESP32-CAM) → one frame is scored by **both** detectors concurrently → fire/smoke (≥35% confidence) goes to the VLM for confirmation → 🚨 Alarm when **both agree** → Alert Service records the incident, **with the people count**, and pushes an FCM notification to the mobile app.

The dashboard shows the two detectors **side by side** over the same frame: fire and smoke boxes on the left, numbered person boxes on the right.

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
├── fire-detection-yolo-service/   # YOLOv11 fire & smoke detection API
├── human-detection-yolo-service/  # YOLO11s (CrowdHuman) person detection + counting
├── vlm-service/       # Gemini 2.5 Flash scene confirmation API
├── alert-service/     # Mobile alert backend — FCM push + zones/incidents/history (SQLite)
├── esp32-service/     # ESP32-CAM bridge — relays the board's MJPEG stream same-origin
├── sensor-service/    # ESP32 sensor bridge — receives MQ-2 / MQ-7 / flame / DHT22 telemetry
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

# 2. Both YOLO models are already committed as
#      fire-detection-yolo-service/best.pt
#      human-detection-yolo-service/best.pt   (crowdhuman_yolo11s_best.pt)
#    Replace either with your own .pt to swap models.

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
| Fire & Smoke Detection | YOLOv11 (Ultralytics) |
| Human Detection & Counting | YOLO11s trained on CrowdHuman |
| Scene Confirmation | Gemini 2.5 Flash (via LangChain) |
| Frontend | HTML / CSS / vanilla JS + FastAPI |
| Alert Backend | FastAPI + SQLite |
| Mobile Push | Firebase Cloud Messaging (FCM) |
| Reverse Proxy | nginx (HTTPS) |
| Deployment | Docker Compose |

---

## Human detection & occupancy

A second YOLO model (`human-detection-yolo-service`) counts people in the same frame the fire
detector scores. It is **YOLO11s trained on CrowdHuman**, single class `person`, 100 epochs at
640px — chosen for dense, heavily occluded scenes:

| Metric | Value |
|---|---|
| Precision | 0.870 |
| Recall | 0.739 |
| mAP@50 | 0.835 |
| mAP@50–95 | 0.529 |

**One upload, two models.** The browser posts a frame to `/api/detect` once; the frontend proxy
fans it out to both detectors concurrently and returns both results together:

```json
{ "fire":  { "detections": [...] },
  "human": { "detections": [...], "count": 7 },
  "timings": { "fireMs": 118, "humanMs": 143 } }
```

Fanning out server-side matters for more than bandwidth: two separate browser calls would capture
two *different* frames up to 500 ms apart, so the two overlays would describe different moments.
The round trip costs `max(fire, human)` rather than their sum.

**Fire is required; human is optional.** A human-service failure degrades to a null count and
nothing else — the alarm path behaves exactly as it did before this existed. A null count is
deliberately distinct from zero: a detector that is down must never read as an empty room.

**The displayed count is a rolling median** of the last 5 frames (~2.5 s). Raw per-frame counts
genuinely oscillate by a person or two on occluded crowds; a median rejects those spikes without
the lag a moving average would add. Both numbers are on screen — the median as the headline, the
raw frame count beneath it.

| Env var | Default | Meaning |
|---------|---------|---------|
| `HUMAN_MIN_CONF` | `0.40` | Person confidence floor. Higher than the fire detector's 0.35 — a false person inflates an evacuation head-count, whereas a false smoke box only asks the VLM for a second opinion. |
| `HUMAN_IOU` | `0.7` | NMS IoU. CrowdHuman labels genuinely overlapping people, so this stays permissive. |
| `HUMAN_IMGSZ` | `640` | Inference size; matches training. |

### Occupancy → the evacuation muster

A confirmed fire now carries the head-count to `alert-service`, which uses it to replace the
muster figure the mobile app previously received as a hardcoded constant.

**Occupancy is not muster, and the two move in opposite directions.** The camera counts people
*still in the zone*; `muster.present` means people *accounted for* away from it. So:

```
muster.total   = peak occupancy seen since the incident opened   (who was there)
muster.present = peak − current occupancy                        (who has got out)
```

As the zone empties, `present` rises to meet `total`. The payload carries `"source": "vision"`
when the number is measured and `"estimated"` when it fell back to the old constant — an incident
raised while the human detector was down, or one predating this feature.

> **This sees one camera's field of view, not the whole zone.** Someone never in frame is never in
> the total, and someone who walks out of shot counts as evacuated. It is a far better number than
> the constant it replaces, but it is an estimate.

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

**ESP32 bridge configuration** (`esp32-service`, all optional except the first):

| Env var | Default | Meaning |
|---------|---------|---------|
| `ESP32_CAM_URL` | _(unset)_ | Default board address, e.g. `http://192.168.1.50`. The dashboard can override it. |
| `ESP32_CONNECT_TIMEOUT` | `3` | Seconds to wait for the board to accept a connection |
| `ESP32_STREAM_READ_TIMEOUT` | `10` | Seconds without stream data before dropping it (`0` = wait forever) |
| `ESP32_STILL_TIMEOUT` | `5` | Seconds for a single `/still` fetch |
| `ESP32_PROBE_TIMEOUT` | `2` | Seconds for a health probe — must stay below the dashboard's poll interval |
| `ESP32_STALE_AFTER_MS` | `3000` | No relayed frames for this long → the feed is reported as frozen |

---

## ESP32 sensor nodes

The **Sensor Network** card on the dashboard shows live readings from one or more
ESP32-WROOM-32 nodes carrying an **MQ-2** (gas/smoke), **MQ-7** (carbon monoxide),
**IR flame** module and **DHT22** (temperature/humidity). The sketch lives in the
companion `esp_32_sensor_network_code` repo and ships in mock mode, so a bare board
with nothing wired to it still populates the dashboard.

**The nodes push; nothing polls them.** The camera bridge reaches *out* to the
ESP32-CAM because an MJPEG stream only exists while someone pulls it. Sensor
readings are the opposite — they exist regardless, the boards are on DHCP so their
addresses move, and a network of nodes would mean a list of addresses to maintain
here. Pushing inverts all of that: each node only needs this machine's address, and
adding a node costs no configuration at all.

`sensor-service` publishes **`8022`** directly to the host so the boards can POST
over plain HTTP, for the same reason `alert-service` publishes `8090` — an ESP32
has no business fighting a self-signed certificate. The browser reaches the same
service through nginx over HTTPS, same-origin.

| Method & Path | Purpose |
|---------------|---------|
| `POST /api/sensors/ingest` | A node submits one sweep of its sensors |
| `GET  /api/sensors/latest` | Latest sweep per node + freshness (the dashboard polls this) |
| `GET  /api/sensors/history` | `?deviceId=&limit=` — recent samples for one node |
| `GET  /health` | Liveness, node count, whether a key is required |

**Configuration** (set in `docker-compose.yml`):

| Env var | Default | Meaning |
|---------|---------|---------|
| `SENSOR_STALE_AFTER_S` | `15` | No sample for this long → the node is reported stale |
| `SENSOR_HISTORY_MAX` | `720` | Samples kept per node (≈36 min at the sketch's 3s cadence) |
| `SENSOR_INGEST_KEY` | _(empty)_ | Shared secret expected as `X-Device-Key`; empty accepts any LAN device |
| `SENSOR_MAX_NODES` | `32` | Cap on distinct nodes, so an open port cannot grow memory without limit |
| `SENSOR_MQ2_WARN` / `_DANGER` | `400` / `800` | Smoke thresholds, ppm |
| `SENSOR_MQ7_WARN` / `_DANGER` | `35` / `100` | CO thresholds, ppm (35 = OSHA 8-hour ceiling) |
| `SENSOR_TEMP_WARN` / `_DANGER` | `45` / `60` | Temperature thresholds, °C |

Readings are graded (`normal` / `warn` / `danger`) **in the service, not the
browser**, so the alerting path can reuse the same verdicts later without the
thresholds living in two places. A stale node keeps its last numbers on screen but
dimmed, and its overall level is withheld — otherwise a node that died mid-fire
would leave the dashboard green.

> **Read-only for now.** Sensor readings are displayed but do not feed the alarm,
> which still requires YOLO and the VLM to agree.

```bash
# Simulate a node from your laptop — no board required
python3 ../esp_32_sensor_network_code/tools/mock_sender.py

# What the dashboard sees
curl -sk https://localhost/api/sensors/latest | python3 -m json.tool

# Can a board on the LAN reach the ingest port? (run from another machine)
curl -s -o /dev/null -w '%{http_code}\n' http://<this-laptop-ip>:8022/health
```

> If the board logs a connection failure but the simulator works, the service is
> fine — suspect the macOS firewall on 8022, or the board being on a different
> network. The WROOM-32 is **2.4 GHz only**.

---

## Health Checks

The alert service is published on the host, so hit it directly. YOLO and VLM are
internal-only, so reach them through their containers:

```bash
curl -s http://localhost:8090/health                                      # Alert service
curl -s http://localhost:8022/health                                      # Sensor bridge
docker compose exec human-detection-yolo-service curl -s http://localhost:8001/health
docker compose exec esp32-service curl -s http://localhost:8021/health    # ESP32 bridge
```

> `fire-detection-yolo-service` and `vlm-service` have **no `curl`** in their images, so
> `docker compose exec … curl` fails on those two. Use Python, which is always present:

```bash
docker compose exec fire-detection-yolo-service \
  python -c "import urllib.request;print(urllib.request.urlopen('http://localhost:8000/health').read().decode())"
docker compose exec vlm-service \
  python -c "import urllib.request;print(urllib.request.urlopen('http://localhost:8019/health').read().decode())"
```

Score a still image through both detectors at once:

```bash
curl -sk -F file=@frame.jpg https://localhost/api/detect | python3 -m json.tool
```

---

## ESP32-CAM as a camera source

The dashboard can run detection on an **ESP32-CAM** instead of the laptop webcam. Flash the
board with the `esp32cam_stream_v2_final_working_code_via_wifi.ino` sketch (set your 2.4 GHz
SSID and password at the top), then pick **ESP32-CAM** in the dashboard's **Source** switch.
Everything downstream — YOLO, VLM confirmation, the alarm, the phone push — is identical.

Find the board's address on the 115200 serial monitor at boot:

```
>>> OPEN THIS:  http://192.168.1.50
```

Put that in `.env` as `ESP32_CAM_URL`, or type it into the address field next to the Source
switch (it is remembered in the browser, which is handy while the board is on DHCP). An
empty field means "use `ESP32_CAM_URL`".

```bash
# Is the board reachable from inside the bridge container?
docker compose exec esp32-service curl -s -o /dev/null -w '%{http_code}\n' http://192.168.1.50/still

# Bridge's view of the board (also what the dashboard polls)
curl -sk https://localhost/api/esp32/health
```

> **`ESP32_CAM_URL` is read at container start.** After editing `.env`, run
> `docker compose up -d --force-recreate esp32-service` — a plain `restart` keeps the old value.

**Why a bridge service rather than pointing the browser at the board?** The dashboard is
HTTPS-only, so a plain-HTTP `<img>` from the board is blocked as mixed content — and even if
it loaded, it would taint the capture canvas and make frame grabbing throw. The bridge
relays the stream same-origin, which solves both.

**One viewer at a time.** The board runs a single-threaded HTTP server whose stream handler
never returns, so while it is streaming it cannot answer anything else. Keep one dashboard
tab on ESP32 mode; opening a second drops the first. The bridge reports liveness from frames
it has actually relayed rather than by polling the board, and if the picture freezes the
dashboard stops sending frames to YOLO so the alarm clears instead of latching on a stale
image.
