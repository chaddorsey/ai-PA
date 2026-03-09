"""
Auto-manage a private Twitter List with top-N Twitter curators.
Creates the list if it doesn't exist, adds/removes members to stay in sync.
"""
import logging
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from .models import Curator, TwitterList, TwitterListMember
from .twitter_client import TwitterClient
from .settings import Settings

logger = logging.getLogger(__name__)


async def sync_twitter_list(session: AsyncSession, client: TwitterClient, settings: Settings) -> dict:
    """Sync the Twitter list with top-N curators. Creates list if needed."""

    list_name = settings.twitter_list_name
    list_size = settings.twitter_list_size

    # Get or create the Twitter list
    result = await session.execute(
        select(TwitterList).where(TwitterList.list_name == list_name)
    )
    twitter_list = result.scalar_one_or_none()

    if not twitter_list:
        logger.info(f"Creating Twitter list: {list_name}")
        list_id = await client.create_list(list_name, description="Auto-managed by Curator Radar", private=True)
        if not list_id:
            logger.error("Failed to create Twitter list")
            return {"status": "error", "message": "Failed to create list"}

        stmt = pg_insert(TwitterList).values(
            list_id=list_id,
            list_name=list_name,
            last_synced_at=datetime.now(timezone.utc),
        ).on_conflict_do_nothing()
        await session.execute(stmt)
        await session.commit()

        result = await session.execute(
            select(TwitterList).where(TwitterList.list_name == list_name)
        )
        twitter_list = result.scalar_one_or_none()

    list_id = twitter_list.list_id

    # Get top-N Twitter curators
    curators_result = await session.execute(
        select(Curator)
        .where(Curator.platform == "twitter", Curator.blocked == False)
        .order_by(Curator.overlap_score.desc())
        .limit(list_size)
    )
    top_curators = {c.user_login for c in curators_result.scalars().all()}

    # Get current list members
    members_result = await session.execute(
        select(TwitterListMember)
        .where(TwitterListMember.list_id == list_id, TwitterListMember.removed_at == None)
    )
    current_members = {m.user_handle for m in members_result.scalars().all()}

    to_add = top_curators - current_members
    to_remove = current_members - top_curators

    added = 0
    removed = 0

    for handle in to_add:
        user_id = await client.get_user_rest_id(handle)
        if not user_id:
            logger.warning(f"Could not resolve user ID for @{handle}")
            continue
        success = await client.add_list_member(list_id, user_id)
        if success:
            stmt = pg_insert(TwitterListMember).values(
                list_id=list_id,
                user_handle=handle,
                added_at=datetime.now(timezone.utc),
            ).on_conflict_do_update(
                index_elements=["list_id", "user_handle"],
                set_={"removed_at": None, "added_at": datetime.now(timezone.utc)},
            )
            await session.execute(stmt)
            added += 1
            logger.info(f"Added @{handle} to list")

    for handle in to_remove:
        user_id = await client.get_user_rest_id(handle)
        if user_id:
            await client.remove_list_member(list_id, user_id)
        result = await session.execute(
            select(TwitterListMember)
            .where(TwitterListMember.list_id == list_id, TwitterListMember.user_handle == handle)
        )
        member = result.scalar_one_or_none()
        if member:
            member.removed_at = datetime.now(timezone.utc)
        removed += 1
        logger.info(f"Removed @{handle} from list")

    twitter_list.last_synced_at = datetime.now(timezone.utc)
    await session.commit()

    stats = {"added": added, "removed": removed, "total_members": len(top_curators)}
    logger.info(f"List sync complete: {stats}")
    return stats
