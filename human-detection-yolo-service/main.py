"""
FireWatch AI – human detection service

YOLO11s trained on CrowdHuman (single class, "person") for occupancy counting.
Runs beside the fire detector rather than inside it: the two models score the
same frame concurrently, so wall-clock cost is max(fire, human) instead of the
sum, and a crash in either one cannot take the other down. The fire detector
drives the alarm, so it must never wait on this service.

THE CONFIDENCE FILTER LIVES HERE, NOT IN THE BROWSER. The fire service returns
every box and lets the dashboard threshold them, which is fine when the output
is a set of badges. Here the output is a *count* that feeds the incident muster
in alert-service, so the threshold has to live in one place or the dashboard and
the evacuation app would disagree about how many people are in the room. Same
reasoning esp32-sensor-service gives for grading readings server-side.

WHY THE COUNT IS SMOOTHED DOWNSTREAM, NOT HERE. This endpoint reports what it
sees in one frame. CrowdHuman scenes are densely occluded and a raw per-frame
count flickers by a person or two; the dashboard runs a rolling median over
that. Keeping this service memoryless means it stays stateless and can be
scaled or restarted without losing a count.
"""

import os

import cv2
import numpy as np
from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from ultralytics import YOLO

# Counting is noticeably more threshold-sensitive than alarming: every box that
# survives is +1 person. 0.40 sits above the fire detector's 0.35 because a
# false person inflates an evacuation head-count, whereas a false smoke box
# only ever asks the VLM for a second opinion.
MIN_CONF = float(os.getenv("HUMAN_MIN_CONF", "0.40"))
# CrowdHuman labels heavily overlapping people, so boxes genuinely do overlap.
# The Ultralytics default of 0.7 already suits that; exposed for tuning.
IOU = float(os.getenv("HUMAN_IOU", "0.7"))
# The model was trained at 640; inferring at another size costs accuracy for
# no real speed win on CPU.
IMGSZ = int(os.getenv("HUMAN_IMGSZ", "640"))

app = FastAPI(title="YOLO Human Detection Service")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

model = YOLO("best.pt")
print(f"[HUMAN] Model loaded. Classes: {model.names} (conf>={MIN_CONF}, imgsz={IMGSZ})")


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "human-detection-yolo-service",
        "classes": model.names,
        "minConfidence": MIN_CONF,
        "imgsz": IMGSZ,
    }


@app.post("/detect")
async def detect(file: UploadFile = File(...)):
    contents = await file.read()
    np_arr = np.frombuffer(contents, np.uint8)
    frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

    if frame is None:
        return JSONResponse(
            content={"detections": [], "count": 0, "error": "Could not decode image"},
            status_code=400,
        )

    results = model(frame, conf=MIN_CONF, iou=IOU, imgsz=IMGSZ, verbose=False)[0]

    detections = []
    for box in results.boxes:
        x1, y1, x2, y2 = box.xyxy[0].tolist()
        detections.append({
            "label": model.names[int(box.cls[0])],
            "confidence": float(box.conf[0]),
            "box": [x1, y1, x2, y2],
        })

    # Boxes are in native frame pixels, exactly like the fire service — the
    # dashboard applies one object-fit:cover transform to both overlays.
    return JSONResponse(content={
        "detections": detections,
        "count": len(detections),
        "minConfidence": MIN_CONF,
    })
