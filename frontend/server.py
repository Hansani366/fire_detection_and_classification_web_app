"""
FireWatch AI – FastAPI backend
Serves the static frontend and proxies frames to YOLO + VLM services.
"""

import os
import httpx
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

YOLO_URL   = os.getenv("YOLO_URL",   "http://yolo-service:8000/detect")
GEMINI_URL = os.getenv("GEMINI_URL", "http://vlm-service:8019/describe-image/")
TIMEOUT    = float(os.getenv("PROXY_TIMEOUT", "15"))

app = FastAPI(title="FireWatch AI")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Proxy endpoints ──────────────────────────────────────────────────────────

@app.post("/api/detect")
async def proxy_detect(file: UploadFile = File(...)):
    """Forward a JPEG frame to the YOLO service and return its JSON."""
    data = await file.read()
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.post(
                YOLO_URL,
                files={"file": ("frame.jpg", data, "image/jpeg")},
            )
        return JSONResponse(content=resp.json(), status_code=resp.status_code)
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"YOLO service unreachable: {exc}")


@app.post("/api/describe")
async def proxy_describe(file: UploadFile = File(...)):
    """Forward a JPEG frame to the VLM service and return its JSON."""
    data = await file.read()
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.post(
                GEMINI_URL,
                files={"file": ("frame.jpg", data, "image/jpeg")},
            )
        return JSONResponse(content=resp.json(), status_code=resp.status_code)
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"VLM service unreachable: {exc}")


# ── Static files (index.html + assets) ──────────────────────────────────────

@app.get("/")
async def root():
    return FileResponse("static/index.html")

app.mount("/", StaticFiles(directory="static", html=True), name="static")