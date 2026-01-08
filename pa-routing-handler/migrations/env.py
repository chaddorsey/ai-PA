"""Alembic environment configuration."""

from __future__ import annotations

import asyncio
import os
from logging.config import fileConfig
from typing import Any

from alembic import context
from sqlalchemy import pool, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# Schema name for pa_web tables
SCHEMA_NAME = "pa_web"


def _get_database_url() -> str:
    return os.environ.get(
        "PA_ROUTING_POSTGRES_URL",
        "postgresql+asyncpg://postgres:postgres@localhost:5432/postgres",
    )


def _get_target_metadata() -> Any:
    from pa_routing.models import metadata
    return metadata


config = context.config
config.set_main_option("sqlalchemy.url", _get_database_url())

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = _get_target_metadata()


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        include_schemas=True,
        version_table_schema=SCHEMA_NAME,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    # Create schema if it doesn't exist
    connection.execute(text(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA_NAME}"))
    connection.commit()

    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_schemas=True,
        version_table_schema=SCHEMA_NAME,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations() -> None:
    if context.is_offline_mode():
        run_migrations_offline()
    else:
        asyncio.run(run_migrations_online())


run_migrations()
