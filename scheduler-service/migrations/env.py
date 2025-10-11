"""Alembic environment configuration."""

from __future__ import annotations

import asyncio
import os
from logging.config import fileConfig
from typing import Any

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config


def _get_database_url() -> str:
    return os.environ.get(
        "SCHEDULER_DB_URL",
        os.environ.get(
            "DATABASE_URL",
            "postgresql+asyncpg://scheduler:scheduler@localhost:5432/scheduler",
        ),
    )


def _get_target_metadata() -> Any:
    import importlib

    module_name = os.environ.get("SCHEDULER_MODELS_MODULE", "scheduler_service.models")
    metadata_attr = os.environ.get("SCHEDULER_METADATA_ATTR", "metadata")
    try:
        module = importlib.import_module(module_name)
        return getattr(module, metadata_attr, None)
    except ModuleNotFoundError:
        return None


config = context.config
config.set_main_option("sqlalchemy.url", _get_database_url())

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = _get_target_metadata()


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""

    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)

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


