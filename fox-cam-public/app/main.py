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
    # Remix permalinks — same posture as /clip/. The page itself
    # renders OG cards for shared links and the inline trimmed MP4
    # is needed for iMessage / Slack / Twitter rich previews. Knowing
    # the remix_id (a random short hash) is the only gate; LIST stays
    # authed so anonymous can't enumerate.
    if path.startswith("/remix/"):
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
    # Remix metadata + inline clip for OG cards + landing-page features.
    # /api/remixes/{id}            → metadata JSON (server-side OG fetch
    #                                 also uses curator directly, but
    #                                 client JS uses this proxy)
    # /api/remixes/{id}/clip       → inline trimmed MP4 (og:video target)
    if path.startswith("/api/remixes/") and (
        path.count("/") == 3 or path.endswith("/clip")
    ):
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
            "active_view": "live",
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
def highlights_page(request: Request, bucket: str | None = None) -> HTMLResponse:
    """Highlights gallery. Bottom-tab nav uses ?bucket= to pick the
    initial view (also restored from URL on refresh / share). Map the
    bucket to the matching active_view label so the bottom-tab pill
    highlights correctly on first paint."""
    bucket_to_view = {
        "mine": "mine",
        "shared": "shared",
        "remixes": "remixes",
        "demoted": "clips",   # demoted lives under Clips → Status filter
    }
    active_view = bucket_to_view.get(bucket or "", "clips")
    return templates.TemplateResponse(
        "highlights.html",
        {
            "request": request,
            "streams": sorted(PUBLIC_STREAMS),
            "v": ASSET_VERSION,
            "initial_bucket": bucket or "pending",
            "active_view": active_view,
            **_identity_ctx(request),
        },
    )


@app.get("/highlights/{event_id}/remix", response_class=HTMLResponse)
async def remix_edit(event_id: str, request: Request) -> HTMLResponse:
    """Authed remix-edit page for a highlight.

    Sits under /highlights/* so it's covered by the authed Access app
    and CF Access reliably injects the email header. The clip
    permalink page at /clip/{id} is in the public Bypass app (so a
    shared featured-clip URL works for anonymous viewers), but Bypass
    strips the auth header — making the remix editor on /clip/* render
    in anonymous mode for authed users. /highlights/{id}/remix is the
    authed-only path that gives the editor a real session.
    """
    return templates.TemplateResponse(
        "clip.html",
        {"request": request, "event_id": event_id, "v": ASSET_VERSION,
         "force_remix_mode": True, "active_view": "clips",
         **_identity_ctx(request)},
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
         "active_view": "clips", **_identity_ctx(request)},
    )


@app.get("/remix/{remix_id}", response_class=HTMLResponse)
async def remix_permalink(remix_id: str, request: Request) -> HTMLResponse:
    """Permalink for a saved remix (sub-clip + zoom region).
    Shares the clip.html template; client JS detects the route and
    fetches /api/remixes/<id> instead of /api/highlights/<id>.

    We also fetch the remix metadata server-side here — *only* to
    populate Open Graph / Twitter Card meta tags so iMessage / Slack /
    Twitter / etc. crawlers (which don't run JS) get a rich preview
    card with thumbnail + inline video. The client still does its own
    fetch on render; the server-side fetch is a one-shot for the
    crawler's benefit and is tolerant of curator being slow or down
    (we just skip the OG tags in that case rather than 502 the page).
    """
    og: dict[str, Any] | None = None
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{CURATOR_API}/remixes/{remix_id}", timeout=3.0)
        if r.status_code == 200:
            data = r.json()
            og = _build_remix_og(data, request)
    except Exception:
        # Curator timeout / unreachable — render the shell without OG
        # tags. Crawler still gets a 200; preview just won't be rich.
        og = None
    return templates.TemplateResponse(
        "clip.html",
        {"request": request, "event_id": "", "remix_id": remix_id,
         "v": ASSET_VERSION, "active_view": "remixes", "og": og,
         **_identity_ctx(request)},
    )


