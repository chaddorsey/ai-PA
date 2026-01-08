"""Database connection and session management."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from pa_routing.settings import settings

# Create async engine
engine = create_async_engine(
    settings.postgres_url,
    echo=settings.log_level == "DEBUG",
    pool_pre_ping=True,
)

# Session factory
async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


@asynccontextmanager
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Get an async database session."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db() -> None:
    """Initialize database connection."""
    # Test connection
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))


async def close_db() -> None:
    """Close database connections."""
    await engine.dispose()
