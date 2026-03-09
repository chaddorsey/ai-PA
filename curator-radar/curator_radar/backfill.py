import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from .models import StarredRepo, RepoStargazer, BackfillCheckpoint
from .github_client import GitHubClient

logger = logging.getLogger(__name__)

TWELVE_MONTHS_AGO = datetime.now(timezone.utc) - timedelta(days=365)


def _parse_dt(val: str | None) -> datetime | None:
    """Parse an ISO 8601 timestamp string to a datetime, or return None."""
    if not val:
        return None
    return datetime.fromisoformat(val.replace("Z", "+00:00"))


async def backfill_stars(session: AsyncSession, client: GitHubClient, since_days: int = 365):
    """Fetch user's starred repos from the last N days."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=since_days)
    count = 0

    async for page in client.get_user_stars():
        for item in page:
            starred_at = datetime.fromisoformat(item["starred_at"].replace("Z", "+00:00"))
            if starred_at < cutoff:
                logger.info(f"Reached cutoff at {starred_at}, stopping. Fetched {count} repos.")
                await session.commit()
                return count
            repo = item["repo"]
            stmt = pg_insert(StarredRepo).values(
                repo_id=repo["id"],
                full_name=repo["full_name"],
                owner=repo["owner"]["login"],
                name=repo["name"],
                language=repo.get("language"),
                topics=repo.get("topics", []),
                stargazers_count=repo.get("stargazers_count", 0),
                created_at=_parse_dt(repo.get("created_at")),
                pushed_at=_parse_dt(repo.get("pushed_at")),
                starred_at_by_chad=starred_at,
            ).on_conflict_do_update(
                index_elements=["repo_id"],
                set_={"stargazers_count": repo.get("stargazers_count", 0), "pushed_at": _parse_dt(repo.get("pushed_at"))},
            )
            await session.execute(stmt)
            count += 1
        await session.commit()

    logger.info(f"Fetched all {count} starred repos.")
    return count


async def backfill_stargazers(session: AsyncSession, client: GitHubClient, max_pages_per_repo: int = 100):
    """Fetch stargazers for all starred repos. Resumable via checkpoint."""
    # Get checkpoint
    cp_result = await session.execute(
        select(BackfillCheckpoint).where(BackfillCheckpoint.job_name == "stargazers")
    )
    checkpoint = cp_result.scalar_one_or_none()
    completed_repos: set = set(checkpoint.checkpoint.get("completed", [])) if checkpoint else set()

    # Get all repos
    repos_result = await session.execute(select(StarredRepo))
    repos = repos_result.scalars().all()

    # Sort smallest first (fastest to complete, best for rate-limit budgeting)
    repos = sorted(repos, key=lambda r: r.stargazers_count)

    for repo in repos:
        if repo.full_name in completed_repos:
            continue

        logger.info(f"Fetching stargazers for {repo.full_name} ({repo.stargazers_count} stars)")
        page_count = 0

        try:
            async for page in client.get_repo_stargazers(repo.full_name):
                for item in page:
                    user = item.get("user", {})
                    if not user or not user.get("login"):
                        continue
                    starred_at = item.get("starred_at")
                    if starred_at:
                        starred_at = datetime.fromisoformat(starred_at.replace("Z", "+00:00"))

                    stmt = pg_insert(RepoStargazer).values(
                        repo_id=repo.repo_id,
                        user_login=user["login"],
                        starred_at=starred_at,
                    ).on_conflict_do_nothing()
                    await session.execute(stmt)

                page_count += 1
                if page_count >= max_pages_per_repo:
                    logger.info(f"  Hit page limit ({max_pages_per_repo}) for {repo.full_name}")
                    break

            await session.commit()
        except Exception as e:
            logger.error(f"Error fetching stargazers for {repo.full_name}: {e}")
            await session.rollback()
            continue

        # Update checkpoint
        completed_repos.add(repo.full_name)
        cp_stmt = pg_insert(BackfillCheckpoint).values(
            job_name="stargazers",
            checkpoint={"completed": list(completed_repos)},
            updated_at=datetime.now(timezone.utc),
        ).on_conflict_do_update(
            index_elements=["job_name"],
            set_={"checkpoint": {"completed": list(completed_repos)}, "updated_at": datetime.now(timezone.utc)},
        )
        await session.execute(cp_stmt)
        await session.commit()

    return len(completed_repos)


async def get_backfill_status(session: AsyncSession) -> dict:
    """Return current backfill progress."""
    total = await session.scalar(select(func.count()).select_from(StarredRepo))
    cp_result = await session.execute(
        select(BackfillCheckpoint).where(BackfillCheckpoint.job_name == "stargazers")
    )
    checkpoint = cp_result.scalar_one_or_none()
    completed = len(checkpoint.checkpoint.get("completed", [])) if checkpoint else 0
    stargazer_count = await session.scalar(select(func.count()).select_from(RepoStargazer))

    return {
        "starred_repos": total or 0,
        "repos_with_stargazers_fetched": completed,
        "total_stargazer_rows": stargazer_count or 0,
        "complete": completed >= (total or 0),
    }
