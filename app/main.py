"""
airdrop-linux — iPhone → Linux clipboard via local Wi-Fi.

Entry point: python -m app.main [options]
"""
from __future__ import annotations
import argparse
import ipaddress
import logging
import sys
import time
from collections import deque
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Deque

import io

import qrcode
import uvicorn
from fastapi import FastAPI, File, Header, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .auth import load_or_create_token, rotate_token, verify_token
from .clipboard import ClipboardError, copy_text_to_clipboard, copy_to_clipboard, session_type
from .images import ImageError, heif_available, to_clipboard_image, to_png_bytes
from .net import get_lan_ip, get_mdns_hostname, is_public_ip

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stderr,
)
log = logging.getLogger("airdrop")

# ---------------------------------------------------------------------------
# Simple in-memory rate limiter (sliding window per IP)
# ---------------------------------------------------------------------------
_RATE_WINDOW_SEC = 1.0
_RATE_MAX_REQUESTS = 3  # per window per IP

# Maps IP → deque of timestamps
_rate_buckets: dict[str, Deque[float]] = {}

# Recent diagnostic events to help troubleshoot upload/clipboard flow
_event_log: Deque[dict[str, Any]] = deque(maxlen=200)

def _check_rate_limit(ip: str) -> bool:
    """Return True if the request is allowed, False if rate-limited."""
    now = time.monotonic()
    window = _rate_buckets.setdefault(ip, deque())
    # Drop entries outside the window
    while window and now - window[0] > _RATE_WINDOW_SEC:
        window.popleft()
    if len(window) >= _RATE_MAX_REQUESTS:
        return False
    window.append(now)
    return True


def _record_event(stage: str, ok: bool, message: str, ip: str = "unknown", **extra: Any) -> None:
    event: dict[str, Any] = {
        "ts": int(time.time()),
        "stage": stage,
        "ok": ok,
        "message": message,
        "ip": ip,
    }
    if extra:
        event["extra"] = extra
    _event_log.append(event)
    level = logging.INFO if ok else logging.WARNING
    log.log(level, "[%s] %s | ip=%s | %s", stage, message, ip, extra if extra else "-")


class ClientLogEvent(BaseModel):
    event: str
    detail: str | None = None
    userAgent: str | None = None
    ts: int | None = None


class TextPayload(BaseModel):
    text: str


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

@asynccontextmanager
async def _lifespan(application: FastAPI):
    log.info("HEIC support: %s", "enabled" if heif_available() else "disabled (install pillow-heif)")
    try:
        st = session_type()
        log.info("Display session: %s", st)
    except Exception as exc:
        log.warning("Could not detect display session: %s", exc)
    yield


app = FastAPI(title="airdrop-linux", docs_url=None, redoc_url=None, lifespan=_lifespan)

_WEB_DIR = Path(__file__).parent.parent / "web"


# Serve the web/ directory as static files at root
# We mount AFTER defining routes so /upload takes precedence.


