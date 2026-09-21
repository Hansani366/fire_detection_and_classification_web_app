"""
FireWatch AI – FastAPI backend
Serves the static frontend and proxies frames to the detectors + VLM services.
"""

import asyncio
import logging
import os
import time

import httpx
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

FIRE_YOLO_URL  = os.getenv("FIRE_YOLO_URL",  "http://fire-detection-yolo-service:8000/detect")
HUMAN_YOLO_URL = os.getenv("HUMAN_YOLO_URL", "http://human-detection-yolo-service:8001/detect")
GEMINI_URL     = os.getenv("GEMINI_URL",     "http://vlm-service:8019/describe-image/")
VLM_WARN_URL   = os.getenv("VLM_WARN_URL",   "http://vlm-service:8019/warn-from-sensors/")
YOLO_TIMEOUT = float(os.getenv("YOLO_TIMEOUT",   "10"))   # YOLO is fast
VLM_TIMEOUT  = float(os.getenv("VLM_TIMEOUT",    "60"))   # Gemini can be slow
# Text-only, so far quicker than the vision call — and the caller falls back to
# a fixed sentence, so waiting a minute for prose would be the wrong trade.
WARN_TIMEOUT = float(os.getenv("WARN_TIMEOUT",   "15"))

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("frontend")

app = FastAPI(title="FireWatch AI")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Proxy endpoints ──────────────────────────────────────────────────────────

async def _score(client: httpx.AsyncClient, url: str, data: bytes) -> tuple[httpx.Response, float]:
    """POST one frame to a detector and report how long it took."""
    started = time.perf_counter()
    resp = await client.post(
        url,
        files={"file": ("frame.jpg", data, "image/jpeg")},
        timeout=YOLO_TIMEOUT,
    )
    return resp, (time.perf_counter() - started) * 1000


@app.post("/api/detect")
async def proxy_detect(file: UploadFile = File(...)):
    """Score one frame with both detectors and return their results together.

    THE FAN-OUT IS HERE RATHER THAN IN THE BROWSER because the two results are
    drawn as overlays on one video frame. Two independent browser calls would
    capture two *different* frames up to a detection interval apart, so the red
    and cyan boxes would describe slightly different moments. Doing it here also
    uploads the JPEG once instead of twice, and runs the models concurrently, so
    the round trip costs max(fire, human) rather than their sum.

    FIRE IS REQUIRED, HUMAN IS OPTIONAL. Fire detection drives the alarm, so its
    failures surface exactly as they did before this endpoint learned to count
    people. A human-service failure degrades to a null count and nothing else —
    it must never be able to break the alarm path.
    """
    data = await file.read()

    async with httpx.AsyncClient() as client:
        fire_result, human_result = await asyncio.gather(
            _score(client, FIRE_YOLO_URL, data),
            _score(client, HUMAN_YOLO_URL, data),
            return_exceptions=True,
        )

    # ── Fire: failures propagate ──
    if isinstance(fire_result, httpx.TimeoutException):
        raise HTTPException(status_code=504, detail="Fire detection service timed out")
    if isinstance(fire_result, BaseException):
        raise HTTPException(status_code=502, detail=f"Fire detection service unreachable: {fire_result}")

    fire_resp, fire_ms = fire_result
    if fire_resp.status_code != 200:
        return JSONResponse(content=fire_resp.json(), status_code=fire_resp.status_code)
    fire_json = fire_resp.json()

    # ── Human: failures degrade ──
    human_json: dict = {"detections": [], "count": None}
    human_ms = None
    if isinstance(human_result, BaseException):
        human_json["error"] = str(human_result) or type(human_result).__name__
        log.warning("Human detection unavailable: %s", human_json["error"])
    else:
        human_resp, human_ms = human_result
        if human_resp.status_code == 200:
            human_json = human_resp.json()
        else:
            human_json["error"] = f"HTTP {human_resp.status_code}"
            log.warning("Human detection returned %s", human_resp.status_code)

    return JSONResponse(content={
        "fire": fire_json,
        "human": human_json,
        "timings": {
            "fireMs": round(fire_ms),
            "humanMs": round(human_ms) if human_ms is not None else None,
        },
    })


@app.post("/api/describe")
async def proxy_describe(file: UploadFile = File(...)):
    """Forward a JPEG frame to the VLM/Gemini service and return its JSON.
    Uses a longer timeout since Gemini API calls can take 20-40s."""
    data = await file.read()
    try:
        async with httpx.AsyncClient(timeout=VLM_TIMEOUT) as client:
            resp = await client.post(
                GEMINI_URL,
                files={"file": ("frame.jpg", data, "image/jpeg")},
            )
        return JSONResponse(content=resp.json(), status_code=resp.status_code)
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="VLM service timed out")
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"VLM service unreachable: {exc}")


@app.post("/api/warn")
async def proxy_warn(body: dict):
    """Tier 1a: turn sensor readings into a plain-language warning.

    JSON in, JSON out — no image. Proxied here rather than called directly so
    the browser stays same-origin, exactly like /api/describe. A short timeout
    because this is a text-only call and the caller has a fallback: a warning
    that arrives late is worse than a blunt one that arrives now.
    """
    try:
        async with httpx.AsyncClient(timeout=WARN_TIMEOUT) as client:
            resp = await client.post(VLM_WARN_URL, json=body)
        return JSONResponse(content=resp.json(), status_code=resp.status_code)
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="VLM service timed out")
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"VLM service unreachable: {exc}")


# ── Static files (index.html + assets) ──────────────────────────────────────

@app.get("/")
async def root():
    return FileResponse("static/index.html")


# Declared explicitly, and above the mount, for the same reason "/" is: the
# StaticFiles mount below resolves a path to a file on disk, and there is no
# file called "ablation" -- only ablation.html -- so an extensionless /ablation
# would 404. The nav bar links here, so it has to resolve.
@app.get("/ablation")
async def ablation():
    return FileResponse("static/ablation.html")

@app.get("/reports")
async def reports():
    return FileResponse("static/reports.html")

app.mount("/", StaticFiles(directory="static", html=True), name="static")
