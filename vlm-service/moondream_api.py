import os
import base64
import logging
import requests as http_requests
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="FireWatch VLM Service")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Backend selection ─────────────────────────────────────────────────────────
VLM_BACKEND  = os.getenv("VLM_BACKEND", "gemini").lower()   # "gemini" | "moondream"
OLLAMA_URL   = os.getenv("OLLAMA_URL", "http://localhost:11434")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")

FIRE_PROMPT = (
    "Describe what you see in this image in detail. "
    "Focus especially on any fire, smoke, flames, burning objects, or signs of combustion."
)

logger.info(f"VLM backend: {VLM_BACKEND.upper()}")

# ── Gemini setup (only if needed) ────────────────────────────────────────────
gemini_llm = None
if VLM_BACKEND == "gemini":
    if not GOOGLE_API_KEY:
        raise RuntimeError("GOOGLE_API_KEY is not set but VLM_BACKEND=gemini")
    from langchain_google_genai import ChatGoogleGenerativeAI
    gemini_llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        api_key=GOOGLE_API_KEY,
    )
    logger.info("Gemini LLM initialised.")


# ── Health ────────────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    if VLM_BACKEND == "gemini":
        return {"status": "ok", "backend": "gemini", "model": "gemini-2.5-flash"}
    # Moondream: check Ollama
    try:
        r = http_requests.get(f"{OLLAMA_URL}/api/tags", timeout=3)
        models = [m["name"] for m in r.json().get("models", [])]
        return {"status": "ok", "backend": "moondream", "models": models}
    except Exception as e:
        return {"status": "error", "backend": "moondream", "detail": str(e)}


# ── Main endpoint ─────────────────────────────────────────────────────────────
@app.post("/describe-image/")
async def describe_image(file: UploadFile = File(...)):
    image_bytes = await file.read()
    image_b64   = base64.b64encode(image_bytes).decode("utf-8")

    try:
        if VLM_BACKEND == "gemini":
            description = await _run_gemini(image_b64)
        else:
            description = await _run_moondream(image_b64)
    except Exception as e:
        logger.exception("VLM inference failed")
        raise HTTPException(status_code=500, detail=f"VLM error: {str(e)}")

    return {"description": description, "backend": VLM_BACKEND}


# ── Gemini backend ────────────────────────────────────────────────────────────
async def _run_gemini(image_b64: str) -> str:
    from langchain_core.messages import HumanMessage
    msg = HumanMessage(content=[
        {"type": "text", "text": FIRE_PROMPT},
        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
    ])
    response = gemini_llm.invoke([msg])
    return response.content.strip()


# ── Moondream backend ─────────────────────────────────────────────────────────
async def _run_moondream(image_b64: str) -> str:
    payload = {
        "model": "moondream",
        "prompt": FIRE_PROMPT,
        "images": [image_b64],
        "stream": False,
    }
    resp = http_requests.post(f"{OLLAMA_URL}/api/generate", json=payload, timeout=60)
    resp.raise_for_status()
    return resp.json().get("response", "").strip()