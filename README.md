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
                                    ├─▶ Sensor Bridge (8022) ◀──HTTP── 🌡️ ESP32 sensor nodes (push)
                                    ├─▶ Fire Classification (8024) ─┬─▶ Fire Detection YOLO (8000)
                                    │     owns both trained models   ├─▶ VLM Service (8019)
                                    │                                └─▶ Sensor Bridge (8022)
                                    └─▶ Ablation Service (8023) ─▶ Fire Classification (8024)
```

The dashboard has **two pages**, switched from the nav bar in the top bar:

| Page | What it is |
|---|---|
| `/` | **Live Monitoring** — the running system: camera, detectors, alarm, sensors |
| `/ablation` | **Ablation Tests** — the six sensing combinations, scored for the research paper |
| `/reports` | **Reports** — what happened in each past incident, and when the system knew it |

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
├── esp32-cam-service/     # ESP32-CAM bridge — relays the board's MJPEG stream same-origin
├── esp32-sensor-service/    # ESP32 sensor bridge — receives MQ-2 / MQ-7 / flame / DHT22 telemetry
├── fire-classification-service/  # Owns sensor_model + fusion_model — what is burning
├── ablation-service/  # Six-combination ablation testing (asks the classifier)
├── ablation-data/     # Your own recorded experiments (git-ignored; see its README)
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

# 5. Upgrading from before the service rename? Remove the old containers first.
#    esp32-service became esp32-cam-service and sensor-service became
#    esp32-sensor-service. The old containers survive a plain `down`, and the
#    old sensor bridge still holds host port 8022 — so the renamed one cannot
#    start until they are gone.
docker compose down --remove-orphans

# 6. Open in browser
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

**ESP32 bridge configuration** (`esp32-cam-service`, all optional except the first):

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

`esp32-sensor-service` publishes **`8022`** directly to the host so the boards can POST
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

## Ablation testing

Open **`https://localhost/ablation`**, or use the nav bar in the top left.

The page answers one question: **what does each sensing modality actually contribute?** It scores six
combinations against known ground truth and produces the table, the confusion matrices and the export
a paper needs.

| # | Combination | Decided by |
|---|---|---|
| 1 | sensors only | `sensor_model.joblib` |
| 2 | YOLO only | documented rule |
| 3 | VLM only | documented rule |
| 4 | sensors + YOLO | documented rule |
| 5 | VLM + YOLO | documented rule — the one the dashboard deploys today |
| 6 | sensors + YOLO + VLM | `fusion_model.joblib` |

Every rule is printed on the page, **rendered from the same frozen constants the service executes**,
so what is printed and what ran cannot disagree. None of the thresholds is hand-picked: each comes
from the model's `manifest.json` or from the dataset generator.

### The two models

They live in **`fire-classification-service`** and nowhere else — the dashboard and this page both ask
it for a verdict, so there is one copy of the weights and no way for the live system and the research
page to disagree. Vendored from the sibling repo `fire_classification_model`; see
`fire-classification-service/model/PROVENANCE.md` for the exact source and checksums.

**`sensor_model.joblib` is required, not optional.** The fusion model reads no raw sensor values at
all — features 92–95 of its 96 are the sensor model's four class probabilities:

```
sensors ─▶ sensor_model (XGBoost, 53 features) ─▶ 4 probabilities ─┐
                                                                    ├─▶ fusion_model ─▶ verdict
vision  ─▶ 17 raw channels + 72 temporal features ─────────────────┘   (MLP, 96 features)
```

`fire-classification-service` pins `scikit-learn==1.9.1`, `xgboost==2.0.3` and `pandas==3.0.6` — the
exact versions that wrote the pickles — and **refuses to start** if the installed versions differ.
`ablation-service` carries none of those libraries: it holds the rules and the metrics, and asks for
the two trained arms over HTTP.

### Batch tab

Two kinds of dataset:

- **Replay** — the 96 held-out CFAST test experiments, plus a 90-experiment out-of-distribution split
  burning three fuels the model never saw. Runs in about a second.
