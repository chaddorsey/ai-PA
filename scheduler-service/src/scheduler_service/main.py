"""Application entrypoint for the scheduler service."""

from __future__ import annotations

from fastapi import FastAPI

from scheduler_service.logging_config import configure_logging, get_logger
from scheduler_service.routers import api_router
from scheduler_service.services.scheduler import scheduler_service, shutdown_scheduler
from scheduler_service.settings import settings


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""

    configure_logging(settings.log_level)
    logger = get_logger(__name__)
    logger.info("Starting scheduler service", app_name=settings.app_name)

    app = FastAPI(title=settings.app_name)

    @app.on_event("startup")
    async def on_startup() -> None:
        await scheduler_service.start()

    @app.on_event("shutdown")
    async def on_shutdown() -> None:
        await shutdown_scheduler()

    app.include_router(api_router, prefix="/v1")

    @app.get("/healthz")
    async def health_check() -> dict[str, str]:
        """Healthcheck endpoint."""

        return {"status": "ok"}

    return app


app = create_app()


