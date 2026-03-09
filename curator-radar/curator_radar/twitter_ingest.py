"""
Ingest bookmarked tweet IDs from Smaug's output files.
Reads bookmarks.md and extracts tweet IDs + metadata.
"""
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from .models import BookmarkedTweet, TweetLiker
from .settings import Settings

logger = logging.getLogger(__name__)

DATE_RE = re.compile(r"^# (.+)$", re.MULTILINE)
TWEET_LINE_RE = re.compile(r"- \*\*Tweet:\*\* (https://x\.com/(\w+)/status/(\d+))")


async def ingest_bookmarks(session: AsyncSession, settings: Settings) -> int:
    """Read Smaug's bookmarks.md and ingest any new tweet IDs."""
    archive_path = Path(settings.smaug_data_path) / "bookmarks.md"
    if not archive_path.exists():
        logger.warning(f"Archive file not found: {archive_path}")
        return 0

    content = archive_path.read_text(encoding="utf-8")

    # Get existing tweet IDs to skip
    result = await session.execute(select(BookmarkedTweet.tweet_id))
    existing_ids = {row[0] for row in result.fetchall()}

    lines = content.split("\n")
    current_date = None
    new_count = 0

    for line in lines:
        date_match = DATE_RE.match(line)
        if date_match:
            try:
                current_date = datetime.strptime(date_match.group(1), "%A, %B %d, %Y")
                current_date = current_date.replace(tzinfo=timezone.utc)
            except ValueError:
                pass
            continue

        tweet_match = TWEET_LINE_RE.match(line.strip())
        if tweet_match:
            tweet_url = tweet_match.group(1)
            author = tweet_match.group(2)
            tweet_id = tweet_match.group(3)

            if tweet_id in existing_ids:
                continue

            stmt = pg_insert(BookmarkedTweet).values(
                tweet_id=tweet_id,
                author_handle=author,
                author_name="",
                text="",
                tweet_url=tweet_url,
                bookmarked_at=current_date or datetime.now(timezone.utc),
                likers_fetched=False,
            ).on_conflict_do_nothing()

            await session.execute(stmt)
            existing_ids.add(tweet_id)
            new_count += 1

            if new_count % 100 == 0:
                await session.commit()

    await session.commit()
    logger.info(f"Ingested {new_count} new bookmarks from Smaug archive")
    return new_count


async def get_ingest_status(session: AsyncSession) -> dict:
    """Return current ingestion and likers-fetch progress."""
    total = await session.scalar(select(func.count()).select_from(BookmarkedTweet))
    fetched = await session.scalar(
        select(func.count()).select_from(BookmarkedTweet).where(BookmarkedTweet.likers_fetched == True)
    )
    liker_rows = await session.scalar(select(func.count()).select_from(TweetLiker))

    return {
        "total_bookmarks": total or 0,
        "likers_fetched": fetched or 0,
        "likers_pending": (total or 0) - (fetched or 0),
        "total_liker_rows": liker_rows or 0,
    }
