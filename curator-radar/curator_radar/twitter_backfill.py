"""
Fetch retweeters for bookmarked tweets via Twitter's Retweeters GraphQL endpoint.
Processes newest-first. Resumable via likers_fetched flag.
Note: Originally designed for Favoriters (likers), but Twitter disabled that endpoint
in 2024 when they made likes private. Retweeters serves as a public-signal proxy.
"""
import logging
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from .models import BookmarkedTweet, TweetLiker
from .twitter_client import TwitterClient

logger = logging.getLogger(__name__)


def _strip_null(s: str) -> str:
    """Remove null bytes that PostgreSQL rejects."""
    return s.replace("\x00", "") if s else s


async def fetch_tweet_likers(session: AsyncSession, client: TwitterClient) -> dict:
    """Fetch likers for all unfetched bookmarked tweets (newest first).

    No artificial cap — adaptive rate limiting governs throughput.
    """
    result = await session.execute(
        select(BookmarkedTweet)
        .where(BookmarkedTweet.likers_fetched == False)
        .order_by(BookmarkedTweet.bookmarked_at.desc())
    )
    tweets = result.scalars().all()

    if not tweets:
        print("No unfetched tweets to process", flush=True)
        return {"tweets_processed": 0, "total_likers": 0}

    # Eagerly capture tweet IDs to avoid lazy-load outside async context
    tweet_ids = [(tweet.tweet_id, tweet) for tweet in tweets]

    print(f"Fetching likers for {len(tweet_ids)} tweets (newest first)", flush=True)

    tweets_processed = 0
    total_likers = 0
    errors = 0

    for tweet_id, tweet in tweet_ids:
        try:
            likers = await client.get_retweeters(tweet_id)

            now = datetime.now(timezone.utc)
            for liker in likers:
                stmt = pg_insert(TweetLiker).values(
                    tweet_id=tweet_id,
                    user_handle=_strip_null(liker["handle"]),
                    user_name=_strip_null(liker.get("name", "")),
                    fetched_at=now,
                ).on_conflict_do_nothing()
                await session.execute(stmt)

            tweet.likers_fetched = True
            await session.commit()

            tweets_processed += 1
            total_likers += len(likers)
            print(
                f"[{tweets_processed}/{len(tweet_ids)}] Tweet {tweet_id}: "
                f"{len(likers)} retweeters (total: {total_likers})",
                flush=True,
            )

        except Exception as e:
            errors += 1
            print(f"Error fetching retweeters for tweet {tweet_id}: {e}", flush=True)
            await session.rollback()

            if errors >= 5:
                print("Too many consecutive errors, stopping backfill", flush=True)
                break
            continue

    stats = {
        "tweets_processed": tweets_processed,
        "tweets_remaining": len(tweet_ids) - tweets_processed,
        "total_likers": total_likers,
        "errors": errors,
    }
    print(f"Backfill complete: {stats}", flush=True)
    return stats
