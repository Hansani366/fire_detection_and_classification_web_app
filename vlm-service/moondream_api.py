from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
import subprocess
import shutil
import os
import base64
import json
import requests as http_requests

app = FastAPI(title="Moondream VLM Image Description API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

OLLAMA_URL = "http://localhost:11434"


@app.get("/health")
async def health():
    try:
        r = http_requests.get(f"{OLLAMA_URL}/api/tags", timeout=3)
        models = [m["name"] for m in r.json().get("models", [])]
        return {"status": "ok", "models": models}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


@app.post("/describe-image/")
async def describe_image(file: UploadFile = File(...)):
    # Save uploaded image
    tmp_path = f"/tmp/{file.filename or 'frame.jpg'}"
    with open(tmp_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    description = ""
    try:
        # Use Ollama REST API with image (multimodal)
        with open(tmp_path, "rb") as img_file:
            img_b64 = base64.b64encode(img_file.read()).decode("utf-8")

        payload = {
            "model": "moondream",
            "prompt": "Describe what you see in this image in detail. Focus on any fire, smoke, flames, or burning objects.",
            "images": [img_b64],
            "stream": False
        }
        resp = http_requests.post(f"{OLLAMA_URL}/api/generate", json=payload, timeout=30)
        if resp.status_code == 200:
            description = resp.json().get("response", "").strip()
        else:
            # Fallback: CLI
            result = subprocess.run(
                ["ollama", "run", "moondream", "Describe what you see. Focus on fire, smoke, or flames."],
                capture_output=True, text=True, timeout=30
            )
            description = result.stdout.strip()
    except Exception as e:
        description = f"[Error generating description: {str(e)}]"
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

    return {"description": description}