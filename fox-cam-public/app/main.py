"""Public-facing fox-cam viewer API.

Read-only by design. Talks to:
  - go2rtc on the host (live WebRTC streams) at host.docker.internal:1985
  - frigate-curator on the host (highlight metadata) at host.docker.internal:5141

Never reaches Frigate's admin endpoints, never writes anywhere, never
talks to anything else on pa-internal. The Docker network attachment is
ONLY for ingress from cloudflare-tunnel; egress is restricted to those
two host loopback APIs.

Auth happens at Cloudflare Access (in front of cloudflare-tunnel). This
service trusts the upstream — but ALSO enforces a minimal "must have a
Cf-Access-Jwt-Assertion header" check as defense in depth, so a misrouted
internal request can't accidentally serve content unauthenticated.
"""
from __future__ import annotations

import logging
import os
from typing import Any

import asyncio

import httpx
import websockets
from fastapi import FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates


GO2RTC_API = os.environ.get("GO2RTC_API", "http://host.docker.internal:1985")
GO2RTC_WS = os.environ.get("GO2RTC_WS", "ws://host.docker.internal:1985")
GO2RTC_RTSP_HOST = os.environ.get("GO2RTC_RTSP_HOST", "host.docker.internal")  # for client-side WebRTC negotiation
CURATOR_API = os.environ.get("CURATOR_API", "http://host.docker.internal:5141")
REQUIRE_CF_ACCESS = os.environ.get("REQUIRE_CF_ACCESS", "true").lower() == "true"

# Whitelist of stream names go2rtc serves to the public. Hardcoded so a
# bug in go2rtc config can't suddenly expose new streams via this service.
PUBLIC_STREAMS = {"fox_den_1", "fox_den_2", "fox_den_3"}


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("fox_cam_public")


app = FastAPI(title="Fox Cam Viewer", docs_url=None, redoc_url=None, openapi_url=None)
templates = Jinja2Templates(directory="/app/templates")
app.mount("/static", StaticFiles(directory="/app/static"), name="static")


# Cache-busting version. Computed once at process start from the mtime
# of the static directory — every container rebuild gets a new value,
# every static file edit (in dev) gets a new value, but identical
# rebuilds with no changes share. Templates append `?v={ASSET_VERSION}`
# to script/css URLs so Cloudflare + browsers can't serve stale assets
# across deploys, even when their default cache rules ignore our
# Cache-Control: no-store on /static/.
def _compute_asset_version() -> str:
    import hashlib
    import pathlib
    h = hashlib.md5()
    for p in sorted(pathlib.Path("/app/static").rglob("*")):
        if p.is_file():
            h.update(p.name.encode())
            h.update(str(int(p.stat().st_mtime)).encode())
    return h.hexdigest()[:10]


ASSET_VERSION = _compute_asset_version()


@app.middleware("http")
async def no_cache_static(request: Request, call_next):
    """Force browsers + Cloudflare to revalidate cacheable responses.

    Cloudflare's default cache rules treat JS/CSS as cacheable even
    when origin says no-store. We append ?v=ASSET_VERSION to script/css
    URLs in templates as the primary cache-busting mechanism, and also
    set no-store headers as a belt-and-suspenders. The HTML response
    itself MUST be no-store, otherwise CF will cache an HTML referring
    to an old ASSET_VERSION across deploys.
    """
    response = await call_next(request)
    p = request.url.path
    if p.startswith("/static/") or p in {"/", "/highlights"}:
        response.headers["Cache-Control"] = "no-store, must-revalidate"
    return response


# ---------------------------------------------------------------------------
# Defense-in-depth: every request must carry a Cloudflare Access JWT.
# (Cloudflare Access strips the cf-access-jwt-assertion from external
# requests that didn't come through Access; if the header is present
# we trust that the request was authenticated.)
# ---------------------------------------------------------------------------

@app.middleware("http")
async def require_cf_access(request: Request, call_next):
    if not REQUIRE_CF_ACCESS:
        return await call_next(request)
    # /healthz is allowed unauthenticated for the host's health-monitor
    # service; loopback only via docker network.
    if request.url.path == "/healthz":
        return await call_next(request)
    # Static assets: served behind the same auth gate (no CDN bypass)
    jwt = request.headers.get("cf-access-jwt-assertion")
    if not jwt:
        return JSONResponse(
            {"detail": "authentication required"},
            status_code=401,
            headers={"WWW-Authenticate": "Bearer realm=\"cloudflare-access\""},
        )
    return await call_next(request)


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
def home(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "streams": sorted(PUBLIC_STREAMS), "v": ASSET_VERSION},
    )


@app.get("/highlights", response_class=HTMLResponse)
def highlights_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        "highlights.html",
        {"request": request, "streams": sorted(PUBLIC_STREAMS), "v": ASSET_VERSION},
    )


@app.get("/healthz")
def healthz() -> dict[str, Any]:
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Live (proxied to go2rtc)
# ---------------------------------------------------------------------------

@app.get("/api/streams")
def list_streams() -> dict[str, Any]:
    """Return the set of streams the viewer is allowed to show."""
    return {"streams": sorted(PUBLIC_STREAMS)}


