"""
FireWatch AI – fire classification service

THE ONE PLACE THE TRAINED MODELS LIVE. `sensor_model.joblib` and
`fusion_model.joblib` are loaded here and nowhere else. Everything that needs a
fuel verdict -- the live dashboard, and the ablation page's combination 6 --
asks this service, so there is a single copy of the weights, a single set of
pinned library versions, and no way for two services to drift into disagreeing
about the same fire.

WHAT IT ANSWERS: "what is burning?", not "is something burning?". Measured on
the 96 held-out test experiments, the fusion model and a sensors-only model
agreed on 95 of them for plain fire/no-fire -- so fusion adds almost nothing to
detection. It reaches 0.948 event accuracy naming the fuel, which nothing else
in the system can do at all. Detection stays with YOLO, the VLM and the sensor
thresholds; this service is for the fuel.

SENSOR_MODEL IS A REQUIRED SUB-MODEL, NOT AN ALTERNATIVE. The fusion model
reads no raw sensor values: its features 92-95 are sensor_model's predict_proba
output. `fire_classifier.build_features()` splices them in. See
model/PROVENANCE.md.

TRAINING IS EXACTLY 1 Hz, AND EVERY TEMPORAL CONSTANT COUNTS SAMPLES. Sessions
here advance one window per tick and callers are expected to tick at 1 Hz;
anything else silently rescales the 25-window persistence mean.

THE NUMBERS ARE SYNTHETIC UNTIL REAL RECORDINGS SAY OTHERWISE. Both models were
trained on CFAST simulation and have never seen a recorded fire. Every response
carries `trainedOn: "simulation"` so a caller cannot present a verdict as
validated when it is not.

MUST STAY SINGLE-WORKER: sessions are in-process (see Dockerfile).
"""

import hashlib
import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import constants as K
import session as L
from fire_classifier import FireClassifier
from sensor_adapter import SensorGapError

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("classify")

MODEL_DIR = Path(__file__).resolve().parent / "model"

# A drifted library silently changes predictions rather than failing, which for
# a safety system is the worst possible failure mode -- so refuse to start. The
# escape hatch exists for debugging and is reported in /health, so a verdict
# from a drifted container can never look clean.
ALLOW_VERSION_DRIFT = os.getenv("CLASSIFY_ALLOW_VERSION_DRIFT", "") == "1"

FIRE_YOLO_URL = os.getenv("FIRE_YOLO_URL",
                          "http://fire-detection-yolo-service:8000/detect")
VLM_DETAILED_URL = os.getenv("VLM_DETAILED_URL",
                             "http://vlm-service:8019/describe-image-detailed/")
SENSOR_LATEST_URL = os.getenv("SENSOR_LATEST_URL",
                              "http://esp32-sensor-service:8022/api/sensors/latest")

STATE: dict = {}


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _check_versions(manifest: dict) -> tuple[bool, dict]:
    """Compare the running libraries against the ones that wrote the pickles.

    joblib bundles carry `_sklearn_version` inside the pickle; a minor mismatch
    raises InconsistentVersionWarning and can unpickle to a subtly different
    estimator. Catching it here turns a silent wrong-answer bug into a
    container that will not start.
    """
    import sklearn
    import xgboost

    have = {"sklearn": sklearn.__version__, "xgboost": xgboost.__version__,
            "pandas": pd.__version__}
    want = manifest["library_versions"]
    report = {k: {"want": want[k], "have": have[k], "ok": want[k] == have[k]} for k in want}
    return all(v["ok"] for v in report.values()), report


def _smoke_frame(clf: FireClassifier, rows: int = 30) -> pd.DataFrame:
    """A minimal in-distribution sequence, to prove the model runs at startup.

    Built from `required_columns()` so it cannot drift from the manifest.
    Values are the quiet-room resting state: zeros except the two channels
    whose "nothing happening" value is not zero.
    """
    frame = pd.DataFrame(0.0, index=range(rows), columns=clf.required_columns())
    if "vlm_staleness_s" in frame:
        frame["vlm_staleness_s"] = K.VLM_NEVER_INVOKED_STALENESS
    if "temperature_c" in frame:
        frame["temperature_c"] = 22.0
    if "humidity_pct" in frame:
        frame["humidity_pct"] = 55.0
    frame["experiment_id"] = "smoke"
    frame["timestamp"] = pd.date_range("2026-01-01", periods=rows, freq="1s")
    return frame


def _load() -> dict:
    manifest = json.loads((MODEL_DIR / "manifest.json").read_text())
    ok, versions = _check_versions(manifest)
    if not ok:
        detail = ", ".join(f"{k}: want {v['want']}, have {v['have']}"
                           for k, v in versions.items() if not v["ok"])
        message = f"library versions do not match model/manifest.json ({detail})"
        if not ALLOW_VERSION_DRIFT:
            raise RuntimeError(
                message + ". These pickles were written by those exact versions. "
                "Fix requirements.txt, or set CLASSIFY_ALLOW_VERSION_DRIFT=1 to "
                "start anyway -- verdicts will be flagged as untrusted.")
        log.warning("STARTING WITH DRIFTED LIBRARIES: %s", message)

    clf = FireClassifier.load(MODEL_DIR)

    # Prove the whole pipeline runs now, not on the first real request: both
    # joblibs unpickle, the sensor model's probabilities splice into the fusion
    # feature matrix, and all 96 columns build.
    result = clf.predict(_smoke_frame(clf))
    assert len(result) == 30, f"smoke prediction returned {len(result)} rows"

    checksums = {p.name: _sha256(p) for p in sorted(MODEL_DIR.iterdir())
                 if p.suffix in (".joblib", ".json")}
    log.info("loaded run_id=%s selected=%s classes=%s",
             manifest["run_id"], manifest["selected_model"], clf.classes)
    log.info("smoke prediction ok: %s", result["predicted_class"].iloc[-1])

    return {"clf": clf, "manifest": manifest, "versions": versions,
            "versions_ok": ok, "checksums": checksums}


