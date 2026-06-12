"""Alembic environment — async engine, autogenerate target = SQLModel metadata.

Config lives in pyproject.toml ([tool.alembic]); no alembic.ini per project
rules. The DB URL is taken from app settings, not the config file, so there is
one source of truth for connection info.
"""

import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel

# Import models so their tables register on SQLModel.metadata for autogenerate.
from python_coach.settings import get_settings
from python_coach.storage.models import lesson as _lesson  # noqa: F401
from python_coach.storage.models import submission as _submission  # noqa: F401

config = context.config
# Config lives in pyproject.toml, so there is no alembic.ini logging section to
# load; only call fileConfig when an actual ini file is present.
if config.config_file_name is not None and os.path.exists(config.config_file_name):
    fileConfig(config.config_file_name)

target_metadata = SQLModel.metadata


def _database_url() -> str:
    """Resolve the async DB URL from validated app settings."""
    return get_settings().database_url


def run_migrations_offline() -> None:
    """Emit SQL without a live connection (alembic upgrade --sql)."""
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def _do_run_migrations(connection) -> None:  # type: ignore[no-untyped-def]
    """Run migrations within a live (sync-facing) connection."""
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Run migrations against the async engine."""
    engine = create_async_engine(_database_url())
    async with engine.connect() as connection:
        await connection.run_sync(_do_run_migrations)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
