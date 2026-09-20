"""
FireWatch AI – ESP32-CAM bridge

Proxies an ESP32-CAM's MJPEG stream and stills so the dashboard can reach them
same-origin. The dashboard is HTTPS-only, so the browser cannot load
http://<board-ip>/stream directly (mixed content), and even if it could, a
cross-origin <img> would taint the capture canvas and make offscreen.toBlob()
throw — which would kill detection entirely.

nginx cannot do this on its own: it has no resolver and every proxy_pass is a
literal service name, so an upstream built from a user-supplied IP would fail at
startup. Hence the address handling — and its SSRF guard — lives here.

THE BOARD SERVES ONE REQUEST AT A TIME. The sketch starts a single
esp_http_server on port 80 and its /stream handler is an infinite loop, so while
a stream is open the board cannot answer / or /still at all. That shapes this
whole module: liveness is reported from bytes we have actually relayed rather
than by probing the board, /still refuses while a stream is running, and a new
stream tears down the previous one so an abandoned connection cannot wedge the
board.
"""

import asyncio
import ipaddress
import logging
import os
import socket
import time
from urllib.parse import urlsplit

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse

DEFAULT_CAM_URL = os.getenv("ESP32_CAM_URL", "").strip()
CONNECT_TIMEOUT = float(os.getenv("ESP32_CONNECT_TIMEOUT", "3"))
STILL_TIMEOUT = float(os.getenv("ESP32_STILL_TIMEOUT", "5"))
# Health is polled on a timer, so its probe must always finish well inside the
# poll interval — a wedged board must not let polls pile up on each other.
PROBE_TIMEOUT = float(os.getenv("ESP32_PROBE_TIMEOUT", "2"))
# Bounded on purpose: it turns a silently stalled board into a clean disconnect
# the dashboard can see. Set to 0 to wait forever.
STREAM_READ_TIMEOUT = float(os.getenv("ESP32_STREAM_READ_TIMEOUT", "10"))
# No relayed bytes for this long while streaming => the feed is frozen.
STALE_AFTER_MS = int(os.getenv("ESP32_STALE_AFTER_MS", "3000"))

# Matches PART_BOUNDARY in the sketch; only used if the board omits the header.
FALLBACK_STREAM_TYPE = "multipart/x-mixed-replace;boundary=frameboundary"

PRIVATE_NETS = [
    ipaddress.ip_network(n)
    for n in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "169.254.0.0/16", "127.0.0.0/8")
]
# Inside 169.254/16, but cloud metadata rather than anything on a LAN.
BLOCKED_ADDRS = {
    ipaddress.ip_address("169.254.169.254"),
    ipaddress.ip_address("169.254.170.2"),
}

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("esp32-cam-service")

app = FastAPI(title="FireWatch ESP32-CAM Bridge")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)

# In-process singletons — this service MUST stay single-worker. /api/esp32/health
# answers from `last_byte_at`, and the single-flight teardown needs one registry.
STATE = {
    "token": 0,           # monotonic; newest stream wins
    "active": None,       # {"token", "origin", "resp", "client"} of the live stream
    "last_byte_at": 0.0,  # time.monotonic() of the last relayed chunk
    "bytes_relayed": 0,
}


# ── Address resolution ───────────────────────────────────────────────────────

class AddressError(Exception):
    """A camera address that is missing ("unconfigured") or rejected ("invalid")."""

    def __init__(self, kind: str, detail: str):
        self.kind = kind
        self.detail = detail
        super().__init__(detail)


def _check_addr(addr: ipaddress._BaseAddress, label: str) -> None:
    if addr in BLOCKED_ADDRS:
        raise AddressError("invalid", f"'{label}' is a reserved metadata address")
    if not any(addr in net for net in PRIVATE_NETS):
        raise AddressError("invalid", f"'{label}' is not a local network address")