- **Your own recordings** — real frames through the real detectors. Drop them in `ablation-data/`;
  the format is documented in [ablation-data/README.md](ablation-data/README.md).

**Replayed results carry a loud SYNTHETIC banner and a column in every export.** Both models were
trained on simulation, never on recorded fire, so a replayed accuracy figure describes the generator.
Your own recordings are the result that actually matters.

**Ground truth has two definitions, and the choice moves the numbers.** In the training data every row
of a fire run carries that run's fuel label, including the 1,892 test rows where nothing is burning
yet — so the model was *trained* to answer "fire" from the first second.

| Mode | Meaning |
|---|---|
| **Strict** (default) | Pre-ignition windows are negatives. What a deployed detector should be judged on. |
| **As trained** | The whole fire run is positive. Matches the dataset labels and the published `metrics.csv`. |

### Live tab

All six combinations scored side by side on the live camera and sensor nodes, at the models' 1 Hz rate.
It shows **agreement, never accuracy** — nothing on a live feed carries a ground-truth label.

The first 30 seconds measure the clean-air sensor baseline, and **no windows are scored until it is
fixed**: the models need a delta above clean air, and a delta against an unknown baseline would poison
every running maximum for the rest of the session. So **record at least 30 seconds of quiet before
ignition**, in live sessions and in your own recordings alike.

### Things the page will tell you, and why they matter

- **Almost every false alarm is a warm-up artifact.** The models' longest features are a 15-window
  rolling statistic and a 25-window persistence mean. Until those fill, they are reading a history
  that does not exist. Measured on the test split, combination 6's false-alarm rate in a quiet room is
  0.74 between seconds 5 and 30 and **exactly 0.00 after second 60**. The practical fix is to ignore
  the first minute of a session, not to retrain.
- **The fusion model's gain over sensors alone is one event in 96.** Every comparison against
  combination 6 therefore carries a paired McNemar test and the absolute event count, not just a
  percentage.
- **Combination 6 contains combination 1.** Four of its features are the sensor model's output, so
  "fusion beats sensors" is partly tautological. The informative comparisons are 6 against 4 and 6
  against 2.
- **Confidence does not detect unfamiliar fuels** (AUROC 0.486 — chance). The out-of-distribution
  split shows what that costs.

```bash
# Run all six combinations over the held-out test split and get the CSV
RID=$(curl -sk -X POST https://localhost/api/ablation/runs \
        -H 'content-type: application/json' \
        -d '{"dataset_id":"test_split"}' | python3 -c 'import sys,json;print(json.load(sys.stdin)["run_id"])')
curl -sk "https://localhost/api/ablation/runs/$RID/export.csv?level=event"

# The JSON export additionally carries model checksums, library versions and the
# full frozen config — this is the artifact to cite.
curl -sk "https://localhost/api/ablation/runs/$RID/export.json"
```

---

## Escalation — how the live system responds

The dashboard no longer has a single alarm rule. The response now matches how strong the evidence is:

| Tier | Trigger | Siren | What happens |
|---|---|---|---|
| **1a Warning** | sensors grade `warn`, sustained ~6 s | **no** | Gemini writes a warning **from the readings as text**, sent on a separate notification channel |
| **1b Danger** | sensors grade `danger`, sustained | **yes** | alarms with nothing visible — a camera cannot see carbon monoxide |
| **2 Fire** | YOLO + VLM agree | **yes** | opens the incident, reports what is visible |
| **3 Classified** | sensors catch up | already on | **upgrades the same incident** with the fuel type and what to do about it |

Four things about it are deliberate:

- **A gas warning never sounds the fire alarm.** Gas sensors react to cooking, aerosols, solvents and
  exhaust. A warning that sounded the alarm would teach people to ignore the alarm.
- **Tier 3 upgrades tier 2, it does not replace it.** Gas reaches the sensor 14–22 s after a camera
  sees the flame, so "all three agree" is nearly always the same fire arriving twice. One incident,
  one muster, one timeline.
