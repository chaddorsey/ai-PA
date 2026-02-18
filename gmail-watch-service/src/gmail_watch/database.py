"""Database connection and session management."""

from __future__ import annotations

from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from gmail_watch.settings import settings


class Base(DeclarativeBase):
    """Base class for all database models."""

    pass


# Only create engine if database_url is set (for testing)
_engine = None
_async_session_maker = None


def get_engine():
    """Get or create the async database engine."""
    global _engine
    if _engine is None and settings.database_url:
        _engine = create_async_engine(settings.database_url, echo=False)
    return _engine


def get_session_maker():
    """Get or create the async session maker."""
    global _async_session_maker
    if _async_session_maker is None:
        engine = get_engine()
        if engine:
            _async_session_maker = async_sessionmaker(
                engine, class_=AsyncSession, expire_on_commit=False
            )
    return _async_session_maker


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Get a database session."""
    session_maker = get_session_maker()
    if session_maker:
        async with session_maker() as session:
            yield session
