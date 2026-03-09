import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from .models import Curator, CuratorEvent, StarredRepo
from .github_client import GitHubClient

logger = logging.getLogger(__name__)


async def refresh_curator_events(session: AsyncSession, client: GitHubClient, top_k: int = 20) -> int:
    """Fetch WatchEvents from top-K curators and store new ones."""
    result = await session.execute(
        select(Curator)
        .where(Curator.blocked == False, Curator.platform == "github")
        .order_by(Curator.overlap_score.desc())
        .limit(top_k)
    )
    curators = result.scalars().all()

    # Get repos Chad already starred (to flag novelty)
    chad_repos = await session.execute(select(StarredRepo.full_name))
    chad_repo_set = {r[0] for r in chad_repos.fetchall()}

    new_events = 0
    for curator in curators:
        logger.info(f"Checking events for {curator.user_login}")
        try:
            async for page in client.get_user_events(curator.user_login):
                for event in page:
                    if event.get("type") != "WatchEvent":
                        continue
                    repo_name = event.get("repo", {}).get("name", "")
                    if repo_name in chad_repo_set:
                        continue  # Skip repos Chad already starred

                    event_time = datetime.fromisoformat(
                        event["created_at"].replace("Z", "+00:00")
                    )
                    stmt = pg_insert(CuratorEvent).values(
                        event_id=str(event["id"]),
                        user_login=curator.user_login,
                        repo_full_name=repo_name,
                        event_time=event_time,
                        processed=False,
                    ).on_conflict_do_nothing()
                    result = await session.execute(stmt)
                    if result.rowcount > 0:
                        new_events += 1
        except Exception as e:
            logger.error(f"Error fetching events for {curator.user_login}: {e}")
            continue

    await session.commit()
    logger.info(f"Found {new_events} new WatchEvents from top-{top_k} curators")
    return new_events


async def get_discoveries(session: AsyncSession, since_days: int = 7) -> list[dict]:
    """Get repos discovered by curators in the last N days, ranked by curator count."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=since_days)
    result = await session.execute(
        select(
            CuratorEvent.repo_full_name,
            Curator.overlap_score,
            CuratorEvent.user_login,
            CuratorEvent.event_time,
        )
        .join(Curator, Curator.user_login == CuratorEvent.user_login)
        .where(CuratorEvent.event_time >= cutoff)
        .order_by(CuratorEvent.event_time.desc())
    )
    rows = result.fetchall()

    # Group by repo, count unique curators, sum their scores
    repo_map: dict[str, dict] = {}
    for row in rows:
        repo = row.repo_full_name
        if repo not in repo_map:
            repo_map[repo] = {"repo": repo, "curators": [], "total_score": 0.0, "latest": row.event_time}
        if row.user_login not in [c["login"] for c in repo_map[repo]["curators"]]:
            repo_map[repo]["curators"].append({"login": row.user_login, "score": row.overlap_score})
            repo_map[repo]["total_score"] += row.overlap_score
        if row.event_time > repo_map[repo]["latest"]:
            repo_map[repo]["latest"] = row.event_time

    # Sort by number of curators (social proof), then total score
    ranked = sorted(repo_map.values(), key=lambda r: (len(r["curators"]), r["total_score"]), reverse=True)

    return [
        {
            "repo": r["repo"],
            "github_url": f"https://github.com/{r['repo']}",
            "curator_count": len(r["curators"]),
            "curators": [c["login"] for c in r["curators"]],
            "total_curator_score": round(r["total_score"], 2),
            "latest_event": r["latest"].isoformat(),
        }
        for r in ranked[:50]
    ]
