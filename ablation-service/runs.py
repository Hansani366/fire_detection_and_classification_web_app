"""
Batch runs: a job registry, and the export that a paper actually cites.

WHY RUNS ARE ASYNCHRONOUS RATHER THAN A PLAIN POST. nginx caps every proxied
request at 30s by default, and a run over real recordings spends most of its
time waiting on Gemini -- minutes, not seconds. So a run is submitted, polled,
and then read, and nothing has to be held open.

WHY A THREAD AND NOT A PROCESS POOL. The worry was that a long pandas feature
build would stall the 1 Hz live tick inside a single-worker service. Measured
on the full 96-experiment test split: build_features 0.6s, score 0.3s,
evaluate 0.3s. That is a ~1.2s stall in the worst case, only if a batch run and
a live session overlap, so the complexity of shipping models across a process
boundary buys very little. asyncio.to_thread keeps the event loop responsive
during the I/O-bound part, which for recordings is nearly all of it. Revisit
this if recordings ever get big enough to matter.

WHAT AN EXPORT MUST CONTAIN TO BE CITABLE. Not just the numbers: the model's
run_id, the checksums of the two joblibs, the checksum of the input data, the
full frozen constants, and the synthetic flag. A results table with no
provenance cannot be reproduced, and a reviewer is entitled to ask.
"""

from __future__ import annotations

import asyncio
import csv
import hashlib
import io
import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

import combos
import constants as K
import metrics as M

DATA_DIR = Path(__file__).resolve().parent / "data"

# Replayed CFAST splits. `synthetic` is not cosmetic -- it drives the warning
# banner and a column in every export, because an accuracy figure from
# simulation must never be quotable without that word attached.
REPLAY_SETS = {
    "test_split": {
        "file": "test_split.csv",
        "label": "CFAST test split (held out)",
        "synthetic": True,
        "note": "The 96 experiments never used for training or model selection.",
    },
    "ood_split": {
        "file": "ood_split.csv",
        "label": "CFAST out-of-distribution split",
        "synthetic": True,
        "note": "90 experiments burning three fuels the model never saw (PVC, "
                "polystyrene, magnesium/lithium), labelled 'unknown'. Read it "
                "for RECALL only. The fuel table is not scored, because no "
                "prediction can match a class that was never trained; and "
                "every experiment here is a fire, so there are no negatives — "
                "precision, accuracy and false-alarm rate are degenerate at "
                "1.0, 1.0 and undefined, and mean nothing. What it does show "
                "honestly is whether an unfamiliar fire is still caught.",
        "degenerate_binary": True,
    },
}

RUNS: dict[str, dict] = {}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def list_datasets() -> list[dict]:
    out = []
    for ds_id, spec in REPLAY_SETS.items():
        path = DATA_DIR / spec["file"]
        if not path.exists():
            continue
        frame = pd.read_csv(path, usecols=["experiment_id", "fire_type"])
        out.append({
            "id": ds_id,
            "kind": "replay",
            "label": spec["label"],
            "synthetic": spec["synthetic"],
            "note": spec["note"],
            "rows": int(len(frame)),
            "experiments": int(frame["experiment_id"].nunique()),
            "classes": {k: int(v) for k, v in
                        frame.groupby("experiment_id")["fire_type"].first()
                             .value_counts().items()},
            "degenerate_binary": spec.get("degenerate_binary", False),
        })
    return out


def _run_sync(dataset_id: str, combo_ids: list[int], clf, manifest: dict,
              experiment_ids: list[str] | None) -> dict:
    """The whole evaluation, start to finish. Runs off the event loop."""
    spec = REPLAY_SETS[dataset_id]
    path = DATA_DIR / spec["file"]
    frame = pd.read_csv(path)
    if experiment_ids:
        frame = frame[frame["experiment_id"].isin(experiment_ids)]
        if frame.empty:
            raise ValueError("no experiments matched")

    timings = {}
    t0 = time.perf_counter()
    features = clf.build_features(frame)
    timings["build_features_ms"] = round((time.perf_counter() - t0) * 1000)

    t0 = time.perf_counter()
    scored = combos.score_all(features, manifest, clf, combo_ids)
    timings["score_ms"] = round((time.perf_counter() - t0) * 1000)

    truth = M.build_truth(frame, features)
    t0 = time.perf_counter()
    result = M.evaluate(scored, truth, clf, manifest, spec["synthetic"])
    timings["evaluate_ms"] = round((time.perf_counter() - t0) * 1000)

    # The OOD split's label is "unknown", a class the model was never trained
    # to emit, so a fuel table there would score every prediction wrong for a
    # reason that has nothing to do with the model's fuel discrimination.
    if dataset_id == "ood_split":
        result.pop("fuel", None)
        result["fuel_note"] = (
            "Not scored: these fuels have no trained class. The binary table "
            "below is the meaningful one."
        )

    result["timings"] = timings
    result["dataset"] = {
        "id": dataset_id, "label": spec["label"], "kind": "replay",
        "synthetic": spec["synthetic"], "note": spec["note"],
        "sha256": _sha256_file(path),
    }
    # Per-window rows, kept so the CSV export can be written without rerunning.
    result["_windows"] = _window_table(frame, features, truth, scored, clf)
    return result


