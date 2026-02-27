import os
import json
import base64
import logging
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage

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

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
if not GOOGLE_API_KEY:
    raise RuntimeError("GOOGLE_API_KEY is not set")

llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    api_key=GOOGLE_API_KEY,
)
logger.info("VLM LLM initialised.")

# Structured prompt — forces a JSON answer so the keyword check in app.py
# only ever fires on an explicit positive detection, never on incidental
# scene description language.
FIRE_PROMPT = """You are a fire and smoke detection assistant.

Carefully examine this image for any of the following:
- visible fire or flames (open flame, candle flame, burning material)
- smoke (any colour)
- burning or charred objects
- embers or glowing combustion

Respond ONLY with a single JSON object — no markdown, no extra text:

If fire/smoke IS detected:
{"detected": true, "type": "<one of: fire, smoke, both>", "description": "<one concise sentence about what you see>"}

If fire/smoke is NOT detected:
{"detected": false, "type": null, "description": null}

Important: a bright light, camera flash, torch, LED, or phone screen is NOT fire.
Only mark detected=true for actual combustion."""


@app.get("/health")
def health():
    return {"status": "ok", "model": "gemini-2.5-flash"}


@app.post("/describe-image/")
async def describe_image(file: UploadFile = File(...)):
    try:
        image_bytes = await file.read()
        image_b64 = base64.b64encode(image_bytes).decode("utf-8")

        msg = HumanMessage(content=[
            {"type": "text", "text": FIRE_PROMPT},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
        ])
        response = llm.invoke([msg])
        raw = response.content.strip()

        # Strip accidental markdown code fences if the model adds them
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()

        parsed = json.loads(raw)

        if parsed.get("detected"):
            # Only return fire-related keywords when detection is positive.
            # The description is a single sentence written by the model — it will
            # naturally contain words like "fire" or "smoke" only when appropriate.
            description = parsed["description"]
        else:
            # Explicitly return empty string so app.py keyword check always fails.
            description = ""

        logger.info("VLM result: detected=%s type=%s", parsed.get("detected"), parsed.get("type"))
        return {"description": description, "detected": parsed.get("detected"), "type": parsed.get("type")}

    except json.JSONDecodeError as e:
        # Model didn't return valid JSON — treat as no detection to avoid false alarms
        logger.warning("VLM returned non-JSON response: %s | error: %s", response.content[:200], e)
        return {"description": "", "detected": False, "type": None}

    except Exception:
        logger.exception("VLM inference failed")
        raise HTTPException(status_code=500, detail="VLM inference failed")