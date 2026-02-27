from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
import numpy as np
import cv2
from ultralytics import YOLO

app = FastAPI()

# Enable CORS for browser security
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Load the YOLO model
model = YOLO("best.pt")


# 1. This route serves the Web Interface
@app.get("/")
async def get_ui():
    return FileResponse("static/index.html")


# 2. This route handles the detection logic
@app.post("/detect")
async def detect(file: UploadFile = File(...)):
    contents = await file.read()
    np_arr = np.frombuffer(contents, np.uint8)
    frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

    results = model(frame)[0]

    detections = []
    for box in results.boxes:
        x1, y1, x2, y2 = box.xyxy[0].tolist()
        conf = float(box.conf[0])
        cls = int(box.cls[0])
        label = model.names[cls]

        detections.append({"label": label, "confidence": conf, "box": [x1, y1, x2, y2]})

    return JSONResponse(content={"detections": detections})
