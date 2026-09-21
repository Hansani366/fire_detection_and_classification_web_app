"""
Your own recorded experiments: frames + sensor log -> the 27 model channels.

WHY THIS IS THE RESULT THAT MATTERS. Replaying the CFAST split answers "which
combination of these signals works best?" but every signal in it came from the
same generator the models were fitted to, so a win there is partly the model
recognising its own simulator. Here the real YOLO looks at real pixels and the
real VLM describes a real scene. The replay tab is the sanity check; this is
the evidence.

THE 1 Hz GRID IS THE CONTRACT. Frames arrive at camera rate, sensors at node
rate, and the models want exactly one row per second. Each slot takes the LAST
frame inside it, not the first: the rolling features are causal and anchored at
the end of their window, so the frame that best represents second 41 is the one
taken at 41.9s, not 41.0s.

THE VLM RUNS ON THE SAME CASCADE THE TRAINING DATA ENCODES. Gated on a YOLO
detection, at most once per cooldown, verdict held in between. Running it on
every frame would be both ruinously slow and out of distribution -- the model
has never seen `vlm_staleness_s` pinned at 0 for a whole experiment.
"""

from __future__ import annotations

import asyncio
import csv
import json
import logging
from pathlib import Path

import httpx
import numpy as np
import pandas as pd

import constants as K
import flicker
import vision
from sensor_adapter import SensorAdapter, SensorGapError
from vlm_adapter import VlmHold

log = logging.getLogger("ablation.recordings")

DATA_ROOT = Path("/data")
VALID_LABELS = {"no_fire", "gas_fire", "liquid_fuel", "solid_combustible"}


def _read_meta(folder: Path) -> dict:
    meta = json.loads((folder / "meta.json").read_text())
    label = meta.get("label")
    if label not in VALID_LABELS:
        raise ValueError(
            f"{folder.name}/meta.json: label must be one of {sorted(VALID_LABELS)}, "
            f"got {label!r}")
    if label != "no_fire" and meta.get("ignition_offset_s") is None:
        raise ValueError(
            f"{folder.name}/meta.json: a fire run needs ignition_offset_s. Without "
            f"it, windows before the fire started would count as positives and "
            f"detection latency would be meaningless.")
    meta.setdefault("frame_rate_hz", 0.0)
    meta.setdefault("baseline_seconds", K.BASELINE_S)
    return meta


def _read_sensors(folder: Path) -> list[tuple[float, dict]]:
    """sensors.csv -> [(seconds since start, reading dict)], time-ordered."""
    path = folder / "sensors.csv"
    if not path.exists():
        return []
    rows: list[tuple[pd.Timestamp, dict]] = []
    with path.open(newline="") as fh:
        for row in csv.DictReader(fh):
            stamp = pd.to_datetime(row.get("t_iso") or row.get("t"), utc=True,
                                   errors="coerce")
            if pd.isna(stamp):
                continue
            reading = {}
            for key in ("mq2_ppm", "mq2_raw", "mq7_ppm", "mq7_raw", "flame",
                        "flame_raw", "temperature_c", "humidity_pct"):
                value = row.get(key)
                if value not in (None, ""):
                    reading[key] = float(value)
            rows.append((stamp, reading))
    if not rows:
        return []
    rows.sort(key=lambda r: r[0])
    t0 = rows[0][0]
    return [((s - t0).total_seconds(), r) for s, r in rows]


def list_recordings(root: Path = DATA_ROOT) -> list[dict]:
    out = []
    if not root.exists():
        return out
    for folder in sorted(p for p in root.iterdir() if p.is_dir()):
        frames = sorted((folder / "frames").glob("*.jpg")) if (folder / "frames").exists() else []
        entry = {"id": f"rec/{folder.name}", "kind": "recording",
                 "label_name": folder.name, "frames": len(frames),
                 "synthetic": False, "warnings": []}
        try:
            meta = _read_meta(folder)
            entry.update({
                "label": meta["label"],
                "frame_rate_hz": meta["frame_rate_hz"],
                "duration_s": round(len(frames) / meta["frame_rate_hz"], 1)
                if meta["frame_rate_hz"] else None,
                "ignition_offset_s": meta.get("ignition_offset_s"),
                "sensors": (folder / "sensors.csv").exists(),
            })
            if not frames:
                entry["warnings"].append("no frames found under frames/")
            if not flicker.usable(meta["frame_rate_hz"]):
                entry["warnings"].append(
                    f"frame_rate_hz {meta['frame_rate_hz']} is below "
                    f"{K.FLICKER_MIN_SOURCE_HZ}; flicker will be reported as "
                    f"unavailable rather than estimated, because at this rate a "
                    f"real 2 Hz flame aliases down to look like no flame at all")
            if not entry["sensors"]:
                entry["warnings"].append(
                    "no sensors.csv; combinations 1, 4 and 6 will not be meaningful")
        except Exception as exc:                                  # noqa: BLE001
            entry["error"] = str(exc)
        out.append(entry)
    return out


