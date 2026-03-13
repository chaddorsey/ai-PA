import asyncio
import logging
from fastapi import APIRouter, Depends, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from .database import get_session
from .settings import Settings
from .github_client import GitHubClient
from .backfill import (
    backfill_stars, backfill_stargazers, get_backfill_status,
    refresh_stargazer_counts, refresh_changed_stargazers,
)
from .scoring import score_curators, get_top_curators
from .monitor import refresh_curator_events, get_discoveries
from .digest import generate_digest
from twitter_cli.client import TwitterClient
from .twitter_ingest import ingest_bookmarks, get_ingest_status
from .twitter_backfill import fetch_tweet_likers
from .twitter_list_sync import sync_twitter_list

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


@router.post("/stargazers/refresh")
async def refresh_stargazers(background_tasks: BackgroundTasks):
    """Incrementally refresh stargazers: check for count changes, fetch new ones, rescore."""
    async def _refresh():
        import traceback
        from .database import AsyncSessionFactory
        client = GitHubClient(settings)
        try:
            async with AsyncSessionFactory() as session:
                print("Stargazer refresh: checking counts...", flush=True)
                counts = await refresh_stargazer_counts(session, client)
                print(f"Stargazer refresh: {counts}", flush=True)

                if counts["counts_changed"] > 0:
                    print("Stargazer refresh: fetching new stargazers...", flush=True)
                    gazers = await refresh_changed_stargazers(session, client)
                    print(f"Stargazer refresh: {gazers}", flush=True)

                    print("Stargazer refresh: rescoring...", flush=True)
                    scored = await score_curators(session, platform="github")
                    print(f"Stargazer refresh: scored {scored} curators", flush=True)
                else:
                    print("Stargazer refresh: no changes detected, skipping fetch and rescore", flush=True)

                print("Stargazer refresh complete.", flush=True)
        except Exception as e:
            print(f"Stargazer refresh failed: {e}\n{traceback.format_exc()}", flush=True)
        finally:
            await client.close()

    background_tasks.add_task(_refresh)
    return {"status": "started", "pipeline": "stargazer-refresh"}


@router.post("/score")
async def run_scoring(platform: str = "github", session: AsyncSession = Depends(get_session)):
    count = await score_curators(session, platform)
    return {"status": "ok", "curators_scored": count}


@router.get("/curators")
async def list_curators(top_k: int = 20, platform: str = "github", session: AsyncSession = Depends(get_session)):
    return await get_top_curators(session, top_k, platform)


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
    client = GitHubClient(settings)
    try:
        return await get_discoveries(session, since_days, client=client)
    finally:
        await client.close()


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


# --- Twitter Curator Routes ---


async def _run_twitter_daily():
    """Daily Twitter curator pipeline: ingest → fetch likers → score → sync list."""
    from .database import AsyncSessionFactory
    client = TwitterClient(settings.smaug_config_path)
    try:
        async with AsyncSessionFactory() as session:
            logger.info("Twitter daily: ingesting new bookmarks...")
            ingested = await ingest_bookmarks(session, settings)
            logger.info(f"Twitter daily: ingested {ingested} new bookmarks")

            logger.info("Twitter daily: fetching likers...")
            stats = await fetch_tweet_likers(session, client)
            logger.info(f"Twitter daily: {stats}")

            logger.info("Twitter daily: scoring curators...")
            scored = await score_curators(session, platform="twitter")
            logger.info(f"Twitter daily: scored {scored} curators")

            logger.info("Twitter daily: syncing list...")
            sync_stats = await sync_twitter_list(session, client, settings)
            logger.info(f"Twitter daily: list sync {sync_stats}")

            logger.info("Twitter daily run complete.")
    except Exception as e:
        logger.error(f"Twitter daily run failed: {e}", exc_info=True)
    finally:
        client.close()


@router.post("/twitter/run")
async def twitter_daily_run(background_tasks: BackgroundTasks):
    """Run the full daily Twitter curator pipeline in background."""
    background_tasks.add_task(_run_twitter_daily)
    return {"status": "started", "pipeline": "twitter-daily"}


@router.post("/twitter/ingest")
async def twitter_ingest(session: AsyncSession = Depends(get_session)):
    """Ingest new bookmarks from Smaug archive."""
    count = await ingest_bookmarks(session, settings)
    return {"status": "ok", "ingested": count}


@router.get("/twitter/status")
async def twitter_status(session: AsyncSession = Depends(get_session)):
    """Get Twitter ingestion and likers-fetch status."""
    return await get_ingest_status(session)


@router.post("/twitter/fetch-likers")
async def twitter_fetch_likers(background_tasks: BackgroundTasks):
    """Fetch likers for unfetched tweets in background."""
    async def _fetch():
        import traceback
        from .database import AsyncSessionFactory
        client = TwitterClient(settings.smaug_config_path)
        try:
            async with AsyncSessionFactory() as session:
                await fetch_tweet_likers(session, client)
        except Exception as e:
            print(f"Background fetch-likers failed: {e}\n{traceback.format_exc()}", flush=True)
        finally:
            client.close()
    background_tasks.add_task(_fetch)
    return {"status": "started"}


@router.post("/twitter/score")
async def twitter_score(session: AsyncSession = Depends(get_session)):
    """Score Twitter curators."""
    count = await score_curators(session, platform="twitter")
    return {"status": "ok", "curators_scored": count}