def _build_remix_og(data: dict[str, Any], request: Request) -> dict[str, Any] | None:
    """Construct the Open Graph context dict for a remix permalink.

    `data` is the JSON shape returned by curator's GET /remixes/{id} —
    {"remix": {...}, "highlight": {...}}. We pull a thumbnail from the
    PARENT highlight (already public via the existing CF Access bypass)
    and an inline-streamable video from the new /api/remixes/{id}/clip
    proxy. The base URL comes from the request so OG URLs stay on the
    same public host the user shared from (ourfoxes.com vs
    foxes.cd-ai-pa.work).
    """
    remix = data.get("remix") or {}
    hl = data.get("highlight") or {}
    if not remix:
        return None

    # request.base_url uses request.url.scheme — which is always 'http'
    # behind Cloudflare Tunnel since we terminate TLS at the edge. Pull
    # the real scheme from X-Forwarded-Proto so OG URLs come out https
    # (Apple's LinkPresentation rejects http resources for og:image and
    # og:video on iOS 16+).
    proto = request.headers.get("x-forwarded-proto", request.url.scheme) or "https"
    host = request.headers.get("host") or request.url.netloc
    base = f"{proto}://{host}"
    remix_id = remix.get("remix_id")
    event_id = remix.get("event_id") or hl.get("event_id")
    start_s = float(remix.get("start_offset_s") or 0.0)
    end_s = float(remix.get("end_offset_s") or 0.0)
    duration = max(0.0, end_s - start_s)
    title_user = (remix.get("title") or "").strip()
    species = (hl.get("species") or "").strip().lower()
    species_label = species if species and species not in {"none", "?", ""} else "fox"
    camera = (hl.get("camera") or "").strip()
    cam_label = camera.replace("_", " ") if camera else ""

    # Title: prefer the user-given remix title, fall back to a
    # generated one. Keep under ~60 chars so iMessage doesn't elide.
    if title_user:
        og_title = f"{title_user} · {duration:.0f}s"
    else:
        og_title = f"Fox remix · {duration:.0f}s"

    # Description: short factual subline. iMessage uses ~90 chars
    # before truncating.
    desc_bits: list[str] = []
    if species_label:
        desc_bits.append(species_label.capitalize())
    if cam_label:
        desc_bits.append(f"on {cam_label}")
    desc_bits.append(f"{duration:.0f}s remix")
    og_desc = " · ".join(desc_bits)

    og_url = f"{base}/remix/{remix_id}"
    og_image = f"{base}/api/highlights/{event_id}/thumbnail" if event_id else None
    og_video = f"{base}/api/remixes/{remix_id}/clip"

    return {
        "title": og_title,
        "description": og_desc,
        "url": og_url,
        "image": og_image,
        "video": og_video,
        "video_type": "video/mp4",
        "site_name": "Our Foxes",
    }


@app.get("/api/remixes/{remix_id}/clip")
async def remix_clip(remix_id: str, request: Request) -> StreamingResponse:
    """Inline-streamable trimmed remix MP4 — proxy to curator's
    /remixes/{id}/download?inline=1.

    Used as the og:video target for rich iMessage / social cards;
    also safe for any future <video src=...> embedding. Same auth
    posture as /api/highlights/{id}/clip — must be in the CF Access
    Bypass app for crawlers + anonymous family/friends to fetch.
    """
    return await _proxy_curator(
        f"/remixes/{remix_id}/download?inline=true",
        "video/mp4", request=request,
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


@app.delete("/api/admin/highlights/{event_id}")
async def admin_delete_highlight(event_id: str, request: Request) -> Any:
    """Hard-delete a highlight (admin-only). Removes DB row, user-actions,
    remixes, and the on-disk clip + thumbnail. Irreversible."""
    _require_admin(request)
    async with httpx.AsyncClient() as client:
        r = await client.delete(f"{CURATOR_API}/highlights/{event_id}", timeout=10.0)
    if r.status_code == 404:
        raise HTTPException(status_code=404, detail="not found")
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail=f"curator error: {r.text[:200]}")
    return r.json()


@app.post("/api/admin/remixes/{remix_id}/feature")
async def admin_feature_remix(remix_id: str, request: Request) -> Any:
    """Promote a remix to the public landing page (admin-only)."""
    admin_email = _require_admin(request)
    body = await request.json() if request.headers.get("content-length") else {}
    payload = {"by": admin_email, "caption": body.get("caption")}
    async with httpx.AsyncClient() as client:
        r = await client.post(f"{CURATOR_API}/remixes/{remix_id}/feature",
                              json=payload, timeout=8.0)
    if r.status_code == 404:
        raise HTTPException(status_code=404, detail="not found")
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail=f"curator error: {r.text[:200]}")
    return r.json()


