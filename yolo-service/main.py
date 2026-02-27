from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import numpy as np
import cv2
from ultralytics import YOLO

app = FastAPI(title="YOLO Fire & Smoke Detection Service")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Load model on startup
model = YOLO("best.pt")
print(f"[YOLO] Model loaded. Classes: {model.names}")


@app.get("/health")
async def health():
    return {"status": "ok", "classes": model.names}


@app.post("/detect")
async def detect(file: UploadFile = File(...)):
    contents = await file.read()
    np_arr = np.frombuffer(contents, np.uint8)
    frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

    if frame is None:
        return JSONResponse(content={"detections": [], "error": "Could not decode image"}, status_code=400)

    results = model(frame)[0]

    detections = []
    for box in results.boxes:
        x1, y1, x2, y2 = box.xyxy[0].tolist()
        conf = float(box.conf[0])
        cls  = int(box.cls[0])
        label = model.names[cls]
        detections.append({"label": label, "confidence": conf, "box": [x1, y1, x2, y2]})

    return JSONResponse(content={"detections": detections})