def resolve_base(host: str | None) -> str:
    """Normalise a camera address to `http://<ip>[:port]`.

    The dashboard lets the user type an address, so this doubles as the SSRF
    guard. A user-supplied ?host= must be a literal IPv4 address: the board is
    on DHCP with a numeric IP anyway, and refusing names removes DNS rebinding
    and stops `?host=alert-service` reaching another container (Docker service
    names resolve into 172.16/12 and would otherwise pass the range check).
    Only ESP32_CAM_URL — trusted operator input — may be a hostname.
    """
    raw = (host or "").strip()
    trusted = False
    if not raw:
        raw, trusted = DEFAULT_CAM_URL, True
    if not raw:
        raise AddressError(
            "unconfigured",
            "No ESP32-CAM address configured. Set ESP32_CAM_URL or pass ?host=",
        )

    if "//" not in raw:
        raw = "http://" + raw
    parts = urlsplit(raw)

    if parts.scheme != "http":
        raise AddressError("invalid", f"Only plain http is supported, got '{parts.scheme}'")
    if parts.username or parts.password:
        raise AddressError("invalid", "Credentials are not allowed in the ESP32-CAM address")
    if parts.path not in ("", "/") or parts.query or parts.fragment:
        raise AddressError("invalid", "Give the board's address only, with no path")

    try:
        hostname, port = parts.hostname, parts.port or 80
    except ValueError:
        raise AddressError("invalid", f"'{raw}' has an invalid port")
    if not hostname:
        raise AddressError("invalid", f"Could not read a host out of '{raw}'")

    if trusted:
        try:
            infos = socket.getaddrinfo(hostname, port, socket.AF_INET, socket.SOCK_STREAM)
        except socket.gaierror as exc:
            raise AddressError("invalid", f"Could not resolve '{hostname}': {exc}")
        if not infos:
            raise AddressError("invalid", f"Could not resolve '{hostname}'")
        addrs = [ipaddress.ip_address(i[4][0]) for i in infos]
        for addr in addrs:
            _check_addr(addr, hostname)
        resolved = addrs[0]
    else:
        try:
            resolved = ipaddress.IPv4Address(hostname)
        except ipaddress.AddressValueError:
            raise AddressError(
                "invalid",
                f"'{hostname}' is not an IPv4 address — enter the board's IP, e.g. 192.168.1.50",
            )
        _check_addr(resolved, hostname)

    # Connect to the validated literal, never back to the name.
    return f"http://{resolved}:{port}"


def _base_or_error(host: str | None) -> str:
    try:
        return resolve_base(host)
    except AddressError as exc:
        raise HTTPException(
            status_code=503 if exc.kind == "unconfigured" else 400, detail=exc.detail
        )


# ── Stream registry ──────────────────────────────────────────────────────────

async def _drop_active() -> None:
    """Tear down the live stream, if any.

    The board cannot accept a second connection while one is open, and an
    abandoned one (tab closed, page reloaded) would wedge it until its own TCP
    timeout. So a new stream explicitly closes the old one first.
    """
    active = STATE.get("active")
    if not active:
        return
    STATE["active"] = None
    log.info("[esp32] dropping stream %s", active["token"])
    for closer in (active["resp"].aclose(), active["client"].aclose()):
        try:
            await closer
        except Exception:  # already torn down by its own generator
            pass


def _stream_age_ms() -> float:
    return (time.monotonic() - STATE["last_byte_at"]) * 1000


# ── Routes ───────────────────────────────────────────────────────────────────
# These carry the full /api/esp32/ prefix because nginx forwards the original
# URI unchanged (its proxy_pass has no URI part).

