"""PA Routing Handler - FastAPI application."""

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from pa_routing.database import close_db, init_db
from pa_routing.routers import routing
from pa_routing.services.session_store import session_store
from pa_routing.routers.routing import set_supabase_client as set_routing_supabase_client
from pa_routing.settings import settings

# Configure structured logging
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
    """Application lifespan handler."""
    logger.info("pa_routing_starting", letta_url=settings.letta_base_url)

    # Initialize database connection
    try:
        await init_db()
        logger.info("database_connected")
    except Exception as e:
        logger.warning("database_connection_failed", error=str(e))

    # Initialize Supabase for session persistence and conversation lookups
    if settings.supabase_url and settings.supabase_service_key:
        try:
            from supabase import create_client
            supabase = create_client(settings.supabase_url, settings.supabase_service_key)
            session_store.set_supabase_client(supabase)
            set_routing_supabase_client(supabase)
            logger.info("session_store_initialized", persistence="supabase")
        except Exception as e:
            logger.warning("supabase_init_failed", error=str(e), persistence="memory_only")
    else:
        logger.info("session_store_initialized", persistence="memory_only")

    yield

    await close_db()
    logger.info("pa_routing_shutdown")


app = FastAPI(
    title="PA Routing Handler",
    description="Message routing service for the PA ecosystem",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS middleware for web UI access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Include API routers
app.include_router(routing.router, prefix="/v1")


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy", "service": "pa-routing-handler"}
