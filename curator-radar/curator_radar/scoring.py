import math
import logging
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from .models import StarredRepo, RepoStargazer, Curator

logger = logging.getLogger(__name__)


async def score_curators(session: AsyncSession) -> int:
    """Score all candidate curators based on overlap, popularity weighting, and earlyness."""

    # 1. Get all starred repos with their stargazer counts
    repos_result = await session.execute(select(StarredRepo))
    repos = {r.repo_id: r for r in repos_result.scalars().all()}

    if not repos:
        logger.warning("No starred repos found. Run backfill first.")
        return 0

    # 2. For each repo, compute earlyness percentiles for all stargazers
    #    earlyness = 1 - percentile (1.0 = earliest, 0.0 = latest)
    #    We do this in SQL for efficiency: rank within each repo's stargazers.

    # 3. Aggregate per user: sum of (idf_weight * (1.0 + 0.7 * earlyness)) across overlapping repos
    #    IDF weight: log(1 + 100000 / (1 + stargazers_count))

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

    result = await session.execute(scoring_sql, {"username": "chaddorsey"})
    rows = result.fetchall()

    # Upsert all curator scores
    now = datetime.now(timezone.utc)
    count = 0
    for row in rows:
        stmt = pg_insert(Curator).values(
            user_login=row.user_login,
            overlap_count=row.overlap_count,
            overlap_score=round(row.overlap_score, 4),
            earlyness_mean=round(row.earlyness_mean, 4),
            last_scored_at=now,
            blocked=False,
        ).on_conflict_do_update(
            index_elements=["user_login"],
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
    logger.info(f"Scored {count} curators (from {len(rows)} candidates with >= 2 overlaps)")
    return count


async def get_top_curators(session: AsyncSession, top_k: int = 20) -> list[dict]:
    """Return top-K curators by score."""
    result = await session.execute(
        select(Curator)
        .where(Curator.blocked == False)
        .order_by(Curator.overlap_score.desc())
        .limit(top_k)
    )
    curators = result.scalars().all()
    return [
        {
            "user_login": c.user_login,
            "overlap_count": c.overlap_count,
            "overlap_score": c.overlap_score,
            "earlyness_mean": c.earlyness_mean,
            "github_url": f"https://github.com/{c.user_login}",
        }
        for c in curators
    ]
