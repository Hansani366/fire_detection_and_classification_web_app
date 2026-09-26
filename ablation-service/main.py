"""
FireWatch AI – ablation service

Scores one observation stream through five sensing combinations at once, so a
research paper can say what each modality actually contributes:

    1 sensors only        4 YOLO + VLM   (the rule the dashboard deploys today)
    2 YOLO only           5 sensors + YOLO + VLM  (the trained fusion model)
    3 sensors + YOLO

Five, not the eight the three components could make. The empty set never alarms,
and the two subsets that hold the VLM without YOLO cannot run at all: Algorithm 3
invokes the VLM only on a YOLO box. constants.py explains which arm was removed
and why.

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

THE TRAINED MODELS LIVE IN fire-classification-service, NOT HERE. This service
owns the research question -- the six rules, the metrics, the two ground-truth
definitions -- and asks the service that owns the weights for the two trained
arms. One copy of the weights, one set of pinned versions, and no way for the
research page and the live dashboard to disagree about the same fire. See
classifier_client.py.

THE NUMBERS ARE SYNTHETIC UNTIL REAL RECORDINGS SAY OTHERWISE. Both models were
trained on CFAST simulation, never on recorded fire. Every export carries that
flag, and /api/ablation/limitations is the list the UI renders.

MUST STAY SINGLE-WORKER: the batch job registry is in-process (see
Dockerfile).
"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

import classifier_client as CC
import constants as K
import runs as R

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("ablation")

# The service that owns sensor_model.joblib and fusion_model.joblib.
CLASSIFIER_URL = os.getenv("CLASSIFIER_URL", "http://fire-classification-service:8024")

FIRE_YOLO_URL = os.getenv("FIRE_YOLO_URL",
                          "http://fire-detection-yolo-service:8000/detect")
VLM_DETAILED_URL = os.getenv("VLM_DETAILED_URL",
                             "http://vlm-service:8019/describe-image-detailed/")

# Populated at startup. Everything downstream reads these.
STATE: dict = {}


async def _connect(attempts: int = 30, delay: float = 2.0):
    """Wait for fire-classification-service, then hold a client for it.

    Retried rather than failed fast: that service loads two models and runs a
    smoke prediction before it answers, so on a cold `compose up` it is
    routinely not ready when this one starts. depends_on orders the start, not
    the readiness.
    """
    last = None
    for attempt in range(attempts):
        try:
            client = await CC.ClassifierClient.connect(CLASSIFIER_URL)
            log.info("classifier ready: run_id=%s classes=%s versions_ok=%s",
                     client.health["manifest_run_id"], client.classes,
                     client.health["lib_versions_ok"])
            return client
        except Exception as exc:                                # noqa: BLE001
            last = exc
            if attempt == 0:
                log.info("waiting for %s …", CLASSIFIER_URL)
            await asyncio.sleep(delay)
    raise RuntimeError(
        f"fire-classification-service never became ready at {CLASSIFIER_URL}: {last}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    STATE["client"] = await _connect()
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
    client = STATE["client"]
    remote = client.health
    return {
        "status": "ok",
        "service": "ablation-service",
        # Mirrored from fire-classification-service so an export can name the
        # exact weights that produced it without a second round trip.
        "classifier_url": CLASSIFIER_URL,
        "manifest_run_id": remote["manifest_run_id"],
        "selected_model": remote["selected_model"],
        "classes": client.classes,
        "required_channels": remote["required_channels"],
        "lib_versions": remote["lib_versions"],
        "lib_versions_ok": remote["lib_versions_ok"],
        "checksums": remote["checksums"],
        "trainedOn": remote.get("trainedOn", "simulation"),
        "synthetic_warning": remote["synthetic_warning"],
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
    {"id": "full_contains_sensors", "severity": "medium",
     "title": f"Combination {K.FULL_COMBO} contains combination 1",
     "detail": f"Four of the fusion model's 96 features are sensor_model's class "
               f"probabilities, so 'fusion beats sensors' is partly "
               f"tautological. The informative comparisons are "
               f"{K.FULL_COMBO} against {K.NO_VLM_COMBO}, and "
               f"{K.FULL_COMBO} against 2."},
]


# Routes carry the full /api/ablation/ prefix because nginx's proxy_pass has no
# URI part and forwards the original path unchanged -- the same reason
# esp32-sensor-service and esp32-cam-service declare theirs that way.
@app.get("/api/ablation/health")
async def health():
    return _health_payload()


@app.get("/api/ablation/config")
async def config():
    """The frozen constants, including each combination's printed rule.

    The page renders its rule text from this response rather than holding its
    own copy, so what is printed and what was executed cannot disagree.
    """
    return K.describe(STATE["client"].manifest)


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
    # "strict" treats pre-ignition windows of a fire run as negatives;
    # "as_trained" matches the dataset's own labels and metrics.csv. See
    # metrics.build_truth for why both exist.
    ground_truth: str = "strict"


@app.post("/api/ablation/runs", status_code=202)
async def create_run(body: RunIn):
    unknown = [c for c in body.combos if c not in K.COMBOS]
    if unknown:
        raise HTTPException(400, f"unknown combinations: {unknown}")
    if body.ground_truth not in ("strict", "as_trained"):
        raise HTTPException(400, "ground_truth must be 'strict' or 'as_trained'")
    try:
        run_id = await R.submit(body.dataset_id, sorted(set(body.combos)),
                                STATE["client"], body.experiment_ids,
                                body.ground_truth, FIRE_YOLO_URL, VLM_DETAILED_URL)
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
        return R.export_json(run_id, _health_payload(), K.describe(STATE["client"].manifest))
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