- **A VLM outage no longer disables the alarm.** If Gemini is unreachable but YOLO and the sensors
  both say fire, it alarms anyway and records that the VLM was unavailable.
- **The fuel verdict says why when it cannot answer.** "Sensors still warming up" is information;
  a blank field looks like a bug.

The ladder lives in [frontend/static/js/escalation.js](frontend/static/js/escalation.js); the incident
side is `alert-service`, which escalates a `warning` incident to `fire` in place.

```bash
# Tier 1a: readings in, plain-language warning out (no image)
curl -sk -X POST https://localhost/api/warn -H 'content-type: application/json' \
  -d '{"readings":"MQ-2 620 ppm (baseline 300), CO 45 ppm","zone":"fabric-store","level":"warn"}'

# What is burning, on a live feed
SID=$(curl -sk -X POST https://localhost/api/classify/sessions \
        -H 'content-type: application/json' -d '{"zoneId":"fabric-store"}' \
      | python3 -c 'import sys,json;print(json.load(sys.stdin)["session_id"])')
curl -sk -X POST "https://localhost/api/classify/sessions/$SID/tick" -F file=@frame.jpg
```

---

## What to fight it with

Once the fusion model names the fuel, the system says what to use — and, more importantly, **what not
to use**. The wrong extinguisher does not simply fail:

| Fuel | Class | Never use | Why |
|---|---|---|---|
| Gas | C | — | **Isolate the supply first.** Putting the flame out while gas still flows lets it fill the room unburned. |
| Liquid | B | **Water** | Burning liquid floats on water and travels with it. |
| Solids | A | CO2 | Knocks the flames down without cooling, so it reignites. |

Two limits are printed with every verdict, because the model has three fuel classes and real fires
have more:

- **Cooking oil is class F, not B.** It needs wet chemical. Foam or water on a deep-fat fire causes a
  violent boil-over, and the model will call a chip-pan fire `liquid_fuel`.
- **Live electrical equipment** changes the answer whatever is burning — CO2 or dry powder only. The
  classifier cannot see whether anything is energised.

The table lives in [alert-service/extinguishers.py](alert-service/extinguishers.py) and is served at
`GET /api/extinguishers`. The dashboard, the phone push and the incident record all read it from
there, so the three cannot drift into giving different answers about the same fire.

---

## Incident reports

`https://localhost/reports` — one record per past incident, with a **Print / Save as PDF** button.
No PDF library: the page simply prints well.

The interesting part is the timeline and the gaps between its stamps:

```
Warning → fire      4s     how much notice the sensors gave
Fire → fuel known   5s     how long the sensors took to catch up
```

Those two numbers are the escalation design, measured. Reporting a single timestamp would imply the
system knew everything at once, which it did not — gas reaches a sensor 14–22 s after a camera sees
the flame.

An incident that escalated keeps both halves of its story: when the gas warning opened, and when the
flame was seen. The fuel type is kept with the record too, so an investigation can still answer *"what
was burning?"* long after the fire is out.

```bash
curl -sk https://localhost/api/incidents/<id>/report | python3 -m json.tool
```

---

## Health Checks

The alert service is published on the host, so hit it directly. YOLO and VLM are
internal-only, so reach them through their containers:

```bash
curl -s http://localhost:8090/health                                      # Alert service
curl -s http://localhost:8022/health                                      # Sensor bridge
docker compose exec human-detection-yolo-service curl -s http://localhost:8001/health
docker compose exec esp32-cam-service curl -s http://localhost:8021/health    # ESP32 bridge
curl -sk https://localhost/api/ablation/health                            # Ablation service
curl -sk https://localhost/api/classify/health                            # Fire classification
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
docker compose exec esp32-cam-service curl -s -o /dev/null -w '%{http_code}\n' http://192.168.1.50/still

# Bridge's view of the board (also what the dashboard polls)
curl -sk https://localhost/api/esp32/health
```

> **`ESP32_CAM_URL` is read at container start.** After editing `.env`, run
> `docker compose up -d --force-recreate esp32-cam-service` — a plain `restart` keeps the old value.

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
