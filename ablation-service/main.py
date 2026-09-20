"""
FireWatch AI – ablation service

Scores one observation stream through six sensing combinations at once, so a
research paper can say what each modality actually contributes:

    1 sensors only        4 sensors + YOLO
    2 YOLO only           5 VLM + YOLO   (the rule the dashboard deploys today)
    3 VLM only            6 sensors + YOLO + VLM  (the trained fusion model)

THE MODEL IS NOT A FRAME CLASSIFIER. 72 of the fusion model's 96 features are
rolling statistics, running maxima and a 25-window persistence mean. Its own
docstring says a detached row "will produce a prediction, but a poor one", and
demo.py forbids trimming the buffer because cummax and persistence reach back
to the start of the session. So everything here is organised around a *session*
that owns its whole history, never around a stateless POST.

TRAINING IS EXACTLY 1 Hz, AND EVERY TEMPORAL CONSTANT IS IN SAMPLES. 180 rows
per 180-second experiment; `roll_windows [5,15]`, `persistence_window 25` and
`smooth_window 5` count samples, not seconds, and `vlm_staleness_s` is a sample
count that only reads as seconds because the rate is 1 Hz. Our inputs do not
arrive at 1 Hz -- the dashboard loop is 2 Hz and the sensor nodes post every
3 s -- so this service owns a 1 Hz windowing clock and resamples onto it. Feed
native rates and `persistence_window` quietly covers 12.5 s instead of 25 s.

SENSOR_MODEL IS A REQUIRED SUB-MODEL, NOT AN ALTERNATIVE. The fusion model
reads no raw sensor values; its features 92-95 are sensor_model's predict_proba
output. See model/PROVENANCE.md.

THE NUMBERS ARE SYNTHETIC UNTIL REAL RECORDINGS SAY OTHERWISE. Both models were
trained on CFAST simulation, never on recorded fire. Every export carries that
flag, and /api/ablation/limitations is the list the UI renders.

MUST STAY SINGLE-WORKER: live sessions and the batch job registry are
in-process (see Dockerfile).
"""

import hashlib
import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

import constants as K
import runs as R
from fire_classifier import FireClassifier

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("ablation")

MODEL_DIR = Path(__file__).resolve().parent / "model"

# A drifted library silently changes predictions rather than failing, which in a
# research setting is the worst possible failure mode -- so refuse to start.
# The escape hatch exists for debugging and is reported in /health, so a result
# exported from a drifted container can never look clean.
ALLOW_VERSION_DRIFT = os.getenv("ABLATION_ALLOW_VERSION_DRIFT", "") == "1"

# Populated at startup by _load(). Everything downstream reads these.
STATE: dict = {}


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _installed_versions() -> dict[str, str]:
    import sklearn
    import xgboost

    return {
        "sklearn": sklearn.__version__,
        "xgboost": xgboost.__version__,
        "pandas": pd.__version__,
    }


def _check_versions(manifest: dict) -> tuple[bool, dict]:
    """Compare the running libraries against the ones that wrote the pickles.

    joblib bundles carry `_sklearn_version` inside the pickle; a minor mismatch
    raises InconsistentVersionWarning and can unpickle to a subtly different
    estimator. Catching that here converts a silent wrong-answer bug into a
    container that will not start.
    """
    want = manifest["library_versions"]
    have = _installed_versions()
    report = {
        name: {"want": want[name], "have": have[name], "ok": want[name] == have[name]}
        for name in want
    }
    return all(entry["ok"] for entry in report.values()), report


def _smoke_frame(clf: FireClassifier, rows: int = 30) -> pd.DataFrame:
    """A minimal in-distribution sequence, used only to prove the model runs.

    Built from `required_columns()` rather than a hardcoded list so it cannot
    drift from the manifest. Values are the quiet-room resting state: zeros
    everywhere except the two channels whose 'nothing happening' value is not
    zero -- `vlm_staleness_s` is -1.0 for 'never invoked', and the MQ baselines
    sit at the training priors so the deltas are near zero rather than hugely
    negative.
    """
    channels = clf.required_columns()
    frame = pd.DataFrame(0.0, index=range(rows), columns=channels)
    if "vlm_staleness_s" in frame:
        frame["vlm_staleness_s"] = -1.0
    if "temperature_c" in frame:
        frame["temperature_c"] = 22.0
    if "humidity_pct" in frame:
        frame["humidity_pct"] = 55.0
    frame["experiment_id"] = "smoke"
    frame["timestamp"] = pd.date_range("2026-01-01", periods=rows, freq="1s")
    return frame