@app.post("/upload")
async def upload_photo(
    request: Request,
    photo: UploadFile = File(..., description="Photo captured on iPhone"),
    t: str | None = Query(default=None, description="Auth token (query param)"),
    x_token: str | None = Header(default=None, description="Auth token (header)"),
) -> JSONResponse:
    # --- Rate limit ---
    client_ip = request.client.host if request.client else "unknown"
    _record_event("upload_request", True, "upload request received", ip=client_ip)

    if not _check_rate_limit(client_ip):
        _record_event("rate_limit", False, "too many requests", ip=client_ip)
        raise HTTPException(status_code=429, detail="Too many requests")

    # --- Auth ---
    provided = t or x_token or ""
    if not provided or not verify_token(provided):
        _record_event("auth", False, "invalid or missing token", ip=client_ip)
        raise HTTPException(status_code=401, detail="Invalid or missing token")
    _record_event("auth", True, "token verified", ip=client_ip)

    # --- Read upload (hard cap via read with limit) ---
    from .images import MAX_UPLOAD_BYTES

    raw = await photo.read(MAX_UPLOAD_BYTES + 1)
    if len(raw) > MAX_UPLOAD_BYTES:
        _record_event("upload_read", False, "upload too large", ip=client_ip, size=len(raw))
        raise HTTPException(status_code=413, detail="Upload too large (max 25 MB)")

    content_type = photo.content_type or "unknown"
    _record_event(
        "photo_received",
        True,
        "photo bytes received",
        ip=client_ip,
        size=len(raw),
        content_type=content_type,
        filename=photo.filename,
    )

    # --- Convert (JPEG passthrough or encode to PNG) ---
    try:
        image_data, mime_type = to_clipboard_image(raw)
    except ImageError as exc:
        _record_event("image_convert", False, f"image conversion failed: {exc}", ip=client_ip)
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    _record_event("image_convert", True, f"image ready as {mime_type}", ip=client_ip, size=len(image_data))

    # Some Linux paste targets only accept image/png from clipboard providers.
    # Keep Windows fast-path JPEG handling, but force PNG on Wayland/X11.
    try:
        sess = session_type()
    except Exception:
        sess = "unknown"

    if mime_type == "image/jpeg" and sess in ("wayland", "x11"):
        image_data = to_png_bytes(raw)
        mime_type = "image/png"
        _record_event(
            "image_convert",
            True,
            "jpeg converted to png for Linux clipboard compatibility",
            ip=client_ip,
            session=sess,
            size=len(image_data),
        )

    # --- Copy to clipboard ---
    try:
        copy_to_clipboard(image_data, mime_type)
    except ClipboardError as exc:
        _record_event("clipboard", False, f"clipboard write failed: {exc}", ip=client_ip)
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    _record_event("clipboard", True, "image copied to clipboard", ip=client_ip)
    return JSONResponse({"status": "ok", "message": "Image copied to clipboard"})


@app.post("/upload-text")
async def upload_text(
    request: Request,
    payload: TextPayload,
    t: str | None = Query(default=None, description="Auth token (query param)"),
    x_token: str | None = Header(default=None, description="Auth token (header)"),
) -> JSONResponse:
    client_ip = request.client.host if request.client else "unknown"
    _record_event("text_request", True, "text upload request received", ip=client_ip)

    if not _check_rate_limit(client_ip):
        _record_event("rate_limit", False, "too many requests", ip=client_ip)
        raise HTTPException(status_code=429, detail="Too many requests")

    provided = t or x_token or ""
    if not provided or not verify_token(provided):
        _record_event("auth", False, "invalid or missing token", ip=client_ip)
        raise HTTPException(status_code=401, detail="Invalid or missing token")

    text = payload.text
    if not text or not text.strip():
        raise HTTPException(status_code=422, detail="Text must not be empty")
    if len(text.encode("utf-8")) > 256 * 1024:
        raise HTTPException(status_code=413, detail="Text too large (max 256 KB)")

    try:
        copy_text_to_clipboard(text)
    except ClipboardError as exc:
        _record_event("clipboard", False, f"text clipboard write failed: {exc}", ip=client_ip)
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    _record_event("clipboard", True, "text copied to clipboard", ip=client_ip, size=len(text))
    return JSONResponse({"status": "ok", "message": "Text copied to clipboard"})


@app.post("/client-log")
async def client_log(
    request: Request,
    payload: ClientLogEvent,
    t: str | None = Query(default=None, description="Auth token (query param)"),
    x_token: str | None = Header(default=None, description="Auth token (header)"),
) -> JSONResponse:
    client_ip = request.client.host if request.client else "unknown"
    provided = t or x_token or ""
    if not provided or not verify_token(provided):
        raise HTTPException(status_code=401, detail="Invalid or missing token")

    _record_event(
        "client",
        True,
        payload.event,
        ip=client_ip,
        detail=payload.detail,
        user_agent=payload.userAgent,
        client_ts=payload.ts,
    )
    return JSONResponse({"status": "ok"})


