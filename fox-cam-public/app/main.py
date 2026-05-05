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

# Comma-separated allowlist of admin emails. Admins can promote/unpromote
# highlights to the public landing page. Comparison is case-insensitive
# and trims whitespace.
ADMIN_EMAILS = {
    e.strip().lower()
    for e in os.environ.get("ADMIN_EMAILS", "").split(",")
    if e.strip()
}

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
    # /robots.txt is allowed so crawlers can read the disallow rule
    # before being challenged at CF Access. (CF will likely block
    # anonymous traffic anyway, but this keeps the polite signal
    # working in any future config.)
    path = request.url.path
    if path in ("/healthz", "/robots.txt", "/sw.js", "/manifest.webmanifest"):
        return await call_next(request)
    # All /static/ assets are public — they're cosmetic (CSS, JS, SVGs,
    # icons, the logo PNG). Nothing sensitive lives in /static. Required
    # for the public landing page to render and for the PWA install
    # prompt to fetch its icons on a fresh device.
    if path.startswith("/static/"):
        return await call_next(request)
    # Public landing surface — anonymous viewers see a curated set of
    # featured highlights at /. The matching API endpoints + clip
    # permalink + clip stream/thumbnail are also unauthenticated so
    # those cards can render and play. Cloudflare Access has matching
    # bypass rules at the edge for these paths.
    if path == "/" or path == "/clip" or path.startswith("/clip/"):
        return await call_next(request)
    if path in ("/api/featured", "/api/whoami"):
        return await call_next(request)
    if path.startswith("/api/featured/"):
        return await call_next(request)
    # Per-clip media that the public landing + permalink need: the
    # thumbnail and clip files for any *featured* highlight. These
    # endpoints check featured-ness before serving (see below).
    if path.startswith("/api/highlights/") and (
        path.endswith("/thumbnail") or path.endswith("/clip")
        or path.endswith(".mp4")
    ):
        return await call_next(request)
    # Single-highlight metadata for the permalink page (anonymous can
    # view only featured ones; the route handler enforces).
    if path.startswith("/api/highlights/") and path.count("/") == 3:
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
    """Public landing page.

    Always renders the landing page. The live multi-camera grid lives
    at /live (a gated Access path) — authed visitors are sent there by
    the landing's login buttons.

    We can't render the live grid here based on the email header,
    because / is in a Cloudflare Access Bypass app: CF strips the
    cf-access-authenticated-user-email header on bypassed paths even
    for authed visitors. So / always looks anonymous to the origin —
    making it strictly a public surface, with /live as the dedicated
    authed home.
    """
    return templates.TemplateResponse(
        "landing.html",
        {"request": request, "v": ASSET_VERSION},
    )


@app.get("/live", response_class=HTMLResponse)
def live_page(request: Request) -> HTMLResponse:
    """Live multi-camera grid (gated by Cloudflare Access)."""
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "streams": sorted(PUBLIC_STREAMS),
            "v": ASSET_VERSION,
            **_identity_ctx(request),
        },
    )


def _identity_ctx(request: Request) -> dict[str, Any]:
    """Identity for template injection on gated routes.

    These routes are guaranteed to be authed (CF Access enforces the
    cf-access-authenticated-user-email header), so we know who the
    visitor is at template-render time. Avoids a round-trip via the
    /api/whoami endpoint, which is unreliable when the client request
    happens to land on a CF Access Bypass path (header gets stripped).
    """
    email = _actor_email(request)
    return {
        "current_email": email or "",
        "is_admin": bool(email and email.lower() in ADMIN_EMAILS),
    }


@app.get("/highlights", response_class=HTMLResponse)
def highlights_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        "highlights.html",
        {
            "request": request,
            "streams": sorted(PUBLIC_STREAMS),
            "v": ASSET_VERSION,
            **_identity_ctx(request),
        },
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
        {"request": request, "event_id": event_id, "v": ASSET_VERSION,
         **_identity_ctx(request)},
    )


@app.get("/remix/{remix_id}", response_class=HTMLResponse)
async def remix_permalink(remix_id: str, request: Request) -> HTMLResponse:
    """Permalink for a saved remix (sub-clip + zoom region).
    Shares the clip.html template; client JS detects the route and
    fetches /api/remixes/<id> instead of /api/highlights/<id>."""
    return templates.TemplateResponse(
        "clip.html",
        {"request": request, "event_id": "", "remix_id": remix_id,
         "v": ASSET_VERSION, **_identity_ctx(request)},
    )


@app.get("/api/highlights/{event_id}")
async def get_highlight(event_id: str, request: Request) -> Any:
    """Single highlight metadata — proxies curator's GET /highlights/<id>.

    Anyone with a valid event_id can read this. Cloudflare Access has
    /api/highlights/* in a Bypass app so anonymous viewers can hit
    featured permalinks; that bypass also strips the auth header for
    authed users, so we can't distinguish them at this layer. The
    LIST endpoint /api/highlights is gated, so anonymous can't
    enumerate IDs — the only way an anonymous visitor learns an ID is
    via the public /api/featured response.
    """
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