def _load() -> dict:
    manifest = json.loads((MODEL_DIR / "manifest.json").read_text())
    versions_ok, versions = _check_versions(manifest)
    if not versions_ok:
        detail = ", ".join(
            f"{k}: want {v['want']}, have {v['have']}"
            for k, v in versions.items()
            if not v["ok"]
        )
        message = f"library versions do not match model/manifest.json ({detail})"
        if not ALLOW_VERSION_DRIFT:
            raise RuntimeError(
                message + ". These pickles were written by those exact versions. "
                "Fix requirements.txt, or set ABLATION_ALLOW_VERSION_DRIFT=1 to "
                "start anyway -- results will be flagged as untrusted."
            )
        log.warning("STARTING WITH DRIFTED LIBRARIES: %s", message)

    clf = FireClassifier.load(MODEL_DIR)

    # Prove the whole pipeline runs now, not on the first real request: both
    # joblibs unpickle, the sensor model's probabilities splice into the fusion
    # feature matrix, and all 96 columns get built.
    result = clf.predict(_smoke_frame(clf))
    assert len(result) == 30, f"smoke prediction returned {len(result)} rows"
    assert set(clf.classes) <= set(
        c[2:] for c in result.columns if c.startswith("p_")
    ), "smoke prediction did not emit one probability column per class"

    checksums = {
        p.name: _sha256(p)
        for p in sorted(MODEL_DIR.iterdir())
        if p.suffix in (".joblib", ".json")
    }

    log.info(
        "loaded run_id=%s selected=%s classes=%s fusion_features=%d sensor_features=%d",
        manifest["run_id"],
        manifest["selected_model"],
        clf.classes,
        len(clf.fusion_features),
        len(clf.sensor_features),
    )
    log.info("smoke prediction ok: %s", result["predicted_class"].iloc[-1])

    return {
        "clf": clf,
        "manifest": manifest,
        "versions": versions,
        "versions_ok": versions_ok,
        "checksums": checksums,
    }


@asynccontextmanager
async def lifespan(app: FastAPI):
    STATE.update(_load())
    yield