@app.get("/debug/events")
async def debug_events(
    request: Request,
    t: str | None = Query(default=None, description="Auth token"),
    limit: int = Query(default=50, ge=1, le=200),
) -> JSONResponse:
    client_ip = request.client.host if request.client else "unknown"
    provided = t or ""
    if not provided or not verify_token(provided):
        raise HTTPException(status_code=401, detail="Invalid or missing token")

    items = list(_event_log)[-limit:]
    photo_taken = any(item.get("stage") == "client" and item.get("message") == "photo_selected" for item in items)
    photo_received = any(item.get("stage") == "photo_received" and item.get("ok") for item in items)
    copied = any(item.get("stage") == "clipboard" and item.get("ok") for item in items)

    return JSONResponse(
        {
            "status": "ok",
            "ip": client_ip,
            "checks": {
                "photo_selected_on_phone": photo_taken,
                "photo_received_by_server": photo_received,
                "copied_to_clipboard": copied,
            },
            "events": items,
        }
    )


@app.get("/")
async def root(request: Request, t: str = "") -> Response:
    """Serve app shell, but first canonicalize host and tokenized URL."""
    token = load_or_create_token()
    canonical = _canonical_base_url(request)
    current = str(request.base_url).rstrip("/")
    if (not t) or (canonical != current):
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url=f"{canonical}/?t={token}", status_code=302)
    # Token present — fall through to static file serving (index.html)
    from starlette.responses import FileResponse
    return FileResponse(str(_WEB_DIR / "index.html"))


@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse({"status": "ok"})


def _make_qr_png(url: str) -> bytes:
    """Render *url* as a QR code and return PNG bytes."""
    qr = qrcode.QRCode(
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=8,
        border=4,
    )
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _build_app_url(request: Request) -> str:
    """Build the full authenticated URL from the canonical base URL + stored token."""
    token = load_or_create_token()
    base = _canonical_base_url(request)
    return f"{base}/?t={token}"


def _is_ip_host(host: str) -> bool:
    """Return True if *host* is an IP literal."""
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return False
    return True


def _canonical_base_url(request: Request) -> str:
    """Prefer mDNS hostname over raw IP host when possible for stable PWA installs."""
    scheme = request.url.scheme
    host = request.url.hostname or ""
    port = request.url.port

    mdns_host = get_mdns_hostname()
    if mdns_host and host and _is_ip_host(host):
        host = mdns_host

    default_port = 443 if scheme == "https" else 80
    if port is None or port == default_port:
        return f"{scheme}://{host}"
    return f"{scheme}://{host}:{port}"


@app.get("/qr.png")
async def qr_png(request: Request) -> Response:
    """Return the pairing QR code as a PNG image (no auth — token is in the URL)."""
    url = _build_app_url(request)
    return Response(content=_make_qr_png(url), media_type="image/png")


@app.get("/pair", response_class=HTMLResponse)
async def pair_page(request: Request) -> HTMLResponse:
    """Mobile-friendly pairing page — shows QR code and a tappable link.

    Requires no auth so the user can reach it just by typing the server IP.
    """
    url = _build_app_url(request)
    html = f"""\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"/>
  <meta name="theme-color" content="#111"/>
    <title>phoneToClipboard — Pair</title>
  <style>
    *,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
    body{{
      background:#111;color:#f5f5f7;
      font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
      min-height:100dvh;
      display:flex;flex-direction:column;align-items:center;
      justify-content:center;gap:28px;
      padding:32px 24px env(safe-area-inset-bottom,24px);
      text-align:center;
    }}
    h1{{font-size:1.4rem;font-weight:700;letter-spacing:-0.02em}}
    p{{font-size:0.9rem;color:#8e8e93;line-height:1.5;max-width:300px}}
    .open-btn{{
      display:block;
      background:#4f8ef7;color:#fff;
      font-size:1rem;font-weight:600;
      padding:16px 36px;border-radius:50px;
      text-decoration:none;
      transition:opacity .15s;
    }}
    .open-btn:active{{opacity:.7}}
    .url-box{{
      font-size:0.72rem;color:#636366;
      word-break:break-all;max-width:320px;line-height:1.4;
    }}
  </style>
</head>
<body>
    <h1>📷 phoneToClipboard</h1>
  <p>Tap the button below to open the app with your pairing token.</p>
    <a class="open-btn" href="{url}">Open phoneToClipboard</a>
  <p class="url-box">{url}</p>
</body>
</html>
"""
    return HTMLResponse(html)


