"""API router definitions."""

from fastapi import APIRouter

from scheduler_service.routes import health, jobs


api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(jobs.router)