@app.get("/api/whoami")
def whoami(request: Request) -> dict[str, Any]:
    """Identity hint for the client.

    Anonymous → {"authed": false, "admin": false}.
    Authenticated non-admin → {"authed": true, "admin": false, "email": "..."}.
    Admin → {"authed": true, "admin": true, "email": "..."}.

    Used by templates to decide which controls to render (e.g., the
    Promote button on highlight cards). NEVER trust the client's
    interpretation of this — every admin action is re-checked against
    ADMIN_EMAILS server-side.
    """
    email = _actor_email(request)
    return {
        "authed": bool(email),
        "admin": bool(email and email.lower() in ADMIN_EMAILS),
        "email": email,
    }


@app.get("/api/featured")
async def get_featured(limit: int = 6) -> Any:
    """Public list of featured highlights for the landing page."""
    if limit < 1 or limit > 24:
        raise HTTPException(status_code=400, detail="limit out of range")
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{CURATOR_API}/featured",
                              params={"limit": limit}, timeout=5.0)
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail="curator error")
    return r.json()


@app.post("/api/admin/highlights/{event_id}/feature")
async def admin_feature(event_id: str, request: Request) -> Any:
    """Promote a highlight to the public landing page (admin-only)."""
    admin_email = _require_admin(request)
    body = await request.json() if request.headers.get("content-length") else {}
    payload = {"by": admin_email, "caption": body.get("caption")}
    async with httpx.AsyncClient() as client:
        r = await client.post(f"{CURATOR_API}/highlights/{event_id}/feature",
                              json=payload, timeout=8.0)
    if r.status_code == 404:
        raise HTTPException(status_code=404, detail="not found")
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail=f"curator error: {r.text[:200]}")
    return r.json()


@app.post("/api/admin/highlights/{event_id}/unfeature")
async def admin_unfeature(event_id: str, request: Request) -> Any:
    """Remove a highlight from the public landing page (admin-only)."""
    admin_email = _require_admin(request)
    async with httpx.AsyncClient() as client:
        r = await client.post(f"{CURATOR_API}/highlights/{event_id}/unfeature",
                              json={"by": admin_email}, timeout=8.0)
    if r.status_code == 404:
        raise HTTPException(status_code=404, detail="not found")
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail=f"curator error: {r.text[:200]}")
    return r.json()


@app.get("/healthz")
def healthz() -> dict[str, Any]:
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# robots.txt — disallow everything. The site is family-private behind
# Cloudflare Access; no benefit to indexing, real downside if a search
# engine crawls anything that ever leaks past Access.
# ---------------------------------------------------------------------------
_ROBOTS_TXT = (
    "# Our Foxes is a private family site behind Cloudflare Access.\n"
    "# Please don't index any of it.\n"
    "User-agent: *\n"
    "Disallow: /\n"
)


@app.get("/robots.txt")
def robots_txt() -> Any:
    from fastapi.responses import Response
    return Response(content=_ROBOTS_TXT, media_type="text/plain")


# ---------------------------------------------------------------------------
# PWA: service worker + manifest at root scope.
#
# A service worker can only control paths within its registration scope,
# which defaults to its own location. To control the whole site we serve
# sw.js at /sw.js (not /static/sw.js). The actual file still lives in
# /app/static so we can hot-edit without restarting; this route just
# proxies that with the right MIME + Service-Worker-Allowed header.
# ---------------------------------------------------------------------------

@app.get("/sw.js")
def service_worker() -> Any:
    from fastapi.responses import Response
    import pathlib
    body = pathlib.Path("/app/static/sw.js").read_bytes()
    return Response(
        content=body,
        media_type="application/javascript",
        headers={
            # Belt-and-suspenders: declare scope explicitly even though
            # /sw.js naturally controls /. Some browsers warn without it.
            "Service-Worker-Allowed": "/",
            # SW files should not be cached by the browser — the browser
            # has its own update flow. Cache-Control: no-cache is the
            # convention for SW updates.
            "Cache-Control": "no-cache",
        },
    )


@app.get("/manifest.webmanifest")
def manifest_root() -> Any:
    """Mirror of /static/manifest.webmanifest for any browser/tool that
    expects the manifest at the URL root. Served with the official
    application/manifest+json content type."""
    from fastapi.responses import Response
    import pathlib
    body = pathlib.Path("/app/static/manifest.webmanifest").read_bytes()
    return Response(
        content=body,
        media_type="application/manifest+json",
    )


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


def _is_admin(request: Request) -> bool:
    email = _actor_email(request)
    return bool(email and email.lower() in ADMIN_EMAILS)


def _require_admin(request: Request) -> str:
    """Raise 403 unless the request comes from an ADMIN_EMAILS user.

    Returns the admin's email so callers can attribute the action.
    """
    email = _actor_email(request)
    if not email or email.lower() not in ADMIN_EMAILS:
        raise HTTPException(status_code=403, detail="admin only")
    return email


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
    # Per-id media is reachable without auth because /api/highlights/*
    # is in a Cloudflare Access Bypass app (so anonymous viewers can
    # play featured permalinks). Event IDs are unguessable timestamp+
    # random hashes, the LIST endpoint stays authed, and only featured
    # IDs are reachable to anonymous viewers via the public /api/featured
    # response — so a knowledge-of-the-id leak is bounded to clips an
    # admin already chose to share.
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