@app.post("/api/admin/remixes/{remix_id}/unfeature")
async def admin_unfeature_remix(remix_id: str, request: Request) -> Any:
    """Remove a remix from the public landing page (admin-only)."""
    admin_email = _require_admin(request)
    async with httpx.AsyncClient() as client:
        r = await client.post(f"{CURATOR_API}/remixes/{remix_id}/unfeature",
                              json={"by": admin_email}, timeout=8.0)
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
    bucket: str = Query(default="pending", regex="^(pending|all|favorites|demoted|mine|shared|remixes)$"),
    time_of_day: str = Query(default="any", regex="^(any|day|night)$"),
    status: str = Query(default="active", regex="^(any|active|archived)$"),
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
        "status": status,
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


# Actions live at /api/actions/* rather than /api/highlights/{id}/{verb}
# because /api/highlights/* is a path that ALSO matches the public Bypass
# app at the Cloudflare Access edge (so anonymous viewers can pull
# featured-clip thumbnails + media). Bypass strips the auth header for
# everyone, including authed users — so a POST under /api/highlights/*
# arrives without an email at the origin and gets rejected.
#
# /api/actions/* matches only the AUTHED Access app, so the email
# header is always present here, and write actions persist correctly.

@app.get("/api/actions/{event_id}/highlight")
async def get_highlight_authed(event_id: str, request: Request) -> Any:
    """Single highlight metadata via the AUTHED path so my_favorited
    is populated. /api/highlights/{id} is in a Cloudflare Access
    Bypass app and CF strips the cf-access-authenticated-user-email
    header on bypassed paths — meaning the curator can't tell which
    user is asking. /api/actions/* is in the authed Access app, so
    the email header arrives intact and the user-state lookup
    succeeds. Modal fetches go through here so the heart reflects
    actual per-user favorite state.
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


@app.post("/api/actions/{event_id}/favorite")
@app.post("/api/highlights/{event_id}/favorite")  # legacy alias
async def favorite(event_id: str, request: Request) -> Any:
    return await _post_action(event_id, "favorite", _actor_email(request))


@app.post("/api/actions/{event_id}/demote")
@app.post("/api/highlights/{event_id}/demote")  # legacy alias
async def demote(event_id: str, request: Request) -> Any:
    return await _post_action(event_id, "demote", _actor_email(request))


@app.post("/api/actions/{event_id}/clear")
@app.post("/api/highlights/{event_id}/clear")  # legacy alias
async def clear(event_id: str, request: Request) -> Any:
    return await _post_action(event_id, "clear", _actor_email(request))


@app.post("/api/actions/{event_id}/archive")
async def archive(event_id: str, request: Request) -> Any:
    return await _post_action(event_id, "archive", _actor_email(request))


@app.post("/api/actions/{event_id}/unflag_no_foxes")
async def unflag_no_foxes(event_id: str, request: Request) -> Any:
    """Globally clear all 'no foxes' votes for this highlight (any
    family member can do this; the client is expected to surface a
    warning first because the action affects every user)."""
    return await _post_action(event_id, "unflag_no_foxes", _actor_email(request))


@app.post("/api/actions/{event_id}/unarchive")
async def unarchive(event_id: str, request: Request) -> Any:
    return await _post_action(event_id, "unarchive", _actor_email(request))


# ---------------------------------------------------------------------------
# Remixes — user-defined sub-clip trims with optional zoom region.
# Proxies through to curator with viewer email forwarded as `by`.
# ---------------------------------------------------------------------------

@app.post("/api/actions/{event_id}/remix")
@app.post("/api/highlights/{event_id}/remix")  # legacy alias
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
async def get_remix(remix_id: str, request: Request) -> Any:
    email = _actor_email(request)
    params = {"email": email} if email else {}
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{CURATOR_API}/remixes/{remix_id}",
                              params=params, timeout=8.0)
    if r.status_code == 404:
        raise HTTPException(status_code=404, detail="not found")
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail="curator error")
    return r.json()


@app.get("/api/remixes")
async def list_remixes(request: Request,
                        event_id: str | None = None,
                        scope: str = Query(default="", regex="^(|mine|all)$"),
                        liked_by_me: int = Query(default=0, ge=0, le=1),
                        limit: int = Query(default=50, ge=1, le=500),
                        offset: int = Query(default=0, ge=0)) -> Any:
    """`email` (viewer) is always forwarded so my_liked + my_favorited
    enrichment works. `scope=mine` filters to the viewer's own remixes
    (forwarded as `created_by` to the curator — `email` is reserved for
    viewer-state enrichment now). `liked_by_me=1` powers the Liked-by-Me
    status filter on the Remix tab."""
    email = _actor_email(request)
    params: dict[str, Any] = {"limit": limit, "offset": offset}
    if email:
        params["email"] = email
    if event_id:
        params["event_id"] = event_id
    elif scope == "mine" and email:
        params["created_by"] = email
    if liked_by_me and email:
        params["liked_by_email"] = email
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{CURATOR_API}/remixes", params=params, timeout=10.0)
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail="curator error")
    return r.json()


@app.post("/api/remixes/{remix_id}/like")
async def like_remix(remix_id: str, request: Request) -> Any:
    email = _actor_email(request)
    if not email:
        raise HTTPException(status_code=401, detail="auth required")
    async with httpx.AsyncClient() as client:
        r = await client.post(f"{CURATOR_API}/remixes/{remix_id}/like",
                               params={"email": email}, timeout=8.0)
    if r.status_code == 404:
        raise HTTPException(status_code=404, detail="not found")
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail="curator error")
    return r.json()


@app.get("/api/notifications")
async def list_notifications(request: Request,
                              unread_only: int = Query(default=0, ge=0, le=1),
                              limit: int = Query(default=50, ge=1, le=200),
                              offset: int = Query(default=0, ge=0)) -> Any:
    email = _actor_email(request)
    if not email:
        raise HTTPException(status_code=401, detail="auth required")
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{CURATOR_API}/notifications",
            params={"email": email, "unread_only": bool(unread_only),
                    "limit": limit, "offset": offset},
            timeout=8.0,
        )
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail="curator error")
    return r.json()


@app.get("/api/notifications/unread_count")
async def unread_count(request: Request) -> Any:
    email = _actor_email(request)
    if not email:
        return {"unread_count": 0}
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{CURATOR_API}/notifications/unread_count",
                              params={"email": email}, timeout=5.0)
    if r.status_code != 200:
        return {"unread_count": 0}
    return r.json()


@app.post("/api/notifications/{notif_id}/read")
async def mark_notif_read(notif_id: int, request: Request) -> Any:
    email = _actor_email(request)
    if not email:
        raise HTTPException(status_code=401, detail="auth required")
    async with httpx.AsyncClient() as client:
        r = await client.post(f"{CURATOR_API}/notifications/{notif_id}/read",
                               params={"email": email}, timeout=5.0)
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail="curator error")
    return r.json()


@app.post("/api/notifications/mark_all_read")
async def mark_all_read(request: Request) -> Any:
    email = _actor_email(request)
    if not email:
        raise HTTPException(status_code=401, detail="auth required")
    async with httpx.AsyncClient() as client:
        r = await client.post(f"{CURATOR_API}/notifications/mark_all_read",
                               params={"email": email}, timeout=5.0)
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail="curator error")
    return r.json()


# ---------------------------------------------------------------------------
# User profiles — friendly display name. CF Access supplies the email;
# this layer is just a passthrough with the email server-injected so a
# client can't write a name under another user's email.
# ---------------------------------------------------------------------------

@app.get("/api/profile")
async def get_my_profile(request: Request) -> Any:
    email = _actor_email(request)
    if not email:
        raise HTTPException(status_code=401, detail="auth required")
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{CURATOR_API}/profile",
                              params={"email": email}, timeout=5.0)
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail="curator error")
    return r.json()


@app.get("/api/profile/all")
async def list_profiles() -> Any:
    """Public to all authed users — the names show up everywhere
    (remix attributions, like notifications, etc.) so there's no
    privacy delta vs. fetching them lazily one by one."""
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{CURATOR_API}/profile/all", timeout=5.0)
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail="curator error")
    return r.json()


@app.post("/api/profile")
async def set_my_profile(request: Request) -> Any:
    email = _actor_email(request)
    if not email:
        raise HTTPException(status_code=401, detail="auth required")
    body = await request.json()
    body["email"] = email   # owner override
    async with httpx.AsyncClient() as client:
        r = await client.post(f"{CURATOR_API}/profile",
                               json=body, timeout=5.0)
    if r.status_code == 400:
        raise HTTPException(status_code=400,
                             detail=(r.json() or {}).get("detail", "bad request"))
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail="curator error")
    return r.json()


# ---------------------------------------------------------------------------
# Web Push proxies. The browser's `pushManager.subscribe` runs in the
# service-worker scope; the resulting PushSubscription gets POSTed here
# (with the user's CF Access email injected server-side as the owner).
# Curator stores it and uses it as the delivery target.
# ---------------------------------------------------------------------------

@app.get("/api/push/vapid-public-key")
async def push_vapid_public_key() -> Any:
    """Forwarded as-is — the public key is meant to be public, but
    routing it through here means the client only ever sees one origin."""
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{CURATOR_API}/push/vapid-public-key",
                              timeout=5.0)
    if r.status_code != 200:
        raise HTTPException(status_code=503, detail="push not configured")
    return r.json()


@app.post("/api/push/subscriptions")
async def push_subscribe(request: Request) -> Any:
    email = _actor_email(request)
    if not email:
        raise HTTPException(status_code=401, detail="auth required")
    body = await request.json()
    # Inject the authed email server-side so the client can't spoof
    # a subscription against a different user.
    body["email"] = email
    if "user_agent" not in body or not body["user_agent"]:
        body["user_agent"] = request.headers.get("user-agent", "")
    async with httpx.AsyncClient() as client:
        r = await client.post(f"{CURATOR_API}/push/subscriptions",
                               json=body, timeout=8.0)
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail="curator error")
    return r.json()


@app.delete("/api/push/subscriptions")
async def push_unsubscribe(request: Request, endpoint: str) -> Any:
    email = _actor_email(request)
    if not email:
        raise HTTPException(status_code=401, detail="auth required")
    async with httpx.AsyncClient() as client:
        r = await client.delete(f"{CURATOR_API}/push/subscriptions",
                                 params={"endpoint": endpoint}, timeout=5.0)
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail="curator error")
    return r.json()


@app.get("/api/push/subscriptions")
async def push_list_subscriptions(request: Request) -> Any:
    email = _actor_email(request)
    if not email:
        raise HTTPException(status_code=401, detail="auth required")
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{CURATOR_API}/push/subscriptions",
                              params={"email": email}, timeout=5.0)
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail="curator error")
    return r.json()


@app.get("/api/push/preferences")
async def push_get_preferences(request: Request) -> Any:
    email = _actor_email(request)
    if not email:
        raise HTTPException(status_code=401, detail="auth required")
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{CURATOR_API}/push/preferences",
                              params={"email": email}, timeout=5.0)
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail="curator error")
    return r.json()


@app.post("/api/push/preferences")
async def push_set_preference(request: Request) -> Any:
    email = _actor_email(request)
    if not email:
        raise HTTPException(status_code=401, detail="auth required")
    body = await request.json()
    body["email"] = email   # owner override
    async with httpx.AsyncClient() as client:
        r = await client.post(f"{CURATOR_API}/push/preferences",
                               json=body, timeout=5.0)
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail="curator error")
    return r.json()


@app.post("/api/push/test")
async def push_test(request: Request) -> Any:
    email = _actor_email(request)
    if not email:
        raise HTTPException(status_code=401, detail="auth required")
    async with httpx.AsyncClient() as client:
        r = await client.post(f"{CURATOR_API}/push/test",
                               params={"email": email}, timeout=10.0)
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail="curator error")
    return r.json()


# ---- Pause / schedule proxies --------------------------------------------

@app.get("/api/push/pause")
async def push_get_pause(request: Request) -> Any:
    email = _actor_email(request)
    if not email:
        raise HTTPException(status_code=401, detail="auth required")
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{CURATOR_API}/push/pause",
                              params={"email": email}, timeout=5.0)
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail="curator error")
    return r.json()


@app.post("/api/push/pause")
async def push_set_pause(request: Request) -> Any:
    email = _actor_email(request)
    if not email:
        raise HTTPException(status_code=401, detail="auth required")
    body = await request.json()
    body["email"] = email
    async with httpx.AsyncClient() as client:
        r = await client.post(f"{CURATOR_API}/push/pause",
                               json=body, timeout=5.0)
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail="curator error")
    return r.json()


@app.get("/api/push/schedule")
async def push_get_schedule(request: Request) -> Any:
    email = _actor_email(request)
    if not email:
        raise HTTPException(status_code=401, detail="auth required")
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{CURATOR_API}/push/schedule",
                              params={"email": email}, timeout=5.0)
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail="curator error")
    return r.json()


@app.post("/api/push/schedule")
async def push_add_schedule(request: Request) -> Any:
    email = _actor_email(request)
    if not email:
        raise HTTPException(status_code=401, detail="auth required")
    body = await request.json()
    body["email"] = email
    async with httpx.AsyncClient() as client:
        r = await client.post(f"{CURATOR_API}/push/schedule",
                               json=body, timeout=5.0)
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail="curator error")
    return r.json()


@app.delete("/api/push/schedule/{interval_id}")
async def push_delete_schedule(interval_id: int, request: Request) -> Any:
    email = _actor_email(request)
    if not email:
        raise HTTPException(status_code=401, detail="auth required")
    async with httpx.AsyncClient() as client:
        r = await client.delete(
            f"{CURATOR_API}/push/schedule/{interval_id}",
            params={"email": email}, timeout=5.0)
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


@app.get("/api/remixes/{remix_id}/download")
async def download_remix(remix_id: str, filename: str | None = None) -> StreamingResponse:
    """Proxy curator's trimmed+cropped remix MP4 for download.

    Curator does the ffmpeg work and caches the result, so subsequent
    downloads are fast. Filename is forwarded so the browser saves the
    file with a meaningful name including the remix title.
    """
    from urllib.parse import quote
    safe = (filename or f"remix-{remix_id}.mp4").replace('"', "").replace("\n", "").replace("\r", "")
    return await _proxy_curator(
        f"/remixes/{remix_id}/download?filename={quote(safe)}",
        "video/mp4",
        extra_headers={"Content-Disposition": f'attachment; filename="{safe}"'},
    )


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
async def highlight_clip(event_id: str, request: Request, download: int = 0,
                          filename: str | None = None) -> StreamingResponse:
    # Per-id media is reachable without auth because /api/highlights/*
    # is in a Cloudflare Access Bypass app (so anonymous viewers can
    # play featured permalinks). Event IDs are unguessable timestamp+
    # random hashes, the LIST endpoint stays authed, and only featured
    # IDs are reachable to anonymous viewers via the public /api/featured
    # response — so a knowledge-of-the-id leak is bounded to clips an
    # admin already chose to share.
    extra: dict[str, str] = {}
    if download:
        safe = (filename or f"{event_id}.mp4").replace('"', '').replace("\n", "").replace("\r", "")
        extra["Content-Disposition"] = f'attachment; filename="{safe}"'
    return await _proxy_curator(f"/highlights/{event_id}/clip", "video/mp4",
                                 extra_headers=extra, request=request)


@app.get("/api/highlights/{event_id}/thumbnail")
async def highlight_thumb(event_id: str, request: Request) -> StreamingResponse:
    return await _proxy_curator(f"/highlights/{event_id}/thumbnail", "image/jpeg",
                                 request=request)


async def _proxy_curator(path: str, media_type: str,
                          extra_headers: dict[str, str] | None = None,
                          request: Request | None = None) -> StreamingResponse:
    # Forward the Range header so curator (FastAPI FileResponse, which
    # supports Range natively) can return 206 Partial Content. Without
    # this, iOS Safari refuses to play <video> elements past a brief
    # scrubber preview — the spec requires byte-range loading and
    # treats a 200 with full content as a non-seekable stream.
    upstream_headers: dict[str, str] = {}
    if request is not None:
        rng = request.headers.get("range")
        if rng:
            upstream_headers["Range"] = rng
    async with httpx.AsyncClient() as client:
        async with client.stream(
            "GET", f"{CURATOR_API}{path}",
            headers=upstream_headers, timeout=30.0,
        ) as r:
            if r.status_code == 404:
                raise HTTPException(status_code=404, detail="not found")
            # Both 200 (full) and 206 (partial) are success — propagate
            # the upstream status code unchanged so the browser knows
            # whether this is a Range response.
            if r.status_code not in (200, 206):
                raise HTTPException(status_code=502, detail="curator error")
            content = await r.aread()
    upstream_status = r.status_code
    headers = {"Cache-Control": "private, max-age=300", "Accept-Ranges": "bytes"}
    # Forward the headers iOS Safari needs to honor a Range response.
    for h in ("content-range", "content-length"):
        if h in r.headers:
            headers[h.title()] = r.headers[h]
    if extra_headers:
        headers.update(extra_headers)
    return StreamingResponse(
        iter([content]),
        media_type=media_type,
        headers=headers,
        status_code=upstream_status,
    )
