"""FastAPI entry point.

Single endpoint: POST /invoke. Health + status endpoints for ops.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import asdict

import structlog
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from letta_local_runner import __version__
from letta_local_runner.invoker import InvokeRequest, Invoker
from letta_local_runner.settings import load as load_settings

log = structlog.get_logger()


class InvokeBody(BaseModel):
    agent_id: str = Field(..., description="Local-mode agent id (agent-local-...)")
    message: str = Field(..., description="Message to send to the agent")
    conversation_id: str | None = Field(
        None,
        description="Conversation id; default cron-<agent_id>",
    )
    timeout: int | None = Field(
        None, ge=10, le=3600, description="Timeout seconds (default from settings)"
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = load_settings()
    settings.log_dir.mkdir(parents=True, exist_ok=True)
    app.state.settings = settings
    app.state.invoker = Invoker(settings)
    log.info(
        "runner_started",
        version=__version__,
        listen=f"{settings.listen_host}:{settings.listen_port}",
        backend_dir=str(settings.backend_dir),
        letta_bin=settings.letta_bin,
    )
    yield
    log.info("runner_stopped")


app = FastAPI(
    title="letta-local-runner",
    version=__version__,
    lifespan=lifespan,
)


@app.get("/health")
async def health():
    invoker: Invoker = app.state.invoker
    status = invoker.status()
    return {
        "status": "healthy",
        "version": __version__,
        "active": len(status["inflight"]),
    }


@app.get("/status")
async def status():
    invoker: Invoker = app.state.invoker
    return invoker.status()


@app.post("/invoke")
async def invoke(body: InvokeBody):
    invoker: Invoker = app.state.invoker
    req = InvokeRequest(
        agent_id=body.agent_id,
        message=body.message,
        conversation_id=body.conversation_id,
        timeout=body.timeout,
    )
    result = await invoker.invoke(req)
    if result.status == "timeout":
        raise HTTPException(status_code=408, detail=asdict(result))
    if result.status == "error":
        raise HTTPException(status_code=500, detail=asdict(result))
    return asdict(result)