@app.api_route("/api/webrtc/{stream}", methods=["POST"])
async def webrtc_offer(stream: str, request: Request) -> StreamingResponse:
    """Proxy WebRTC SDP exchange to go2rtc.

    Browser POSTs an SDP offer; go2rtc returns the SDP answer. We just
    pass the body through. Path is whitelisted to PUBLIC_STREAMS so an
    attacker cannot supply a stream name we didn't intend to expose.
    """
    if stream not in PUBLIC_STREAMS:
        raise HTTPException(status_code=404, detail="unknown stream")
    body = await request.body()
    headers = {"Content-Type": request.headers.get("content-type", "application/sdp")}
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{GO2RTC_API}/api/webrtc",
            params={"src": stream},
            content=body,
            headers=headers,
            timeout=15.0,
        )
    return StreamingResponse(
        iter([r.content]),
        status_code=r.status_code,
        media_type=r.headers.get("content-type"),
    )


@app.websocket("/api/mse/{stream}")
async def mse_websocket(ws: WebSocket, stream: str) -> None:
    """Proxy go2rtc's MSE-over-WebSocket stream.

    go2rtc serves fragmented MP4 chunks over WS at /api/ws?src=<name>
    when the client requests "mse" as the format. We pass that through
    so the browser can attach the chunks to a MediaSource for low-latency
    playback (~500-800ms). Works over Cloudflare Tunnel because it's
    just a WebSocket — no UDP, no NAT traversal needed.

    Cloudflare Access auth is checked at WebSocket accept time via the
    cf-access-jwt-assertion header forwarded with the upgrade request.
    """
    if stream not in PUBLIC_STREAMS:
        await ws.close(code=4404, reason="unknown stream")
        return
    if REQUIRE_CF_ACCESS and not ws.headers.get("cf-access-jwt-assertion"):
        await ws.close(code=4401, reason="authentication required")
        return

    upstream_url = f"{GO2RTC_WS}/api/ws?src={stream}"
    await ws.accept()
    try:
        async with websockets.connect(upstream_url, max_size=None) as upstream:
            # Don't send init here — let the browser drive the protocol
            # (it knows what its MediaSource supports). The proxy is a
            # transparent passthrough; the browser sends its mse codec
            # spec when it's ready, and go2rtc starts streaming after.

            async def upstream_to_client() -> None:
                async for msg in upstream:
                    if isinstance(msg, bytes):
                        await ws.send_bytes(msg)
                    else:
                        await ws.send_text(msg)

            async def client_to_upstream() -> None:
                while True:
                    msg = await ws.receive()
                    if msg.get("type") == "websocket.disconnect":
                        return
                    if "bytes" in msg and msg["bytes"] is not None:
                        await upstream.send(msg["bytes"])
                    elif "text" in msg and msg["text"] is not None:
                        await upstream.send(msg["text"])

            await asyncio.gather(
                upstream_to_client(),
                client_to_upstream(),
                return_exceptions=True,
            )
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning("MSE proxy error for %s: %s", stream, e)
        try:
            await ws.close(code=1011, reason="upstream error")
        except Exception:
            pass


@app.get("/api/snapshot/{stream}")
async def snapshot(stream: str) -> StreamingResponse:
    """Serve a single JPEG snapshot from go2rtc (fallback for non-WebRTC clients)."""
    if stream not in PUBLIC_STREAMS:
        raise HTTPException(status_code=404, detail="unknown stream")
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{GO2RTC_API}/api/frame.jpeg",
            params={"src": stream},
            timeout=10.0,
        )
        if r.status_code != 200:
            raise HTTPException(status_code=502, detail="snapshot unavailable")
    return StreamingResponse(
        iter([r.content]),
        media_type="image/jpeg",
        headers={"Cache-Control": "no-store"},
    )


# ---------------------------------------------------------------------------
# Highlights (proxied to curator)
# ---------------------------------------------------------------------------

@app.get("/api/highlights")
async def list_highlights(
    camera: str | None = None,
    since: float | None = Query(default=None),
    until: float | None = Query(default=None),
    min_score: float = Query(default=0.0, ge=0.0, le=1.0),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> Any:
    if camera and camera not in PUBLIC_STREAMS:
        raise HTTPException(status_code=400, detail="unknown camera")
    params: dict[str, Any] = {
        "min_score": min_score,
        "limit": limit,
        "offset": offset,
    }
    if camera:
        params["camera"] = camera
    if since is not None:
        params["since"] = since
    if until is not None:
        params["until"] = until
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{CURATOR_API}/highlights", params=params, timeout=10.0)
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail="curator error")
    return r.json()


@app.get("/api/highlights/{event_id}/clip")
async def highlight_clip(event_id: str) -> StreamingResponse:
    return await _proxy_curator(f"/highlights/{event_id}/clip", "video/mp4")


@app.get("/api/highlights/{event_id}/thumbnail")
async def highlight_thumb(event_id: str) -> StreamingResponse:
    return await _proxy_curator(f"/highlights/{event_id}/thumbnail", "image/jpeg")


async def _proxy_curator(path: str, media_type: str) -> StreamingResponse:
    async with httpx.AsyncClient() as client:
        async with client.stream("GET", f"{CURATOR_API}{path}", timeout=30.0) as r:
            if r.status_code == 404:
                raise HTTPException(status_code=404, detail="not found")
            if r.status_code != 200:
                raise HTTPException(status_code=502, detail="curator error")
            content = await r.aread()
    return StreamingResponse(
        iter([content]),
        media_type=media_type,
        headers={"Cache-Control": "private, max-age=300"},
    )
