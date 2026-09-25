# FireWatch — fire detection and classification web system

## 1. Overview

FireWatch is a research prototype that detects indoor fires early, verifies them
before raising an alarm, and then delivers a complete response. It runs as ten
services behind a web dashboard, with a companion Android application for
occupants.

**The problem.** A review of 104 published fire detection studies found that only
12.5 per cent consider evacuation or the people inside the building, and only one
produces a written report for the person who must act. This system is built to
continue past the point where that work stops.

**What makes it different:**

- **Three independent sources.** Sensors, object detection and a vision language
  model each produce a judgement, and rules combine them. Nothing is averaged, so
  every source stays readable and any one of them can be switched off.
- **Four states, so the alarm stays trusted.** Each state has its own trigger
  and its own response, as Table 1 sets out.
- **Verification that fails safe.** The vision language model can confirm or
  reject a detection but never create one. If it cannot be reached, an existing
  alarm is kept and the incident records that verification was unavailable.
- **Claims are checked before release.** Every statement in the situation report
  is tested against the logged evidence. Contradicted statements are withheld and
  unverifiable ones are marked, so hallucination control runs live rather than
  afterwards.
- **A response, not just an alert.** The system classifies the fuel, recommends
  an extinguishing agent, counts the people present, and builds an escape route
  that avoids the fire. It returns a refuge instruction when no exit is reachable.
- **Measurement is built in.** An ablation service runs the six combinations in
  Table 2 against the same recorded data, so the contribution of each component
  can be isolated. Route validity, hazard avoidance and notification delivery
  time are computed from stored records rather than asserted.

**The four states.** A zone is always in exactly one of the states in Table 1.

**Table 1.** The four system states, their entry conditions and the response to each.

| State | What triggers it | What the system does |
|---|---|---|
| **Clear** | No sensor channel above its warning level, and nothing confirmed on camera. | Monitoring only. No alert is sent. |
| **Gas warning** | A sensor channel reads "warn" for three polls in a row, with nothing visible on camera. | A short written warning is sent on a separate quiet channel. No siren, and the zone status stays clear. |
| **Gas danger** | A sensor channel reads "danger", still with nothing visible. | A full alarm. An incident opens and the phone is notified. The readings form the report, because there is no image to describe. |
| **Fire confirmed** | The fire model finds a box above 0.35 and the vision language model agrees. A box plus raised sensor readings also confirms it when that model cannot be reached. | A full alarm. The head count is recorded, and the report, the escape route and the fire fighting guidance are delivered. |

Two rules hold this together:

- **Gas alone never sounds the siren**, because gas sensors also react to
  cooking, sprays, solvents and vehicle exhaust. A warning that cried wolf would
  teach people to ignore the alarm.
- **Dangerous carbon monoxide alarms anyway**, even with nothing visible, because
  a camera can never see it and the level that harms people is reached before
  anything is.

Once the fuel is identified, the open incident is upgraded in place. A second
incident is never created, because the gas and the flame are the same fire
arriving twice.

**The six combinations** the ablation service evaluates are listed in Table 2.

**Table 2.** The six source combinations compared by the ablation study.

| | Combination | What it tests |
|---|---|---|
| 1 | Sensors only | What the gas, temperature and flame channels achieve alone. |
| 2 | Detector only | What the fire and smoke model achieves alone. |
| 3 | Vision language model only | What scene understanding achieves alone. |
| 4 | Sensors and detector | Decision level fusion, with no scene verification. |
| 5 | Detector and vision language model | Camera evidence only, but verified. |
| 6 | Sensors, detector and vision language model | The full system. |

Because every combination sees the same recorded frames and readings, the
comparison between them is paired, and the contribution of each source can be
measured rather than assumed.

**Research purpose.** The study addresses two problems that the literature reports
but rarely solves together:

- **Late detection.** A ceiling detector only reacts once smoke reaches it, which
  takes time in a large or ventilated space.
- **False alarms.** A camera alone cannot tell a welding arc from a flame, and a
  system that cries wolf gets muted.

The system is a research prototype. It is not certified against any fire safety
standard and is not offered as a replacement for a code compliant alarm system.

## 2. Services

Ten services run together under Docker Compose, as listed in Table 3.

**Table 3.** The ten services, the port each one listens on, and its responsibility.

| Service | Port | What it does |
|---|---|---|
| `nginx` | 80, 443 | Handles HTTPS and routes each request to the right service. |
| `frontend` | 3000 | Serves the dashboard and sends each frame to both detectors at once. |
| `fire-detection-yolo-service` | 8000 | Finds fire and smoke in a frame. |
| `human-detection-yolo-service` | 8001 | Counts the people in a frame for the head count. |
| `vlm-service` | 8019 | Asks Gemini to verify a detection, describe the scene, or write a gas warning. |
| `esp32-cam-service` | 8021 | Passes the ESP32 camera stream to the dashboard. |
| `esp32-sensor-service` | 8022 | Receives sensor readings and grades them normal, warn or danger. |
| `fire-classification-service` | 8024 | Decides what is burning. It holds both trained models and is the only service that loads them. |
| `ablation-service` | 8023 | Compares six combinations of the sources for the research results. |
| `alert-service` | 8090 | Stores incidents, builds escape routes and sends notifications. |

Two services publish their port to the host. The sensor bridge does so because
the nodes send readings over plain HTTP, and the alert service does so because
the mobile application must reach it on the local network.

The dashboard serves three pages: live monitoring at `/`, ablation results at
`/ablation`, and incident reports at `/reports`.

**The two fuel classification models**, both held by
`fire-classification-service`:

- **The sensors only model** predicts the fuel class from the gas, carbon
  monoxide, temperature and humidity channels alone.