async def build_frame(folder: Path, yolo_url: str, vlm_url: str,
                      progress=None) -> tuple[pd.DataFrame, dict]:
    """One recording -> a DataFrame of 1 Hz rows ready for build_features()."""
    from PIL import Image

    meta = _read_meta(folder)
    rate = float(meta["frame_rate_hz"])
    frames = sorted((folder / "frames").glob("*.jpg"))
    if not frames:
        raise ValueError(f"{folder.name}: no frames under frames/")
    if rate <= 0:
        raise ValueError(f"{folder.name}: frame_rate_hz must be positive")

    sensors = _read_sensors(folder)
    adapter = SensorAdapter(
        baseline_mode="manual" if meta.get("mq2_baseline") is not None else "quiet_prefix",
        mq2_baseline=meta.get("mq2_baseline"),
        mq7_baseline=meta.get("mq7_baseline"),
        flame_dark=meta.get("flame_dark_counts", K.FLAME_DARK_COUNTS),
        flame_bright=meta.get("flame_bright_counts", K.FLAME_BRIGHT_COUNTS),
        baseline_s=float(meta.get("baseline_seconds", K.BASELINE_S)),
    )
    hold = VlmHold()
    flicker_ok = flicker.usable(rate)

    # Group frames into 1 s slots by their index, then keep the last of each.
    last_in_slot: dict[int, int] = {}
    for idx in range(len(frames)):
        last_in_slot[int(idx / rate)] = idx
    duration = max(last_in_slot) + 1

    # How many frames of history the flicker window spans at this rate.
    flicker_span = int(K.FLICKER_WINDOW_N * rate / K.FLICKER_SAMPLE_HZ) or 1

    rows: list[dict] = []
    luma: list[float] = []
    sensor_cursor = 0
    warnings: list[str] = []

    async with httpx.AsyncClient(timeout=60.0) as client:
        for slot in range(duration):
            # feed every sensor sample whose timestamp has arrived
            while sensor_cursor < len(sensors) and sensors[sensor_cursor][0] <= slot:
                adapter.observe(*sensors[sensor_cursor])
                sensor_cursor += 1

            frame_idx = last_in_slot.get(slot)
            if frame_idx is None:
                continue
            path = frames[frame_idx]
            image_bytes = path.read_bytes()

            resp = await client.post(
                yolo_url, files={"file": (path.name, image_bytes, "image/jpeg")})
            resp.raise_for_status()
            detections = resp.json().get("detections", [])

            with Image.open(path) as img:
                width, height = img.size
                fire_boxes = [d["box"] for d in detections
                              if str(d.get("label", "")).lower() == "fire"
                              and float(d.get("confidence", 0)) >= K.YOLO_DETECT_THRESHOLD]
                if flicker_ok:
                    value = flicker.luminance(img, fire_boxes)
                    # A box blinking out for one frame should not restart the
                    # window; a sustained absence should.
                    luma.append(value if value is not None else
                                (luma[-1] if luma else 0.0))
                    if value is None and len(luma) > 2 and all(
                            abs(luma[-1] - v) < 1e-9 for v in luma[-3:]):
                        luma.clear()

            hz = (flicker.estimate(np.array(luma[-flicker_span:]))
                  if flicker_ok and len(luma) >= flicker_span else K.FLICKER_QUIET_HZ)
            vis = vision.channels(detections, width, height, hz)

            # ── the cascade, exactly as the training data encodes it ──
            invoked = False
            if hold.due(gated=bool(vis["yolo_detected"])):
                try:
                    vlm_resp = await client.post(
                        vlm_url, files={"file": (path.name, image_bytes, "image/jpeg")})
                    vlm_resp.raise_for_status()
                    hold.observe(vlm_resp.json())
                    invoked = True
                except Exception as exc:                          # noqa: BLE001
                    log.warning("%s slot %d: VLM failed: %s", folder.name, slot, exc)
                    hold.failed()

            try:
                sensor_channels = adapter.channels(float(slot))
            except SensorGapError as exc:
                warnings.append(f"stopped at {slot}s: {exc}")
                break
            hold.tick()
            if sensor_channels is None:
                continue                       # still measuring the baseline

            rows.append({
                "experiment_id": folder.name,
                "timestamp": pd.Timestamp("2000-01-01") + pd.Timedelta(seconds=slot),
                **vis,
                **hold.channels(invoked_this_window=invoked),
                **sensor_channels,
                "fire_type": meta["label"],
                "ignition_offset_s": meta.get("ignition_offset_s"),
            })
            if progress:
                progress(slot + 1, duration)

    if not rows:
        raise ValueError(
            f"{folder.name}: produced no scored windows. The most common cause is "
            f"a recording shorter than the {adapter.baseline_s:.0f}s clean-air "
            f"baseline.")

    if not flicker_ok:
        warnings.append(
            f"flicker unavailable: frame_rate_hz {rate} is below "
            f"{K.FLICKER_MIN_SOURCE_HZ}")
    if hold.errors:
        warnings.append(f"{hold.errors} VLM calls failed; the last good verdict "
                        f"was held across them")
    if adapter.flame_disagreements:
        warnings.append(
            f"{adapter.flame_disagreements} windows where the flame sensor's "
            f"digital pin and its analog reading disagreed — check "
            f"flame_bright_counts for this node")

    meta["warnings"] = warnings
    meta["vlm_invocations"] = hold.invocations
    meta["baseline"] = adapter.status(float(duration))
    return pd.DataFrame(rows), meta
