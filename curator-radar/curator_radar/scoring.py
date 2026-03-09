import logging
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from .models import Curator

logger = logging.getLogger(__name__)


async def score_github_curators(session: AsyncSession, username: str = "chaddorsey") -> int:
    """Score GitHub curators based on repo overlap, IDF weighting, and earlyness."""
    scoring_sql = text("""
        WITH repo_earlyness AS (
            SELECT
                rs.repo_id,
                rs.user_login,
                rs.starred_at,
                CASE
                    WHEN COUNT(*) OVER (PARTITION BY rs.repo_id) <= 1 THEN 0.5
                    ELSE 1.0 - (
                        RANK() OVER (PARTITION BY rs.repo_id ORDER BY COALESCE(rs.starred_at, '2099-01-01'::timestamp))::float
                        / NULLIF(COUNT(*) OVER (PARTITION BY rs.repo_id), 0)
                    )
                END AS earlyness
            FROM repo_stargazers rs
        ),
        user_scores AS (
            SELECT
                re.user_login,
                COUNT(DISTINCT re.repo_id) AS overlap_count,
                SUM(
                    LN(1 + 100000.0 / (1 + sr.stargazers_count))
                    * (1.0 + 0.7 * re.earlyness)
                ) AS overlap_score,
                AVG(re.earlyness) AS earlyness_mean
            FROM repo_earlyness re
            JOIN starred_repos sr ON sr.repo_id = re.repo_id
            WHERE re.user_login != :username
            GROUP BY re.user_login
            HAVING COUNT(DISTINCT re.repo_id) >= 2
        )
        SELECT user_login, overlap_count, overlap_score, earlyness_mean
        FROM user_scores
        ORDER BY overlap_score DESC
    """)

    result = await session.execute(scoring_sql, {"username": username})
    rows = result.fetchall()

    now = datetime.now(timezone.utc)
    count = 0
    for row in rows:
        stmt = pg_insert(Curator).values(
            user_login=row.user_login,
            platform="github",
            overlap_count=row.overlap_count,
            overlap_score=round(row.overlap_score, 4),
            earlyness_mean=round(row.earlyness_mean, 4),
            last_scored_at=now,
            blocked=False,
        ).on_conflict_do_update(
            index_elements=["user_login", "platform"],
            set_={
                "overlap_count": row.overlap_count,
                "overlap_score": round(row.overlap_score, 4),
                "earlyness_mean": round(row.earlyness_mean, 4),
                "last_scored_at": now,
            },
        )
        await session.execute(stmt)
        count += 1
        if count % 1000 == 0:
            await session.commit()

    await session.commit()
    logger.info(f"Scored {count} GitHub curators")
    return count


async def score_twitter_curators(session: AsyncSession) -> int:
    """Score Twitter curators based on tweet-like overlap with IDF weighting."""
    scoring_sql = text("""
        WITH tweet_liker_counts AS (
            SELECT
                tl.tweet_id,
                tl.user_handle,
                COUNT(*) OVER (PARTITION BY tl.tweet_id) AS likers_count
            FROM tweet_likers tl
        ),
        user_scores AS (
            SELECT
                tlc.user_handle AS user_login,
                COUNT(DISTINCT tlc.tweet_id) AS overlap_count,
                SUM(
                    LN(1 + 100000.0 / (1 + tlc.likers_count))
                ) AS overlap_score
            FROM tweet_liker_counts tlc
            GROUP BY tlc.user_handle
            HAVING COUNT(DISTINCT tlc.tweet_id) >= 2
        )
        SELECT user_login, overlap_count, overlap_score
        FROM user_scores
        ORDER BY overlap_score DESC
    """)

    result = await session.execute(scoring_sql)
    rows = result.fetchall()

    now = datetime.now(timezone.utc)
    count = 0
    for row in rows:
        stmt = pg_insert(Curator).values(
            user_login=row.user_login,
            platform="twitter",
            overlap_count=row.overlap_count,
            overlap_score=round(row.overlap_score, 4),
            earlyness_mean=0.0,
            last_scored_at=now,
            blocked=False,
        ).on_conflict_do_update(
            index_elements=["user_login", "platform"],
            set_={
                "overlap_count": row.overlap_count,
                "overlap_score": round(row.overlap_score, 4),
                "last_scored_at": now,
            },
        )
        await session.execute(stmt)
        count += 1
        if count % 1000 == 0:
            await session.commit()

    await session.commit()
    logger.info(f"Scored {count} Twitter curators")
    return count


async def score_curators(session: AsyncSession, platform: str = "github") -> int:
    """Score curators for a given platform."""
    if platform == "twitter":
        return await score_twitter_curators(session)
    return await score_github_curators(session)


async def get_top_curators(session: AsyncSession, top_k: int = 20, platform: str = "github") -> list[dict]:
    """Return top-K curators by score for a given platform."""
    result = await session.execute(
        select(Curator)
        .where(Curator.blocked == False, Curator.platform == platform)
        .order_by(Curator.overlap_score.desc())
        .limit(top_k)
    )
    curators = result.scalars().all()

    url_prefix = "https://github.com" if platform == "github" else "https://x.com"
    return [
        {
            "user_login": c.user_login,
            "platform": c.platform,
            "overlap_count": c.overlap_count,
            "overlap_score": c.overlap_score,
            "earlyness_mean": c.earlyness_mean,
            "profile_url": f"{url_prefix}/{c.user_login}",
        }
        for c in curators
    ]