@app.get("/api/esp32/stream")
async def stream(host: str | None = Query(None)):
    """Pass the board's endless MJPEG response straight through to the browser."""
    origin = _base_or_error(host)
    await _drop_active()

    read_timeout = STREAM_READ_TIMEOUT or None
    client = httpx.AsyncClient(
        timeout=httpx.Timeout(read_timeout, connect=CONNECT_TIMEOUT),
        follow_redirects=False,
    )
    request = client.build_request(
        "GET", f"{origin}/stream", headers={"Accept-Encoding": "identity"}
    )

    # Everything that could fail must fail before the StreamingResponse exists:
    # once it starts, the status code is locked in.
    try:
        resp = await client.send(request, stream=True)
    except httpx.ConnectTimeout:
        await client.aclose()
        raise HTTPException(status_code=504, detail=f"ESP32-CAM timed out at {origin}")
    except httpx.RequestError as exc:
        await client.aclose()
        raise HTTPException(status_code=502, detail=f"ESP32-CAM unreachable at {origin}: {exc}")

    async def reject(detail: str, code: int = 502):
        await resp.aclose()
        await client.aclose()
        raise HTTPException(status_code=code, detail=detail)

    if resp.status_code != 200:
        await reject(f"ESP32-CAM returned HTTP {resp.status_code}")
    ctype = resp.headers.get("content-type", FALLBACK_STREAM_TYPE)
    if "multipart/x-mixed-replace" not in ctype:
        await reject(f"ESP32-CAM did not return a stream (content-type {ctype!r})")

    STATE["token"] += 1
    token = STATE["token"]
    STATE["active"] = {"token": token, "origin": origin, "resp": resp, "client": client}
    STATE["last_byte_at"] = time.monotonic()
    log.info("[esp32] stream %d open (%s)", token, origin)

    async def relay():
        # aiter_raw with no chunk_size: yield each network read as it arrives.
        # aiter_bytes would content-decode, and a chunk_size would buffer.
        try:
            async for chunk in resp.aiter_raw():
                active = STATE.get("active")
                if not active or active["token"] != token:
                    break  # a newer stream took over
                STATE["last_byte_at"] = time.monotonic()
                STATE["bytes_relayed"] += len(chunk)
                yield chunk
        except asyncio.CancelledError:
            raise  # browser disconnected — let uvicorn unwind normally
        except (httpx.HTTPError, OSError) as exc:
            log.warning("[esp32] stream %d ended: %s", token, exc or type(exc).__name__)
        finally:
            active = STATE.get("active")
            if active and active["token"] == token:
                STATE["active"] = None
            # Also runs on browser disconnect, so the board's socket is released.
            for closer in (resp.aclose(), client.aclose()):
                try:
                    await closer
                except Exception:
                    pass
            log.info("[esp32] stream %d closed", token)

    return StreamingResponse(
        relay(),
        media_type=ctype,  # keeps ;boundary=... — the browser cannot demux without it
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


@app.get("/api/esp32/still")
async def still(host: str | None = Query(None)):
    """A single JPEG. A debugging handle; the detection loop never calls this."""
    origin = _base_or_error(host)

    active = STATE.get("active")
    if active and active["origin"] == origin:
        raise HTTPException(
            status_code=409,
            detail="The board serves one request at a time; stop the stream first.",
        )

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(STILL_TIMEOUT, connect=CONNECT_TIMEOUT),
            follow_redirects=False,
        ) as client:
            resp = await client.get(f"{origin}/still")
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"ESP32-CAM unreachable at {origin}: {exc}")

    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail=f"ESP32-CAM returned HTTP {resp.status_code}")

    return Response(
        content=resp.content,
        media_type=resp.headers.get("content-type", "image/jpeg"),
        headers={"Cache-Control": "no-store"},
    )


async def report(host: str | None) -> dict:
    """Liveness for one board address.

    While we are relaying, this answers purely from the bytes we have passed on
    — the board could not reply to a probe anyway, and relayed bytes are a
    better signal than a reachable socket: they go stale the moment the picture
    freezes. Only when nothing is streaming do we actually probe the board.
    """
    try:
        origin = resolve_base(host)
    except AddressError as exc:
        return {"status": exc.kind, "host": None, "lastFrameAgeMs": None, "detail": exc.detail}

    active = STATE.get("active")
    if active and active["origin"] == origin:
        age = _stream_age_ms()
        fresh = age < STALE_AFTER_MS
        return {
            "status": "ok" if fresh else "stale",
            "host": origin,
            "lastFrameAgeMs": round(age),
            "detail": "" if fresh else f"No frames for {round(age)}ms",
        }

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(PROBE_TIMEOUT, connect=min(CONNECT_TIMEOUT, PROBE_TIMEOUT)),
            follow_redirects=False,
        ) as client:
            resp = await client.get(f"{origin}/still")
    except httpx.RequestError as exc:
        return {
            "status": "unreachable",
            "host": origin,
            "lastFrameAgeMs": None,
            "detail": str(exc) or exc.__class__.__name__,
        }

    ok = resp.status_code == 200
    return {
        "status": "ok" if ok else "unreachable",
        "host": origin,
        "lastFrameAgeMs": None,
        "detail": "" if ok else f"HTTP {resp.status_code}",
    }


@app.get("/api/esp32/health")
async def camera_health(host: str | None = Query(None)):
    """Always 200 so the dashboard can poll it without filling the console."""
    return JSONResponse(await report(host))


@app.get("/api/esp32/config")
async def config():
    """Lets the dashboard show the .env default as the address placeholder."""
    return {"defaultHost": DEFAULT_CAM_URL or None, "configured": bool(DEFAULT_CAM_URL)}


@app.get("/health")
async def health():
    """Container liveness. Deliberately never touches the board."""
    active = STATE.get("active")
    return {
        "status": "ok",
        "service": "esp32-cam-service",
        "defaultHost": DEFAULT_CAM_URL or None,
        "activeStreams": 1 if active else 0,
        "bytesRelayed": STATE["bytes_relayed"],
        "lastFrameAgeMs": round(_stream_age_ms()) if active else None,
    }


@app.on_event("startup")
async def _log_config():
    log.info("[esp32] default camera URL: %s", DEFAULT_CAM_URL or "(unset — dashboard must supply one)")
