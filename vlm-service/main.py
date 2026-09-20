import os
import json
import base64
import logging
import time
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


# ── Detailed prompt, for the ablation service ────────────────────────────────
# WHY A SECOND PROMPT RATHER THAN EXTENDING THE FIRST. The dashboard alarm
# depends on /describe-image/ returning exactly {description, detected, type};
# changing that shape would break the live alarm. The fusion model, meanwhile,
# needs eleven VLM channels, and asking one prompt to serve both would make
# every dashboard frame pay for detail the alarm never reads.
#
# WHY IT ASKS FOR OBSERVABLES, NOT LABELS. The model's VLM channels are things
# a camera can see -- how dark the smoke is, how blue or orange the flame is,
# how clear the view is -- not a verdict. Asking the VLM to name the fuel
# directly would hand it the fusion model's whole job and make combination 3
# indistinguishable from combination 6.
#
# WHY THE THREE SOURCE SCORES MUST NOT SUM TO 1. In the training generator the
# three are a softmax scaled by `evidence = max(flame, smoke)`; measured on the
# test split they sum to a median of 0.46, not 1.0. A VLM handing back three
# probabilities that sum to 1.0 would be out of distribution on the model's
# most-used feature family, so the prompt says so explicitly and the adapter in
# ablation-service rescales anyway.
DETAILED_PROMPT = """You are a fire-scene analyst. Look at this image and report what you can SEE.
Do not guess. If you cannot see something, report 0.

Respond ONLY with one JSON object, no markdown, no extra text:

{
  "flame_visible":      <0.0-1.0>,
  "smoke_visible":      <0.0-1.0>,
  "smoke_darkness":     <0.0-1.0>,
  "flame_colour_index": <0.0-1.0>,
  "source_gas":         <0.0-1.0>,
  "source_liquid":      <0.0-1.0>,
  "source_solid":       <0.0-1.0>,
  "view_quality":       <0.0-1.0>,
  "description":        "<one concise sentence about what you see>"
}

Field meanings:
- flame_visible: confidence that open flame is present.
- smoke_visible: confidence that smoke is present.
- smoke_darkness: 0 = white, pale or grey smoke; 1 = black sooty smoke. Report 0 if there is no smoke.
- flame_colour_index: 0.18 = blue flame, 0.62 = yellow flame, 0.88 = deep orange or red flame with
  soot. Report 0 if there is no flame.
- source_gas: burning gas — blue-tinged flame, little smoke, a jet or burner.
- source_liquid: burning liquid — a pool of flame, dark oily smoke.
- source_solid: burning wood, cloth or paper — pale smoke, embers, charring.
- view_quality: 1 = clear, bright, unobstructed view; 0 = dark, blurred or blocked.

The three source_ values are independent judgements, not a probability distribution.
They do NOT need to sum to 1. Score each one on its own evidence.

Important: a bright light, camera flash, torch, LED, sun or phone screen is NOT fire.
Only report flame_visible above 0 for actual combustion."""

# The eight numeric channels the detailed endpoint promises. Kept as a tuple so
# the clamp below and the zero-filled failure response cannot drift apart.
DETAIL_FIELDS = (
    "flame_visible", "smoke_visible", "smoke_darkness", "flame_colour_index",
    "source_gas", "source_liquid", "source_solid", "view_quality",
)


def _image_message(prompt: str, image_bytes: bytes) -> HumanMessage:
    image_b64 = base64.b64encode(image_bytes).decode("utf-8")
    return HumanMessage(content=[
        {"type": "text", "text": prompt},
        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
    ])


def _strip_fences(raw: str) -> str:
    """Drop markdown code fences the model sometimes adds despite the prompt."""
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    return raw


def _clamp01(value) -> float:
    """Coerce to a float in [0, 1].

    A VLM occasionally answers 1.3, or "0.4", or null. Any of those reaching
    the fusion model would be a value its StandardScaler never saw, so the
    boundary is enforced here rather than trusted upstream.
    """
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


@app.get("/health")
def health():
    return {"status": "ok", "model": "gemini-2.5-flash"}


@app.post("/describe-image/")
async def describe_image(file: UploadFile = File(...)):
    try:
        image_bytes = await file.read()
        response = llm.invoke([_image_message(FIRE_PROMPT, image_bytes)])
        parsed = json.loads(_strip_fences(response.content))

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


@app.post("/describe-image-detailed/")
async def describe_image_detailed(file: UploadFile = File(...)):
    """The eleven-channel view the ablation service's fusion model needs.

    Returns the eight numeric observables clamped to [0, 1], plus `parsed` so
    the caller can tell a real all-zero reading ("looked, saw nothing") from a
    parse failure. Like /describe-image/, unparseable output is 200 with
    everything zeroed rather than an error: an unreadable answer must never be
    able to raise an alarm, and on this path it must also never inject a
    fabricated feature vector into a research result.
    """
    started = time.perf_counter()
    zeros = {name: 0.0 for name in DETAIL_FIELDS}

    try:
        image_bytes = await file.read()
        response = llm.invoke([_image_message(DETAILED_PROMPT, image_bytes)])
        parsed = json.loads(_strip_fences(response.content))

        result = {name: _clamp01(parsed.get(name)) for name in DETAIL_FIELDS}
        logger.info(
            "VLM detailed: flame=%.2f smoke=%.2f view=%.2f",
            result["flame_visible"], result["smoke_visible"], result["view_quality"],
        )
        return {
            **result,
            "description": parsed.get("description") or "",
            "parsed": True,
            "latency_ms": round((time.perf_counter() - started) * 1000),
        }

    except json.JSONDecodeError as e:
        logger.warning("VLM detailed returned non-JSON: %s | error: %s",
                       response.content[:200], e)
        return {**zeros, "description": "", "parsed": False,
                "latency_ms": round((time.perf_counter() - started) * 1000)}

    except Exception:
        logger.exception("VLM detailed inference failed")
        raise HTTPException(status_code=500, detail="VLM inference failed")