- **The fusion model** combines those sensor readings with the outputs of both
  detectors and of the vision language model.

Both are evaluated on the same cases, so the value of combining the sources is
measured rather than assumed. Each returns a probability for four classes: no
fire, gas fire, liquid fuel and solid combustible.

## 3. Technologies

Table 4 lists the technologies used to build each part of the system.

**Table 4.** Technologies used in the implementation.

| Area | Technology |
|---|---|
| Services | Python 3, FastAPI, uvicorn |
| Containers | Docker, Docker Compose |
| Web server | nginx with a self-signed certificate |
| Object detection | YOLO11 (Ultralytics), trained on HomeFire and CrowdHuman |
| Vision language model | Gemini 2.5 Flash, through LangChain |
| Fire classification | scikit-learn and XGBoost, trained on CFAST simulation data |
| Dashboard | HTML, CSS and plain JavaScript, with no framework |
| Database | SQLite through aiosqlite |
| Notifications | Firebase Cloud Messaging |
| Hardware | ESP32 sensor node and ESP32-CAM module |

## 4. Setup and usage

**Requirements:**

- Docker and Docker Compose.
- A Google API key for Gemini.
- A camera, either a webcam or an ESP32-CAM board.
- Optional: an ESP32 sensor node and a Firebase service account key.

**Installation:**

```bash
cp sample.env .env          # then add your GOOGLE_API_KEY to .env
docker compose up --build   # nginx creates its certificate during the build
open https://localhost      # accept the certificate warning, then allow the camera
```

The certificate is self-signed, so the browser warns you the first time. This is
expected.

**Configuration.** Settings are environment variables in `docker-compose.yml`
and `.env`. Table 5 lists the ones you are most likely to change.

**Table 5.** Configuration variables, their defaults and their effect.

| Variable | Default | Meaning |
|---|---|---|
| `GOOGLE_API_KEY` | none | Your Gemini key. Verification needs it. |
| `SITE_KEY` | `unit7` | Which facility to load: `unit7` or `home`. |
| `HAZARD_RADIUS_M` | from the site file | How close to the fire a route may pass. |
| `HUMAN_MIN_CONF` | `0.40` | Confidence floor for counting a person. |
| `SENSOR_INGEST_KEY` | empty | Shared secret for the sensor nodes. |
| `COOLDOWN_SECONDS` | `120` | Minimum gap between two incidents in one zone. |
| `CLEAR_AFTER_SECONDS` | `30` | Quiet time before an incident closes. |
| `FIREBASE_CREDENTIALS` | `/secrets/firebase-sa.json` | Without it, pushes are logged instead of sent. |

Environment variables are read when a container starts. After changing one, run
`docker compose up -d --force-recreate <service>`, because a plain restart keeps
the old value.

**The detection setting.** The top bar has a switch that decides what counts as
a fire:

- **Industrial setting** alarms only for an unintended fire. A candle or a pilot
  light is treated as a normal controlled flame.
- **Home demo** alarms for any real flame, including a candle. Use this for
  demonstrations indoors.

**Checking that it works:**

```bash
curl -s  http://localhost:8090/health           # alert service
curl -s  http://localhost:8022/health           # sensor bridge
curl -sk https://localhost/api/classify/health  # fuel classifier

# send a test alarm without lighting anything
curl -X POST localhost:8090/api/test-alert -H 'content-type: application/json' \
     -d '{"zoneId":"fabric-store"}'
```

**Tests.** These run offline and need no Docker:

```bash
cd alert-service
python3 -m pytest test_routing.py -q   # the escape route scenarios
python3 -m pytest test_report.py -q    # the check applied before a report is released
python3 -m pytest test_api.py -q       # every endpoint, over HTTP
```

## 5. Scope and design decisions

Each point is a decision taken for a stated reason, with what it means for the
results.

- **The training data was selected to match the problem.** HomeFire was chosen
  over larger datasets because those show outdoor fires, while this work needs
  early indoor ones. CrowdHuman was chosen because it labels partly hidden
  people, which is the condition that matters around racking. The official splits
  are used unchanged, so the figures compare directly with published work.
- **Industrial premises could not be accessed**, and fires cannot be set safely
  in a working plant. The detection figures therefore describe indoor domestic and
  crowded scenes, and are reported on that basis.
- **Simulation made all four fuel classes testable.** Gas and liquid fuel fires
  cannot be created safely in a house, so an experimental dataset could only have
  covered solid combustibles. CFAST, developed by NIST, produced 570 runs across
  all four classes.
- **The models are tested on unfamiliar fires too.** Ninety runs use fuels and
  room sizes outside the training ranges, which checks whether the model
  recognises a fire unlike anything it has seen.
- **Fuel verdicts state their own confidence.** Validation against recorded fire
  is the next step, so the system marks every verdict as unvalidated rather than
  presenting an estimate as a finding.
- **The guidance covers the classes in scope.** Solid combustibles, liquid fuels
  and gas fires are supported, following ISO 3941. Class F is outside scope, so a
  cooking oil fire is reported as a liquid fuel and the system says so.
- **The detection loop runs in the browser**, which makes switching each
  configuration on and off easy for the ablation study. Monitoring stops when the
  tab is closed. Moving the loop server side is a contained change.
- **The classifier measures a clean air baseline first.** It declines to answer
  during the first 30 seconds rather than returning an unreliable verdict. Start
  monitoring before anything is lit.
- **Each source covers the weakness of the other.** Gas sensors react to cooking
  and solvents, which is why gas alone never sounds the alarm. Cameras need a
  clear view, which is why the sensors work independently of them.
- **Scope of the safety claim.** This is a research prototype. Its guidance is
  advisory and does not override statutory signage or a trained fire warden.
