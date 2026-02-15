import asyncio
import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse

from app.checkpoint import CheckpointDB
from app.notifications import NotificationManager
from app.runner import BackfillRunner

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

# Global references set during lifespan
_db: Optional[CheckpointDB] = None
_runner: Optional[BackfillRunner] = None
_notifications: Optional[NotificationManager] = None
_sse_queues: list[asyncio.Queue] = []


def create_app(db_path: str = "data/backfill.db") -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        global _db, _runner, _notifications
        _db = CheckpointDB(db_path)
        await _db.initialize()

        _notifications = NotificationManager(_db)
        await _notifications.initialize()

        _runner = BackfillRunner(db=_db, notifications=_notifications)
        _runner.on_event = _broadcast_sse

        # Auto-resume if was running before crash
        state = await _db.get_runner_state()
        if state["state"] == "running":
            logger.info("Auto-resuming backfill from checkpoint")
            await _runner.start()

        yield

        await _runner.shutdown()
        await _db.close()

    app = FastAPI(title="Entity Backfill Service", lifespan=lifespan)

    # --- Health ---
    @app.get("/health")
    async def health():
        return {"status": "healthy", "service": "entity-backfill-service"}

    # --- Status ---
    @app.get("/api/status")
    async def status():
        return await _runner.get_status()

    # --- Controls ---
    @app.post("/api/start")
    async def start():
        return await _runner.start()

    @app.post("/api/pause")
    async def pause():
        return await _runner.pause()

    @app.post("/api/resume")
    async def resume():
        return await _runner.resume()

    @app.post("/api/retry-errors")
    async def retry_errors():
        count = await _db.retry_errors()
        return {"status": "ok", "retried": count}

    # --- Errors ---
    @app.get("/api/errors")
    async def errors(limit: int = 50):
        return await _db.get_errors(limit=limit)

    # --- SSE ---
    @app.get("/api/events")
    async def events(request: Request):
        queue: asyncio.Queue = asyncio.Queue()
        _sse_queues.append(queue)

        async def event_generator():
            try:
                while True:
                    if await request.is_disconnected():
                        break
                    try:
                        data = await asyncio.wait_for(queue.get(), timeout=30.0)
                        yield {"event": "progress", "data": json.dumps(data)}
                    except asyncio.TimeoutError:
                        yield {"event": "ping", "data": "{}"}
            finally:
                _sse_queues.remove(queue)

        return EventSourceResponse(event_generator())

    # --- Push ---
    @app.get("/api/push/vapid-key")
    async def vapid_key():
        keys = await _notifications.get_vapid_keys()
        return {"public_key": keys["public_key"]}

    @app.post("/api/push/subscribe")
    async def push_subscribe(request: Request):
        sub = await request.json()
        await _notifications.add_subscription(sub)
        return {"status": "subscribed"}

    @app.get("/api/push/test")
    async def push_test():
        await _notifications.send_notification(
            "Test Notification", "Push notifications are working!"
        )
        return {"status": "sent"}

    # --- Static PWA ---
    static_dir = Path(__file__).parent / "static"
    if static_dir.exists():
        index_file = static_dir / "index.html"
        sw_file = static_dir / "sw.js"
        manifest_file = static_dir / "manifest.json"

        if index_file.exists():
            @app.get("/", response_class=HTMLResponse)
            async def index():
                return index_file.read_text()

        if sw_file.exists():
            # Service worker must be served from root
            @app.get("/sw.js")
            async def service_worker():
                from fastapi.responses import Response
                return Response(
                    content=sw_file.read_text(),
                    media_type="application/javascript",
                )

        if manifest_file.exists():
            @app.get("/manifest.json")
            async def manifest():
                from fastapi.responses import Response
                return Response(
                    content=manifest_file.read_text(),
                    media_type="application/json",
                )

        # Only mount static files if there are actual files to serve
        if any(static_dir.iterdir()):
            app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    return app


async def _broadcast_sse(data: dict):
    for queue in _sse_queues:
        try:
            queue.put_nowait(data)
        except asyncio.QueueFull:
            pass


app = create_app()
