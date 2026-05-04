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
# Base camera names — what the live grid renders as tiles. One section
# per camera; other UI keys off these names too (data-stream, id, etc.).
PUBLIC_STREAMS = {"fox_den_1", "fox_den_2", "fox_den_3", "fox_den_4"}

# Streams the WebRTC/MSE proxy will pass through. Includes the _sub
# variants because the live grid currently asks for them (main-stream
# SPS-level mismatch causes browser decode errors).
ALLOWED_PROXY_STREAMS = PUBLIC_STREAMS | {f"{s}_sub" for s in PUBLIC_STREAMS}


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


@app.get("/clip/{event_id}", response_class=HTMLResponse)
async def clip_permalink(event_id: str, request: Request) -> HTMLResponse:
    """Permalink page for a single highlight — easily shareable URL.

    The fetch happens client-side after the page loads, so the page
    template itself is small + cacheable. The clip metadata (and
    favorite/demote state) comes from /api/highlights/<id>.
    """
    return templates.TemplateResponse(
        "clip.html",
        {"request": request, "event_id": event_id, "v": ASSET_VERSION},
    )


@app.get("/remix/{remix_id}", response_class=HTMLResponse)
async def remix_permalink(remix_id: str, request: Request) -> HTMLResponse:
    """Permalink for a saved remix (sub-clip + zoom region).
    Shares the clip.html template; client JS detects the route and
    fetches /api/remixes/<id> instead of /api/highlights/<id>."""
    return templates.TemplateResponse(
        "clip.html",
        {"request": request, "event_id": "", "remix_id": remix_id, "v": ASSET_VERSION},
    )


@app.get("/api/highlights/{event_id}")
async def get_highlight(event_id: str, request: Request) -> Any:
    """Single highlight metadata — proxies curator's GET /highlights/<id>."""
    email = _actor_email(request)
    params = {"email": email} if email else {}
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{CURATOR_API}/highlights/{event_id}",
                              params=params, timeout=8.0)
    if r.status_code == 404:
        raise HTTPException(status_code=404, detail="not found")
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail="curator error")
    return r.json()


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
    if stream not in ALLOWED_PROXY_STREAMS:
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
    if stream not in ALLOWED_PROXY_STREAMS:
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
    if stream not in ALLOWED_PROXY_STREAMS:
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
    request: Request,
    camera: str | None = None,
    since: float | None = Query(default=None),
    until: float | None = Query(default=None),
    min_score: float = Query(default=0.0, ge=0.0, le=1.0),
    bucket: str = Query(default="pending", regex="^(pending|all|favorites|demoted|mine|shared)$"),
    time_of_day: str = Query(default="any", regex="^(any|day|night)$"),
    species_filter: str = Query(default="", regex="^(|wildlife|fox|unclassified)$"),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> Any:
    if camera and camera not in PUBLIC_STREAMS:
        raise HTTPException(status_code=400, detail="unknown camera")
    params: dict[str, Any] = {
        "min_score": min_score,
        "bucket": bucket,
        "time_of_day": time_of_day,
        "limit": limit,
        "offset": offset,
    }
    if camera:
        params["camera"] = camera
    if since is not None:
        params["since"] = since
    if until is not None:
        params["until"] = until
    # Forward viewer email so curator can attach my_favorited / my_demoted
    # state per card and resolve bucket=mine.
    email = _actor_email(request)
    if email:
        params["email"] = email
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{CURATOR_API}/highlights", params=params, timeout=10.0)
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail="curator error")
    body = r.json()
    # Apply species filter client-side (curator doesn't know the
    # 'wildlife' bucket — that's a viewer-level concept derived from
    # species). Cheap; result sets are bounded.
    if species_filter:
        items = body.get("items", [])
        if species_filter == "wildlife":
            kept = [h for h in items if h.get("species") not in
                    (None, "", "none", "person", "vehicle", "error")]
        elif species_filter == "fox":
            kept = [h for h in items if h.get("species") == "fox"]
        elif species_filter == "unclassified":
            kept = [h for h in items if not h.get("species")]
        else:
            kept = items
        body["items"] = kept
        body["count"] = len(kept)
    return body


# ---------------------------------------------------------------------------
# Family-vote actions. The user's email comes from Cloudflare Access via
# the cf-access-authenticated-user-email header (CF sets it on every
# authenticated request). We forward it to the curator as the `by` field.
# ---------------------------------------------------------------------------

