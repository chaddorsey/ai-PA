"""
Fetch likers for bookmarked tweets via Twitter's Favoriters GraphQL endpoint.
Processes newest-first. Resumable via likers_fetched flag.
"""
import logging
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from .models import BookmarkedTweet, TweetLiker
from .twitter_client import TwitterClient

logger = logging.getLogger(__name__)


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
        logger.info("No unfetched tweets to process")
        return {"tweets_processed": 0, "total_likers": 0}

    logger.info(f"Fetching likers for {len(tweets)} tweets (newest first)")

    tweets_processed = 0
    total_likers = 0
    errors = 0

    for tweet in tweets:
        try:
            likers = await client.get_favoriters(tweet.tweet_id)

            now = datetime.now(timezone.utc)
            for liker in likers:
                stmt = pg_insert(TweetLiker).values(
                    tweet_id=tweet.tweet_id,
                    user_handle=liker["handle"],
                    user_name=liker.get("name", ""),
                    fetched_at=now,
                ).on_conflict_do_nothing()
                await session.execute(stmt)

            tweet.likers_fetched = True
            await session.commit()

            tweets_processed += 1
            total_likers += len(likers)
            logger.info(
                f"[{tweets_processed}/{len(tweets)}] Tweet {tweet.tweet_id}: "
                f"{len(likers)} likers (total: {total_likers})"
            )

        except Exception as e:
            errors += 1
            logger.error(f"Error fetching likers for tweet {tweet.tweet_id}: {e}")
            await session.rollback()

            if errors >= 5:
                logger.error("Too many consecutive errors, stopping backfill")
                break
            continue

    stats = {
        "tweets_processed": tweets_processed,
        "tweets_remaining": len(tweets) - tweets_processed,
        "total_likers": total_likers,
        "errors": errors,
    }
    logger.info(f"Backfill complete: {stats}")
    return stats
