"""Alembic environment — async-aware online runner.

DB URL is taken from the ``HT_LENS_DB_URL`` env var, falling back to
``./data/ht_lens.db`` resolved against the current working directory. CLI users
typically run ``HT_LENS_DB_URL=sqlite+aiosqlite:///abs/path uv run alembic upgrade head``.
"""

from __future__ import annotations

import asyncio
import os
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from ht_lens.db.base import Base
from ht_lens.db.models import (  # noqa: F401  (imported so metadata sees every model)
    Block,
    Document,
    Message,
    Page,
    Thread,
    Translation,
)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def _resolve_url() -> str:
    env_url = os.environ.get("HT_LENS_DB_URL")
    if env_url:
        return env_url
    default_path = (Path.cwd() / "data" / "ht_lens.db").resolve()
    return f"sqlite+aiosqlite:///{default_path}"


config.set_main_option("sqlalchemy.url", _resolve_url())

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section, {})
    connectable = async_engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