def _actor_email(request: Request) -> str | None:
    return request.headers.get("cf-access-authenticated-user-email")


# ---------------------------------------------------------------------------
# Per-user viewer state — "new since last visit" badging.
# ---------------------------------------------------------------------------

@app.get("/api/viewer/state")
async def get_viewer_state(request: Request) -> Any:
    email = _actor_email(request)
    async with httpx.AsyncClient() as client:
        params = {"email": email} if email else {}
        r = await client.get(f"{CURATOR_API}/viewer/state", params=params, timeout=5.0)
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail="curator error")
    return r.json()


@app.post("/api/viewer/seen")
async def mark_viewer_seen(request: Request) -> Any:
    email = _actor_email(request)
    if not email:
        return {"status": "ignored", "reason": "anonymous"}
    async with httpx.AsyncClient() as client:
        r = await client.post(f"{CURATOR_API}/viewer/seen",
                              json={"email": email}, timeout=5.0)
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail="curator error")
    return r.json()


@app.post("/api/highlights/{event_id}/favorite")
async def favorite(event_id: str, request: Request) -> Any:
    return await _post_action(event_id, "favorite", _actor_email(request))


@app.post("/api/highlights/{event_id}/demote")
async def demote(event_id: str, request: Request) -> Any:
    return await _post_action(event_id, "demote", _actor_email(request))


@app.post("/api/highlights/{event_id}/clear")
async def clear(event_id: str, request: Request) -> Any:
    return await _post_action(event_id, "clear", _actor_email(request))


# ---------------------------------------------------------------------------
# Remixes — user-defined sub-clip trims with optional zoom region.
# Proxies through to curator with viewer email forwarded as `by`.
# ---------------------------------------------------------------------------

@app.post("/api/highlights/{event_id}/remix")
async def create_remix(event_id: str, request: Request) -> Any:
    body = await request.json()
    body["by"] = _actor_email(request)
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{CURATOR_API}/highlights/{event_id}/remix",
            json=body, timeout=10.0,
        )
    if r.status_code == 404:
        raise HTTPException(status_code=404, detail="not found")
    if r.status_code == 400:
        raise HTTPException(status_code=400, detail=(r.json() or {}).get("detail", "bad request"))
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail="curator error")
    return r.json()


@app.get("/api/remixes/{remix_id}")
async def get_remix(remix_id: str) -> Any:
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{CURATOR_API}/remixes/{remix_id}", timeout=8.0)
    if r.status_code == 404:
        raise HTTPException(status_code=404, detail="not found")
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail="curator error")
    return r.json()


@app.get("/api/remixes")
async def list_remixes(request: Request,
                        event_id: str | None = None,
                        scope: str = Query(default="", regex="^(|mine|all)$"),
                        limit: int = Query(default=50, ge=1, le=500),
                        offset: int = Query(default=0, ge=0)) -> Any:
    email = _actor_email(request)
    params: dict[str, Any] = {"limit": limit, "offset": offset}
    if event_id: params["event_id"] = event_id
    elif scope == "mine" and email: params["email"] = email
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{CURATOR_API}/remixes", params=params, timeout=10.0)
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail="curator error")
    return r.json()


@app.patch("/api/remixes/{remix_id}")
async def update_remix(remix_id: str, request: Request) -> Any:
    body = await request.json()
    async with httpx.AsyncClient() as client:
        r = await client.patch(f"{CURATOR_API}/remixes/{remix_id}",
                                json=body, timeout=10.0)
    if r.status_code == 404:
        raise HTTPException(status_code=404, detail="not found")
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail="curator error")
    return r.json()


@app.delete("/api/remixes/{remix_id}")
async def delete_remix(remix_id: str, request: Request) -> Any:
    by = _actor_email(request)
    async with httpx.AsyncClient() as client:
        r = await client.delete(f"{CURATOR_API}/remixes/{remix_id}",
                                 params={"by": by} if by else {}, timeout=10.0)
    if r.status_code == 404:
        raise HTTPException(status_code=404, detail="not found")
    if r.status_code == 403:
        raise HTTPException(status_code=403, detail="only creator may delete")
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail="curator error")
    return r.json()


async def _post_action(event_id: str, action: str, by: str | None) -> Any:
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{CURATOR_API}/highlights/{event_id}/{action}",
            json={"by": by},
            timeout=10.0,
        )
    if r.status_code == 404:
        raise HTTPException(status_code=404, detail="not found")
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
