import asyncio
import logging
from fastapi import APIRouter, Depends, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from .database import get_session
from .settings import Settings
from .github_client import GitHubClient
from .backfill import backfill_stars, backfill_stargazers, get_backfill_status
from .scoring import score_curators, get_top_curators
from .monitor import refresh_curator_events, get_discoveries
from .digest import generate_digest

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1")
settings = Settings()


async def _run_backfill(since_days: int):
    """Run full backfill in background."""
    from .database import AsyncSessionFactory
    client = GitHubClient(settings)
    try:
        async with AsyncSessionFactory() as session:
            logger.info("Starting stars backfill...")
            await backfill_stars(session, client, since_days=since_days)
            logger.info("Starting stargazers backfill...")
            await backfill_stargazers(session, client)
            logger.info("Scoring curators...")
            await score_curators(session)
            logger.info("Backfill complete.")
    finally:
        await client.close()


@router.post("/backfill")
async def start_backfill(background_tasks: BackgroundTasks, since_days: int = 365):
    background_tasks.add_task(_run_backfill, since_days)
    return {"status": "started", "since_days": since_days}


@router.get("/backfill/status")
async def backfill_status(session: AsyncSession = Depends(get_session)):
    return await get_backfill_status(session)


@router.post("/score")
async def run_scoring(session: AsyncSession = Depends(get_session)):
    count = await score_curators(session)
    return {"status": "ok", "curators_scored": count}


@router.get("/curators")
async def list_curators(top_k: int = 20, session: AsyncSession = Depends(get_session)):
    return await get_top_curators(session, top_k)


@router.post("/monitor/refresh")
async def monitor_refresh(session: AsyncSession = Depends(get_session)):
    client = GitHubClient(settings)
    try:
        count = await refresh_curator_events(session, client)
        return {"status": "ok", "new_events": count}
    finally:
        await client.close()


@router.get("/discoveries")
async def discoveries(since_days: int = 7, session: AsyncSession = Depends(get_session)):
    return await get_discoveries(session, since_days)


@router.get("/digest")
async def digest(since_days: int = 7, session: AsyncSession = Depends(get_session)):
    md = await generate_digest(session, since_days)
    return {"status": "ok", "digest": md}


@router.post("/digest/deliver")
async def deliver_digest(since_days: int = 7, session: AsyncSession = Depends(get_session)):
    """Generate digest and post to Slack."""
    import httpx
    md = await generate_digest(session, since_days)
    async with httpx.AsyncClient() as http:
        resp = await http.post(
            settings.slackbot_notify_url,
            json={
                "text": "Weekly Curator Radar Digest",
                "detail": md,
                "user_slack_id": settings.slack_user_id,
            },
        )
    return {"status": "ok", "slack_response": resp.status_code}