# Mount static files last so dynamic routes win
if _WEB_DIR.exists():
    app.mount("/", StaticFiles(directory=str(_WEB_DIR), html=True), name="web")
else:
    @app.get("/")
    async def _no_web() -> HTMLResponse:
        return HTMLResponse("<h1>web/ directory not found</h1>", status_code=500)


# ---------------------------------------------------------------------------
# QR code terminal output
# ---------------------------------------------------------------------------

def _print_qr(url: str) -> None:
    qr = qrcode.QRCode(
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=1,
        border=2,
    )
    qr.add_data(url)
    qr.make(fit=True)
    qr.print_ascii(invert=True)
    print(f"\n  URL: {url}\n", flush=True)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="phoneToClipboard server")
    p.add_argument("--host", default="0.0.0.0", help="Bind host (default: 0.0.0.0)")
    p.add_argument("--port", type=int, default=8765, help="Bind port (default: 8765)")
    p.add_argument("--ssl-keyfile", default=None, help="Path to TLS private key")
    p.add_argument("--ssl-certfile", default=None, help="Path to TLS certificate")
    p.add_argument(
        "--rotate-token",
        action="store_true",
        help="Generate a new auth token (invalidates existing QR codes)",
    )
    return p.parse_args()


def main() -> None:
    args = _parse_args()

    if args.rotate_token:
        new_token = rotate_token()
        print(f"Token rotated. New token: {new_token}", flush=True)

    token = load_or_create_token()
    lan_ip = get_lan_ip()

    if lan_ip is None:
        log.warning("Could not detect LAN IP; QR code will use 127.0.0.1")
        lan_ip = "127.0.0.1"
    elif is_public_ip(lan_ip):
        log.error(
            "Detected IP %s looks like a public address. "
            "Refusing to start to avoid unintended exposure. "
            "Bind explicitly with --host <lan-ip>.",
            lan_ip,
        )
        sys.exit(1)

    scheme = "https" if args.ssl_keyfile else "http"
    url = f"{scheme}://{lan_ip}:{args.port}/?t={token}"
    pair_url = f"{scheme}://{lan_ip}:{args.port}/pair"
    mdns_host = get_mdns_hostname()
    mdns_url = f"{scheme}://{mdns_host}:{args.port}/?t={token}" if mdns_host else None
    mdns_pair_url = f"{scheme}://{mdns_host}:{args.port}/pair" if mdns_host else None

    print("\n" + "=" * 60, flush=True)
    print("  phoneToClipboard — scan the QR code on your iPhone", flush=True)
    print("=" * 60 + "\n", flush=True)
    if mdns_url and mdns_host and lan_ip != "127.0.0.1":
        _print_qr(mdns_url)
        print(f"  Pair page (stable): {mdns_pair_url}\n", flush=True)
        print(f"  Stable URL (try this for Home Screen icon): {mdns_url}", flush=True)
        print(f"  Stable pair page: {mdns_pair_url}\n", flush=True)
    else:
        _print_qr(url)
        print(f"  Pair page (no token needed): {pair_url}\n", flush=True)
    if not args.ssl_keyfile:
        print(
            "  ⚠  Running over HTTP — camera capture still works,\n"
            "     but traffic is unencrypted on the LAN.\n"
            "     Run scripts/setup-mkcert.sh for HTTPS.\n",
            flush=True,
        )

    uvicorn_kwargs: dict = {
        "app": "app.main:app",
        "host": args.host,
        "port": args.port,
        "log_level": "warning",
        "access_log": False,
    }
    if args.ssl_keyfile:
        uvicorn_kwargs["ssl_keyfile"] = args.ssl_keyfile
        uvicorn_kwargs["ssl_certfile"] = args.ssl_certfile

    uvicorn.run(**uvicorn_kwargs)


if __name__ == "__main__":
    main()
