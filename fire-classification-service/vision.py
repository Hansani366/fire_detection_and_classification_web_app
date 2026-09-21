"""
YOLO boxes -> the six vision channels the models expect.

WHY UNION AREA AND NOT A SUM OF AREAS. `fire_area_ratio` is the fraction of
the frame that is on fire. Summing box areas double-counts every overlap, so
two boxes over one flame report twice the fire. NMS removes most same-class
overlap but not all of it, and the error is one-sided -- it can only ever
inflate the fire. On a channel the model reads directly, and whose running
maximum it also reads, a one-sided error is worth fifteen lines of coordinate
compression to avoid.

THE SERVICE OWNS THIS, NOT THE BROWSER. The dashboard draws boxes and thinks
in display pixels; the model thinks in frame fractions. Deriving the channels
here means the live path and the recordings path compute them identically,
from the same code, instead of agreeing by inspection.
"""

from __future__ import annotations

import constants as K

# The fire detector's two classes. Anything else it ever learns to emit is
# ignored rather than silently folded into one of these.
FIRE_LABELS = {"fire"}
SMOKE_LABELS = {"smoke"}


def _union_area(boxes: list[list[float]]) -> float:
    """Area covered by a set of axis-aligned boxes, counting overlap once.

    Coordinate compression: cut the plane at every box edge, then add up the
    cells that any box covers. O(n^3) in the number of boxes, which is nothing
    at the handful of boxes a frame produces.
    """
    if not boxes:
        return 0.0
    xs = sorted({c for b in boxes for c in (b[0], b[2])})
    ys = sorted({c for b in boxes for c in (b[1], b[3])})
    total = 0.0
    for i in range(len(xs) - 1):
        for j in range(len(ys) - 1):
            x0, x1, y0, y1 = xs[i], xs[i + 1], ys[j], ys[j + 1]
            if any(b[0] <= x0 and b[2] >= x1 and b[1] <= y0 and b[3] >= y1
                   for b in boxes):
                total += (x1 - x0) * (y1 - y0)
    return total


def channels(detections: list[dict], frame_w: int, frame_h: int,
             flicker_hz: float = K.FLICKER_QUIET_HZ) -> dict[str, float]:
    """Raw /detect output -> yolo_fire_conf, yolo_smoke_conf, areas, flicker, detected."""
    frame_area = float(max(1, frame_w) * max(1, frame_h))

    fire_conf = smoke_conf = 0.0
    fire_boxes: list[list[float]] = []
    smoke_boxes: list[list[float]] = []

    for det in detections or []:
        label = str(det.get("label", "")).lower()
        conf = float(det.get("confidence", 0.0))
        box = det.get("box")
        if label in FIRE_LABELS:
            fire_conf = max(fire_conf, conf)
            bucket = fire_boxes
        elif label in SMOKE_LABELS:
            smoke_conf = max(smoke_conf, conf)
            bucket = smoke_boxes
        else:
            continue
        # Only boxes that pass the shared gate contribute area. A 0.05-confidence
        # box is not evidence of area, and the generator's area channels track
        # what was actually detected.
        if box and conf >= K.YOLO_DETECT_THRESHOLD:
            bucket.append([float(v) for v in box])

    return {
        "yolo_fire_conf": fire_conf,
        "yolo_smoke_conf": smoke_conf,
        "fire_area_ratio": min(1.0, _union_area(fire_boxes) / frame_area),
        "smoke_area_ratio": min(1.0, _union_area(smoke_boxes) / frame_area),
        "flame_flicker_hz": max(0.0, min(K.FLICKER_MAX_HZ, float(flicker_hz))),
        # The generator's own `yolo_detected` column is exactly this gate, which
        # is the cross-check that 0.35 is the right number to use here.
        "yolo_detected": 1.0 if max(fire_conf, smoke_conf) > K.YOLO_DETECT_THRESHOLD
        else 0.0,
    }
