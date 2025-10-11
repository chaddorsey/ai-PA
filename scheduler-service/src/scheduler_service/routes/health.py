"""Health endpoints."""

from fastapi import APIRouter

from scheduler_service.services.metrics import get_metrics

router = APIRouter(prefix="/v1/health", tags=["health"])


@router.get("/ready")
async def readiness_probe() -> dict[str, str]:
    return {"status": "ready"}


@router.get("/metrics")
async def metrics_probe() -> dict[str, object]:
    return {"metrics": get_metrics()}


@router.get("/healthz")
async def legacy_health() -> dict[str, str]:
    return await readiness_probe()


