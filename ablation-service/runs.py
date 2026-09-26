"""
Batch runs: a job registry, and the export that a paper actually cites.

WHY RUNS ARE ASYNCHRONOUS RATHER THAN A PLAIN POST. nginx caps every proxied
request at 30s by default, and a run over real recordings spends most of its
time waiting on Gemini -- minutes, not seconds. So a run is submitted, polled,
and then read, and nothing has to be held open.

WHY A THREAD AND NOT A PROCESS POOL. The heavy part -- building 96 features
and running two models -- now happens in fire-classification-service, so what
is left here is rules and arithmetic: a few hundred milliseconds on the full
96-experiment split. asyncio.to_thread keeps the event loop responsive while it
runs, which matters because the model call before it is I/O and this service is
pinned to one worker.

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

import classifier_client as CC
import combos
import constants as K
import metrics as M
import recordings

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
    out = list(_replay_datasets())
    try:
        out.extend(recordings.list_recordings())
    except Exception as exc:                                    # noqa: BLE001
        # A malformed recording folder must not hide the replay sets, which
        # are the ones that always work.
        out.append({"id": "rec/?", "kind": "recording", "error": str(exc)})
    return out


def _replay_datasets():
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


def _score_frame(frame: pd.DataFrame, dataset: dict, combo_ids: list[int],
                 client, proba: dict, ground_truth: str, timings: dict) -> dict:
    """Six combinations -> metrics, over raw rows plus the remote probabilities.

    Pure CPU, so it runs off the event loop. The model call already happened:
    everything here is rules, rolling statistics and arithmetic.
    """
    manifest = client.manifest
    # Reproduce the ordering the classification service scored in, or every
    # metric would be computed against misaligned probabilities.
    features = CC.sorted_like_service(frame)

    t0 = time.perf_counter()
    scored = combos.score_all(features, manifest, client.classes, proba, combo_ids)
    timings["score_ms"] = round((time.perf_counter() - t0) * 1000)

    truth = M.build_truth(frame, features, ground_truth)
    t0 = time.perf_counter()
    result = M.evaluate(scored, truth, client.classes, manifest, dataset["synthetic"])
    timings["evaluate_ms"] = round((time.perf_counter() - t0) * 1000)

    result["timings"] = timings
    result["dataset"] = dataset
    result["_windows"] = _window_table(features, truth, scored, client.classes)
    return result


async def _run_replay(dataset_id: str, combo_ids: list[int], client,
                      experiment_ids: list[str] | None, ground_truth: str,
                      run: dict) -> dict:
    """Replay one vendored split through all five combinations."""
    spec = REPLAY_SETS[dataset_id]
    path = DATA_DIR / spec["file"]
    frame = pd.read_csv(path)
    if experiment_ids:
        frame = frame[frame["experiment_id"].isin(experiment_ids)]
        if frame.empty:
            raise ValueError("no experiments matched")

    timings = {}
    run["progress"] = {"stage": "scoring the trained arms", "done": 0, "total": 1}
    t0 = time.perf_counter()
    proba = await client.score(frame)
    timings["classify_ms"] = round((time.perf_counter() - t0) * 1000)

    dataset = {
        "id": dataset_id, "label": spec["label"], "kind": "replay",
        "synthetic": spec["synthetic"], "note": spec["note"],
        "sha256": _sha256_file(path),
    }
    run["progress"] = {"stage": "computing metrics", "done": 1, "total": 1}
    result = await asyncio.to_thread(
        _score_frame, frame, dataset, combo_ids, client, proba, ground_truth, timings)

    # The OOD split's label is "unknown", a class the model was never trained
    # to emit, so a fuel table there would score every prediction wrong for a
    # reason that has nothing to do with the model's fuel discrimination.
    if dataset_id == "ood_split":
        result.pop("fuel", None)
        result["fuel_note"] = (
            "Not scored: these fuels have no trained class. The binary table "
            "below is the meaningful one."
        )
    return result


def _window_table(features, truth, scored, classes) -> list[dict]:
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
        # Named from K.FULL_COMBO, because only the full system carries a fuel
        # verdict. Hardcoding the number here meant the exported columns kept
        # the name of an arm that no longer exists after the arms were renumbered.
        rows[f"combo{K.FULL_COMBO}_class"] = scored["fuel"]["predicted_class"].to_numpy()
        rows[f"combo{K.FULL_COMBO}_confidence"] = (
            scored["fuel"]["confidence"].to_numpy().round(6))
    return pd.DataFrame(rows).to_dict("records")


async def _run_recordings(dataset_id: str, combo_ids: list[int], client,
                          ground_truth: str, run: dict, yolo_url: str,
                          vlm_url: str) -> dict:
    """Score one recording folder, or every one of them with `rec/*`.

    The frame build is I/O bound -- one YOLO call per second of footage plus a
    VLM call per cooldown -- so it stays on the event loop, and only the pandas
    feature build is handed to a thread.
    """
    name = dataset_id.split("/", 1)[1]
    root = recordings.DATA_ROOT
    folders = ([p for p in sorted(root.iterdir()) if p.is_dir()] if name == "*"
               else [root / name])

    frames, metas = [], []
    for i, folder in enumerate(folders):
        if not folder.exists():
            raise KeyError(dataset_id)
        run["progress"] = {"stage": f"scoring {folder.name}",
                           "done": i, "total": len(folders)}

        def report(done, total, folder=folder, i=i):
            run["progress"] = {"stage": f"{folder.name}: {done}/{total}s",
                               "done": i, "total": len(folders)}

        frame, meta = await recordings.build_frame(folder, yolo_url, vlm_url,
                                                   progress=report)
        frames.append(frame)
        metas.append({"experiment_id": folder.name, **{
            k: v for k, v in meta.items() if k in
            ("label", "frame_rate_hz", "warnings", "vlm_invocations", "baseline")}})

    combined = pd.concat(frames, ignore_index=True)
    dataset = {
        "id": dataset_id, "kind": "recording",
        "label": f"{len(folders)} recording(s)", "synthetic": False,
        "note": "Your own recordings, scored through the real detectors.",
        "experiments": metas,
    }
    timings = {}
    run["progress"] = {"stage": "scoring the trained arms",
                       "done": len(folders), "total": len(folders)}
    t0 = time.perf_counter()
    proba = await client.score(combined)
    timings["classify_ms"] = round((time.perf_counter() - t0) * 1000)

    run["progress"] = {"stage": "computing metrics", "done": len(folders),
                       "total": len(folders)}
    return await asyncio.to_thread(_score_frame, combined, dataset, combo_ids,
                                   client, proba, ground_truth, timings)


async def submit(dataset_id: str, combo_ids: list[int], client,
                 experiment_ids: list[str] | None = None,
                 ground_truth: str = "strict",
                 yolo_url: str = "", vlm_url: str = "") -> str:
    is_recording = dataset_id.startswith("rec/")
    if not is_recording and dataset_id not in REPLAY_SETS:
        raise KeyError(dataset_id)
    run_id = f"run_{uuid.uuid4().hex[:10]}"
    RUNS[run_id] = {
        "run_id": run_id, "status": "queued", "dataset_id": dataset_id,
        "combos": combo_ids, "ground_truth": ground_truth,
        "started_at": _now(), "finished_at": None, "progress": None,
        "error": None, "result": None,
    }

    async def _go():
        run = RUNS[run_id]
        run["status"] = "running"
        try:
            if is_recording:
                result = await _run_recordings(dataset_id, combo_ids, client,
                                               ground_truth, run, yolo_url, vlm_url)
            else:
                result = await _run_replay(dataset_id, combo_ids, client,
                                           experiment_ids, ground_truth, run)
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
            # READ trainedOn, NOT data_source. _health_payload has only ever
            # built "trainedOn" (mirroring fire-classification-service, which
            # also names it that), so this line raised KeyError and the whole
            # export returned 500 -- taking out the one button that produces the
            # citable provenance file. The output key stays "data_source"
            # because that is what the exported document calls it; only the
            # lookup was wrong. Read defensively so a rename upstream degrades
            # to "unknown" instead of breaking the export again.
            "data_source": health.get("data_source")
                           or health.get("trainedOn")
                           or "unknown",
            "synthetic_warning": health.get("synthetic_warning"),
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
              "vs_full_event_delta", "vs_full_p_value"]
    writer = csv.DictWriter(buf, fieldnames=fields)
    writer.writeheader()
    for c, r in sorted(result["combos"].items()):
        w, e, lat = r["window"], r["event"], r["latency"]
        vs = r.get("vs_full", {})
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
            "vs_full_event_delta": vs.get("event_delta"),
            "vs_full_p_value": round(vs["p_value"], 6) if vs else None,
        })
    return buf.getvalue()