@router.get("/twitter/curators")
async def twitter_curators(top_k: int = 50, session: AsyncSession = Depends(get_session)):
    """List top Twitter curators."""
    return await get_top_curators(session, top_k, platform="twitter")


@router.post("/twitter/sync-list")
async def twitter_sync_list(session: AsyncSession = Depends(get_session)):
    """Sync the Twitter list with top curators."""
    client = TwitterClient(settings.smaug_config_path)
    try:
        stats = await sync_twitter_list(session, client, settings)
        return {"status": "ok", **stats}
    finally:
        client.close()


# --- Twitter Agent Access Routes ---


@router.get("/twitter/feed")
async def twitter_feed(count: int = 20):
    """Fetch home timeline for agent access."""
    client = TwitterClient(settings.smaug_config_path)
    try:
        tweets = await asyncio.to_thread(client.get_home_timeline, count)
        return {"status": "ok", "tweets": tweets}
    finally:
        client.close()


@router.get("/twitter/user/{handle}")
async def twitter_user_tweets(handle: str, count: int = 20):
    """Fetch a user's tweets for agent access."""
    client = TwitterClient(settings.smaug_config_path)
    try:
        tweets = await asyncio.to_thread(client.get_user_tweets, handle, count)
        return {"status": "ok", "handle": handle, "tweets": tweets}
    finally:
        client.close()


@router.get("/twitter/search")
async def twitter_search(q: str, count: int = 20):
    """Search tweets for agent access."""
    client = TwitterClient(settings.smaug_config_path)
    try:
        tweets = await asyncio.to_thread(client.search_tweets, q, count)
        return {"status": "ok", "query": q, "tweets": tweets}
    finally:
        client.close()


@router.get("/twitter/tweet/{tweet_id}")
async def twitter_tweet_detail(tweet_id: str):
    """Fetch a tweet and its replies for agent access."""
    client = TwitterClient(settings.smaug_config_path)
    try:
        data = await asyncio.to_thread(client.get_tweet_detail, tweet_id)
        return {"status": "ok", "data": data}
    finally:
        client.close()


@router.get("/twitter/bookmarks")
async def twitter_bookmarks_read(count: int = 20):
    """Fetch bookmarked tweets via API for agent access."""
    client = TwitterClient(settings.smaug_config_path)
    try:
        tweets = await asyncio.to_thread(client.get_bookmarks, count)
        return {"status": "ok", "tweets": tweets}
    finally:
        client.close()


@router.get("/twitter/lists")
async def twitter_my_lists():
    """Fetch the authenticated user's owned lists."""
    client = TwitterClient(settings.smaug_config_path)
    try:
        lists = await asyncio.to_thread(client.get_my_lists)
        return {"status": "ok", "lists": lists}
    finally:
        client.close()


@router.get("/twitter/list/{list_id}/members")
async def twitter_list_members(list_id: str, count: int = 100):
    """Fetch list members for agent access."""
    client = TwitterClient(settings.smaug_config_path)
    try:
        members = await asyncio.to_thread(client.get_list_members, list_id, count)
        return {"status": "ok", "list_id": list_id, "members": members}
    finally:
        client.close()


@router.get("/twitter/list/{list_id}/tweets")
async def twitter_list_tweets(list_id: str, count: int = 20):
    """Fetch recent tweets from a list timeline."""
    client = TwitterClient(settings.smaug_config_path)
    try:
        tweets = await asyncio.to_thread(client.get_list_tweets, list_id, count)
        return {"status": "ok", "list_id": list_id, "tweets": tweets}
    finally:
        client.close()


@router.post("/twitter/list/create")
async def twitter_create_list(name: str, description: str = "", private: bool = True):
    """Create a new Twitter list."""
    client = TwitterClient(settings.smaug_config_path)
    try:
        list_id = await asyncio.to_thread(client.create_list, name, description, private)
        if not list_id:
            return {"status": "error", "error": "Failed to create list"}
        return {"status": "ok", "list_id": list_id, "name": name}
    finally:
        client.close()


@router.post("/twitter/bookmark/{tweet_id}")
async def twitter_bookmark_tweet(tweet_id: str):
    """Bookmark a tweet for agent access."""
    client = TwitterClient(settings.smaug_config_path)
    try:
        ok = await asyncio.to_thread(client.add_bookmark, tweet_id)
        return {"status": "ok" if ok else "error", "tweet_id": tweet_id}
    finally:
        client.close()


@router.post("/twitter/list-add")
async def twitter_list_add(list_id: str, handle: str):
    """Add a user to a Twitter list."""
    client = TwitterClient(settings.smaug_config_path)
    try:
        user_id = await asyncio.to_thread(client.get_user_rest_id, handle)
        if not user_id:
            return {"status": "error", "error": f"User not found: {handle}"}
        ok = await asyncio.to_thread(client.add_list_member, list_id, user_id)
        return {"status": "ok" if ok else "error", "handle": handle, "list_id": list_id}
    finally:
        client.close()


@router.post("/twitter/list-remove")
async def twitter_list_remove(list_id: str, handle: str):
    """Remove a user from a Twitter list."""
    client = TwitterClient(settings.smaug_config_path)
    try:
        user_id = await asyncio.to_thread(client.get_user_rest_id, handle)
        if not user_id:
            return {"status": "error", "error": f"User not found: {handle}"}
        ok = await asyncio.to_thread(client.remove_list_member, list_id, user_id)
        return {"status": "ok" if ok else "error", "handle": handle, "list_id": list_id}
    finally:
        client.close()
