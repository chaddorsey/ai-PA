"""
One-time migration: add platform column to curators table.
Safe to run multiple times (idempotent).
"""
import asyncio
import logging
from sqlalchemy import text
from curator_radar.database import engine

logger = logging.getLogger(__name__)


async def migrate():
    async with engine.begin() as conn:
        # Check if platform column exists
        result = await conn.execute(text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'curators' AND column_name = 'platform'
        """))
        if result.fetchone():
            print("Migration already applied: platform column exists.")
            return

        print("Adding platform column to curators table...")
        await conn.execute(text(
            "ALTER TABLE curators ADD COLUMN platform VARCHAR(20) NOT NULL DEFAULT 'github'"
        ))
        await conn.execute(text("ALTER TABLE curators DROP CONSTRAINT curators_pkey"))
        await conn.execute(text("ALTER TABLE curators ADD PRIMARY KEY (user_login, platform)"))
        print("Migration complete: curators table now has composite PK (user_login, platform).")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(migrate())