def _window_table(frame, features, truth, scored, clf) -> list[dict]:
    rows = {
        "experiment_id": truth["experiment_id"].to_numpy(),
        "window_idx": truth["window_idx"].to_numpy(),
        "fire_type": truth["fire_type"].to_numpy(),
        "y_window": truth["y_window"].to_numpy().astype(int),
        "ignition_window": truth["ignition_window"].to_numpy(),
    }
    for c in sorted(scored["alarm"]):
        rows[f"combo{c}_alarm"] = scored["alarm"][c].to_numpy().astype(int)
        rows[f"combo{c}_score"] = scored["score"][c].to_numpy().round(6)
    if scored.get("fuel") is not None:
        rows["combo6_class"] = scored["fuel"]["predicted_class"].to_numpy()
        rows["combo6_confidence"] = scored["fuel"]["confidence"].to_numpy().round(6)
    return pd.DataFrame(rows).to_dict("records")


async def submit(dataset_id: str, combo_ids: list[int], clf, manifest: dict,
                 experiment_ids: list[str] | None = None) -> str:
    if dataset_id not in REPLAY_SETS:
        raise KeyError(dataset_id)
    run_id = f"run_{uuid.uuid4().hex[:10]}"
    RUNS[run_id] = {
        "run_id": run_id, "status": "queued", "dataset_id": dataset_id,
        "combos": combo_ids, "started_at": _now(), "finished_at": None,
        "error": None, "result": None,
    }

    async def _go():
        RUNS[run_id]["status"] = "running"
        try:
            result = await asyncio.to_thread(
                _run_sync, dataset_id, combo_ids, clf, manifest, experiment_ids)
            RUNS[run_id]["result"] = result
            RUNS[run_id]["status"] = "done"
        except Exception as exc:                       # noqa: BLE001
            RUNS[run_id]["status"] = "error"
            RUNS[run_id]["error"] = f"{type(exc).__name__}: {exc}"
        finally:
            RUNS[run_id]["finished_at"] = _now()

    asyncio.create_task(_go())
    return run_id


def status(run_id: str) -> dict:
    run = RUNS[run_id]
    return {k: v for k, v in run.items() if k != "result"}


def results(run_id: str) -> dict:
    run = RUNS[run_id]
    if run["status"] != "done":
        raise ValueError(f"run is {run['status']}")
    return {k: v for k, v in run["result"].items() if not k.startswith("_")}


def export_json(run_id: str, health: dict, config: dict) -> dict:
    """The citable artifact: numbers plus everything needed to reproduce them."""
    run = RUNS[run_id]
    if run["status"] != "done":
        raise ValueError(f"run is {run['status']}")
    return {
        "exported_at": _now(),
        "run": {k: v for k, v in run.items() if k != "result"},
        "provenance": {
            "manifest_run_id": health["manifest_run_id"],
            "selected_model": health["selected_model"],
            "model_checksums": health["checksums"],
            "library_versions": health["lib_versions"],
            "library_versions_ok": health["lib_versions_ok"],
            "data_source": health["data_source"],
            "synthetic_warning": health["synthetic_warning"],
        },
        "config": config,
        "results": results(run_id),
    }


def export_csv(run_id: str, level: str = "window") -> str:
    run = RUNS[run_id]
    if run["status"] != "done":
        raise ValueError(f"run is {run['status']}")
    result = run["result"]
    buf = io.StringIO()

    if level == "window":
        rows = result["_windows"]
        writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
        return buf.getvalue()

    # Event level: one row per combination -- the table that goes in the paper.
    fields = ["combo", "name", "sensors", "yolo", "vlm", "synthetic",
              "window_accuracy", "window_precision", "window_recall", "window_f1",
              "window_false_alarm_rate", "false_alarms_per_hour",
              "event_accuracy", "event_precision", "event_recall", "event_f1",
              "median_detection_s", "p90_detection_s", "events_never_detected",
              "vs_combo6_event_delta", "vs_combo6_p_value"]
    writer = csv.DictWriter(buf, fieldnames=fields)
    writer.writeheader()
    for c, r in sorted(result["combos"].items()):
        w, e, lat = r["window"], r["event"], r["latency"]
        vs = r.get("vs_combo6", {})
        writer.writerow({
            "combo": c, "name": r["name"],
            "sensors": int(r["modalities"]["sensors"]),
            "yolo": int(r["modalities"]["yolo"]),
            "vlm": int(r["modalities"]["vlm"]),
            "synthetic": int(result["synthetic"]),
            "window_accuracy": round(w["accuracy"], 6),
            "window_precision": round(w["precision"], 6),
            "window_recall": round(w["recall"], 6),
            "window_f1": round(w["f1"], 6),
            "window_false_alarm_rate": round(w["false_alarm_rate"], 6),
            "false_alarms_per_hour": round(w["false_alarms_per_hour"], 1),
            "event_accuracy": round(e["accuracy"], 6),
            "event_precision": round(e["precision"], 6),
            "event_recall": round(e["recall"], 6),
            "event_f1": round(e["f1"], 6),
            "median_detection_s": lat["median_detection_s"],
            "p90_detection_s": lat["p90_detection_s"],
            "events_never_detected": lat["events_never_detected"],
            "vs_combo6_event_delta": vs.get("event_delta"),
            "vs_combo6_p_value": round(vs["p_value"], 6) if vs else None,
        })
    return buf.getvalue()