app = FastAPI(title="FireWatch Ablation Service", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _health_payload() -> dict:
    clf: FireClassifier = STATE["clf"]
    manifest = STATE["manifest"]
    return {
        "status": "ok",
        "service": "ablation-service",
        "manifest_run_id": manifest["run_id"],
        "selected_model": manifest["selected_model"],
        "classes": clf.classes,
        "fusion_features": len(clf.fusion_features),
        "sensor_features": len(clf.sensor_features),
        "needs_sensor_proba": clf.needs_sensor_proba,
        "required_channels": clf.required_columns(),
        "lib_versions": STATE["versions"],
        "lib_versions_ok": STATE["versions_ok"],
        "checksums": STATE["checksums"],
        "data_source": manifest["data_source"],
        "synthetic_warning": manifest["synthetic_warning"],
    }


# Every limitation here is measured, not guessed, and the UI renders this list
# rather than hardcoding it -- so a caveat cannot quietly fall out of the paper
# while staying true of the system.
LIMITATIONS = [
    {"id": "synthetic", "severity": "high",
     "title": "Both trained models learned from simulation, not from fire",
     "detail": "fusion_model and sensor_model were trained on CFAST-generated "
               "data. Neither has ever seen a recorded fire, and the camera "
               "branch of the generator was invented rather than measured. Any "
               "accuracy figure from the replay tabs describes the generator."},
    {"id": "fusion_gain", "severity": "high",
     "title": "The fusion model's gain over sensors alone is within the noise",
     "detail": "On the held-out test split the published event accuracy is "
               "0.9479 for the fusion model and 0.9375 for sensors alone — a "
               "difference of one event in 96. Every comparison on this page "
               "therefore carries a paired McNemar test and the absolute event "
               "count, not just a percentage."},
    {"id": "temperature_gap", "severity": "high",
     "title": "Real temperature sensors cannot reach the trained range",
     "detail": "Training temperature_c has a 95th percentile of 202 °C and a "
               "maximum of 314 °C, because CFAST reports the hot upper layer. A "
               "DHT22 is rated to 80 °C and will fail well before 200. "
               "Temperature and its rolling statistics are a large share of the "
               "sensor model's 53 features, so live readings sit far below the "
               "range the model learned on."},
    {"id": "mq_gap", "severity": "low",
     "title": "Gas-sensor range is mostly reachable, the extreme tail is not",
     "detail": "99% of test rows have mq2_delta below 650 ADC counts, well "
               "inside a 12-bit ADC's 4095. Only the flashover tail exceeds it. "
               "This gap is much smaller than the temperature one."},
    {"id": "confidence_novelty", "severity": "medium",
     "title": "Confidence does not detect unfamiliar fuels",
     "detail": "Measured as a novelty detector on held-out fuels it scores "
               "AUROC 0.486 — chance. Do not read a high confidence as "
               "'this is a familiar situation'. The out-of-distribution split "
               "on this page shows what that costs."},
    {"id": "combo6_contains_combo1", "severity": "medium",
     "title": "Combination 6 contains combination 1",
     "detail": "Four of the fusion model's 96 features are sensor_model's class "
               "probabilities, so 'fusion beats sensors' is partly "
               "tautological. The informative comparisons are 6 against 4, and "
               "6 against 2."},
    {"id": "live_no_truth", "severity": "medium",
     "title": "The Live tab cannot measure accuracy",
     "detail": "Nothing on the live feed carries a ground-truth label, so the "
               "Live tab shows agreement and disagreement between the six "
               "combinations and never an accuracy figure."},
]


# Routes carry the full /api/ablation/ prefix because nginx's proxy_pass has no
# URI part and forwards the original path unchanged -- the same reason
# sensor-service and esp32-service declare theirs that way.
@app.get("/api/ablation/health")
async def health():
    return _health_payload()


@app.get("/api/ablation/config")
async def config():
    """The frozen constants, including each combination's printed rule.

    The page renders its rule text from this response rather than holding its
    own copy, so what is printed and what was executed cannot disagree.
    """
    return K.describe(STATE["manifest"])


@app.get("/api/ablation/limitations")
async def limitations():
    return {"limitations": LIMITATIONS}


@app.get("/api/ablation/datasets")
async def datasets():
    return {"datasets": R.list_datasets()}


class RunIn(BaseModel):
    dataset_id: str = "test_split"
    combos: list[int] = Field(default_factory=lambda: sorted(K.COMBOS))
    experiment_ids: list[str] | None = None


@app.post("/api/ablation/runs", status_code=202)
async def create_run(body: RunIn):
    unknown = [c for c in body.combos if c not in K.COMBOS]
    if unknown:
        raise HTTPException(400, f"unknown combinations: {unknown}")
    try:
        run_id = await R.submit(body.dataset_id, sorted(set(body.combos)),
                                STATE["clf"], STATE["manifest"], body.experiment_ids)
    except KeyError:
        raise HTTPException(404, f"unknown dataset: {body.dataset_id}")
    return {"run_id": run_id, "status": "queued"}


@app.get("/api/ablation/runs")
async def list_runs():
    return {"runs": [R.status(r) for r in R.RUNS]}


@app.get("/api/ablation/runs/{run_id}")
async def get_run(run_id: str):
    if run_id not in R.RUNS:
        raise HTTPException(404, "no such run")
    return R.status(run_id)


@app.get("/api/ablation/runs/{run_id}/results")
async def get_results(run_id: str):
    if run_id not in R.RUNS:
        raise HTTPException(404, "no such run")
    try:
        return R.results(run_id)
    except ValueError as exc:
        raise HTTPException(409, str(exc))


@app.get("/api/ablation/runs/{run_id}/export.json")
async def export_json(run_id: str):
    if run_id not in R.RUNS:
        raise HTTPException(404, "no such run")
    try:
        return R.export_json(run_id, _health_payload(), K.describe(STATE["manifest"]))
    except ValueError as exc:
        raise HTTPException(409, str(exc))


@app.get("/api/ablation/runs/{run_id}/export.csv", response_class=PlainTextResponse)
async def export_csv(run_id: str, level: str = "event"):
    if run_id not in R.RUNS:
        raise HTTPException(404, "no such run")
    if level not in ("window", "event"):
        raise HTTPException(400, "level must be 'window' or 'event'")
    try:
        return PlainTextResponse(
            R.export_csv(run_id, level),
            headers={"content-disposition":
                     f'attachment; filename="{run_id}_{level}.csv"'},
        )
    except ValueError as exc:
        raise HTTPException(409, str(exc))


@app.delete("/api/ablation/runs/{run_id}")
async def delete_run(run_id: str):
    if R.RUNS.pop(run_id, None) is None:
        raise HTTPException(404, "no such run")
    return {"deleted": run_id}