@asynccontextmanager
async def lifespan(app: FastAPI):
    STATE.update(_load())
    yield


app = FastAPI(title="FireWatch Fire Classification Service", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])


# Routes carry the full /api/classify/ prefix because nginx's proxy_pass has no
# URI part and forwards the original path unchanged.
@app.get("/api/classify/health")
async def health():
    clf: FireClassifier = STATE["clf"]
    manifest = STATE["manifest"]
    return {
        "status": "ok",
        "service": "fire-classification-service",
        "manifest_run_id": manifest["run_id"],
        "selected_model": manifest["selected_model"],
        "classes": clf.classes,
        # The manifest's temporal configuration, served so that callers do not
        # each keep a copy. `smooth_window`, `persistence_window` and
        # `gate_threshold` describe how the model treats time, and a caller
        # that guessed them would smooth over a different span than the model
        # was trained with.
        "config": manifest["config"],
        "required_channels": clf.required_columns(),
        "lib_versions": STATE["versions"],
        "lib_versions_ok": STATE["versions_ok"],
        "checksums": STATE["checksums"],
        "trainedOn": "simulation",
        "synthetic_warning": manifest["synthetic_warning"],
        "sessions": len(L.SESSIONS),
    }


# ── Batch: the whole-sequence path, used by ablation-service ─────────────────

class BatchIn(BaseModel):
    """Raw observation rows for one or more experiments.

    The caller sends the 27 raw channels plus experiment_id and timestamp, and
    gets back both probability sets. It deliberately does NOT get the 96 built
    features: those are the model's internals, and returning them would invite
    a caller to reimplement the feature pipeline and drift from it.
    """
    rows: list[dict]
    smooth: bool = False


@app.post("/api/classify/batch")
async def classify_batch(body: BatchIn):
    """Score a whole sequence. Returns fusion AND sensor probabilities.

    Both, because a caller comparing a sensors-only arm against the full model
    needs the sensor model's own output — and running it twice in two services
    is how the two end up disagreeing.
    """
    if not body.rows:
        raise HTTPException(400, "rows must not be empty")
    clf: FireClassifier = STATE["clf"]
    try:
        frame = pd.DataFrame(body.rows)
        features = clf.build_features(frame)
        fusion = clf.fusion.predict_proba(features[clf.fusion_features])
        if body.smooth:
            fusion = clf._smooth(fusion, features["experiment_id"].to_numpy())
        sensor = features[[f"sensor_p_{c}" for c in clf.classes]].to_numpy()
    except ValueError as exc:
        raise HTTPException(400, str(exc))

    return {
        "classes": clf.classes,
        "n": int(len(features)),
        # Row order follows build_features, which sorts by (experiment_id,
        # timestamp) -- so these are returned too, and the caller must align on
        # them rather than assuming its input order survived.
        "experiment_id": features["experiment_id"].tolist(),
        "window_idx": features["window_idx"].tolist(),
        "fusion_proba": fusion.tolist(),
        "sensor_proba": sensor.tolist(),
        "trainedOn": "simulation",
    }


# ── Live sessions: the dashboard path ────────────────────────────────────────

class SessionIn(BaseModel):
    zoneId: str = "fabric-store"
    sensor_source: str = "node"          # node | none
    device_id: str | None = None
    baseline_mode: str = "quiet_prefix"  # quiet_prefix | running_min


@app.post("/api/classify/sessions", status_code=201)
async def create_session(body: SessionIn):
    if body.sensor_source not in ("node", "none"):
        raise HTTPException(400, "sensor_source must be 'node' or 'none'")
    try:
        s = L.create(body.zoneId, body.sensor_source, body.device_id, body.baseline_mode)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return s.status()


@app.post("/api/classify/sessions/{sid}/tick")
async def session_tick(sid: str, file: UploadFile = File(...),
                       frame_w: int = Form(640), frame_h: int = Form(480),
                       flicker_hz: float = Form(K.FLICKER_QUIET_HZ)):
    """One 1 Hz window. The caller sends the frame; this service does the rest."""
    s = L.SESSIONS.get(sid)
    if s is None:
        raise HTTPException(404, "no such session")
    try:
        return await L.tick(s, await file.read(), frame_w, frame_h, flicker_hz,
                            FIRE_YOLO_URL, VLM_DETAILED_URL, SENSOR_LATEST_URL,
                            STATE["clf"])
    except SensorGapError as exc:
        raise HTTPException(409, str(exc))
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    except RuntimeError as exc:
        raise HTTPException(502, str(exc))


@app.get("/api/classify/sessions/{sid}")
async def get_session(sid: str):
    s = L.SESSIONS.get(sid)
    if s is None:
        raise HTTPException(404, "no such session")
    return {**s.status(), "last": s.last}


@app.delete("/api/classify/sessions/{sid}")
async def delete_session(sid: str):
    if L.SESSIONS.pop(sid, None) is None:
        raise HTTPException(404, "no such session")
    return {"deleted": sid}
