"""Application entrypoint for the Gmail watch service."""

from __future__ import annotations

from contextlib import asynccontextmanager

import structlog
from fastapi import Depends, FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from gmail_watch.database import get_session
from gmail_watch.mcp_server import router as mcp_router
from gmail_watch.scheduler import watch_scheduler
from gmail_watch.services.watch_manager import WatchManager
from gmail_watch.settings import settings

structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
)

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle."""
    logger.info("Starting Gmail watch service")
    await watch_scheduler.start()
    yield
    logger.info("Shutting down Gmail watch service")
    await watch_scheduler.stop()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(title=settings.app_name, lifespan=lifespan)

    @app.get("/health")
    async def health_check() -> dict:
        """Health check endpoint."""
        return {
            "status": "ok",
            "service": settings.app_name,
            "scheduler_running": watch_scheduler.is_running,
        }

    @app.get("/v1/status")
    async def get_status(session: AsyncSession = Depends(get_session)) -> dict:
        """Get current watch status."""
        manager = WatchManager(session=session)
        sync_status = await manager.get_sync_status()
        return {"status": "ok", **sync_status}

    @app.post("/v1/admin/force-pull")
    async def force_pull(session: AsyncSession = Depends(get_session)) -> dict:
        """Manually trigger a Pub/Sub pull."""
        manager = WatchManager(session=session)
        result = await manager.process_notifications()
        return result

    @app.post("/v1/admin/renew-watch")
    async def renew_watch(session: AsyncSession = Depends(get_session)) -> dict:
        """Manually renew Gmail watch subscription."""
        manager = WatchManager(session=session)
        result = await manager.initialize_watch()
        return result

    app.include_router(mcp_router)

    return app


app = create_app()
