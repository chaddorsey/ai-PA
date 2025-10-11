"""Database session handling utilities."""

from __future__ import annotations

from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from scheduler_service.settings import Settings, settings


def create_engine(settings: Settings) -> AsyncEngine:
    return create_async_engine(settings.database_url, echo=False)


engine = create_engine(settings)
AsyncSessionFactory = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide an async session dependency for FastAPI endpoints."""

    async with AsyncSessionFactory() as session:
        yield session


