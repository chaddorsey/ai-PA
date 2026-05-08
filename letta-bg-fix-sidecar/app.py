"""
letta-bg-fix-sidecar — transparent proxy in front of Letta that rewrites
`stream_tokens: true` → `stream_tokens: false` on
POST /v1/conversations/{id}/messages.

Issue #99: pa-web-ui's letta-code v0.24.10 subprocess sets
stream_tokens:true on the conversations endpoint. With Letta v0.16.7 +
letta_v1_agent + chatgpt_oauth/gpt-5.4, that combination silently
drops assistant content — runs complete cleanly (stop_reason=end_turn,
real completion tokens) but persist only the user_message. Setting
stream_tokens:false makes assistant_message persist every time.

Bisected 2026-05-08 (3x baseline STALLED, 3x stream_tokens=false
PERSISTED). The `background` flag had no effect on persistence in
either direction; the offending field is stream_tokens.

This sidecar keeps letta-code v0.24.10 + memfs working while the
upstream bug is unaddressed. All other traffic passes through unchanged.

Health check: GET /health → 200 OK.
"""

import asyncio
import json
import logging
import os
from typing import Any

from aiohttp import ClientSession, ClientTimeout, web

UPSTREAM = os.environ.get("LETTA_UPSTREAM_URL", "http://letta:8283")
PORT = int(os.environ.get("PORT", "8284"))
# Long enough to absorb any reasonable MC turn including multi-step tool chains.
TIMEOUT = ClientTimeout(total=600, connect=10)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("letta-bg-fix")


async def health(request: web.Request) -> web.Response:
    return web.Response(text="ok", status=200)


def maybe_rewrite_body(method: str, path: str, body: bytes) -> tuple[bytes, bool]:
    """If this is a POST /v1/conversations/{id}/messages with
    stream_tokens:true, rewrite to stream_tokens:false. Otherwise pass
    body through unchanged.

    Returns (body, was_rewritten).
    """
    if method != "POST" or not body:
        return body, False
    # Match /v1/conversations/{id}/messages (NOT /messages/preview-raw-payload, etc.)
    parts = path.strip("/").split("/")
    if len(parts) != 4:
        return body, False
    if parts[0] != "v1" or parts[1] != "conversations" or parts[3] != "messages":
        return body, False

    try:
        payload: dict[str, Any] = json.loads(body)
    except (ValueError, TypeError):
        return body, False
    if not isinstance(payload, dict) or payload.get("stream_tokens") is not True:
        return body, False

    payload["stream_tokens"] = False
    return json.dumps(payload).encode(), True


async def proxy(request: web.Request) -> web.StreamResponse:
    tail = request.match_info.get("tail", "")
    url = f"{UPSTREAM}/{tail}"
    if request.query_string:
        url += f"?{request.query_string}"

    body = await request.read() if request.can_read_body else b""
    is_conv_msg = (
        request.method == "POST"
        and tail.startswith("v1/conversations/")
        and tail.endswith("/messages")
    )
    if is_conv_msg and body:
        try:
            with open("/tmp/last-conv-msg-body.json", "wb") as f:
                f.write(body)
            log.info(
                "conv-msg body captured to /tmp/last-conv-msg-body.json (%d bytes, keys=%s)",
                len(body),
                list(json.loads(body).keys()),
            )
        except Exception as e:
            log.warning("failed to capture body: %s", e)
    body, rewritten = maybe_rewrite_body(request.method, "/" + tail, body)
    if rewritten:
        log.info("rewrote stream_tokens:true → false for %s %s", request.method, tail)

    # Forward all headers except hop-by-hop / size-affecting ones.
    skip = {"host", "content-length", "connection", "keep-alive",
            "proxy-authenticate", "proxy-authorization", "te",
            "trailers", "transfer-encoding", "upgrade"}
    headers = {k: v for k, v in request.headers.items() if k.lower() not in skip}
    if rewritten:
        headers["Content-Length"] = str(len(body))

    try:
        session = request.app["http_session"]
        async with session.request(
            request.method,
            url,
            data=body if body else None,
            headers=headers,
            allow_redirects=False,
            timeout=TIMEOUT,
        ) as upstream_resp:
            resp_headers = {
                k: v
                for k, v in upstream_resp.headers.items()
                if k.lower() not in {"content-length", "transfer-encoding", "connection"}
            }
            resp = web.StreamResponse(status=upstream_resp.status, headers=resp_headers)
            await resp.prepare(request)
            async for chunk in upstream_resp.content.iter_any():
                if not chunk:
                    continue
                await resp.write(chunk)
            await resp.write_eof()
            return resp
    except asyncio.CancelledError:
        log.info("client disconnected mid-stream %s %s", request.method, tail)
        raise
    except Exception as e:
        log.warning("upstream error %s %s: %s", request.method, tail, e)
        return web.Response(status=502, text=f"sidecar upstream error: {e}")


async def init_session(app: web.Application) -> None:
    app["http_session"] = ClientSession()


async def close_session(app: web.Application) -> None:
    await app["http_session"].close()


def make_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/health", health)
    app.router.add_route("*", "/{tail:.*}", proxy)
    app.on_startup.append(init_session)
    app.on_cleanup.append(close_session)
    return app


if __name__ == "__main__":
    log.info("letta-bg-fix-sidecar listening on :%d → upstream %s", PORT, UPSTREAM)
    web.run_app(make_app(), host="0.0.0.0", port=PORT, access_log=None)
