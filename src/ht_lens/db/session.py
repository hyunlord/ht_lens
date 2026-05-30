"""Async engine + session factory + schema-version helpers.

Phase 2a keeps PRAGMA work minimal: only ``foreign_keys=ON`` is enforced (needed
for cascade test correctness). WAL / synchronous tuning is deferred to Phase
2b/3 once concurrency requirements are measured.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import event, text
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

ALEMBIC_HEAD = "0007"
"""Current head revision for `alembic_version`. Bumped whenever a new migration is added."""


def make_engine(db_path: Path | str) -> AsyncEngine:
    """Create an async SQLite engine, enabling ``foreign_keys=ON`` on every connection.

    ``db_path`` is resolved to absolute and its parent is created if missing.
    """
    p = Path(db_path).resolve()
    p.parent.mkdir(parents=True, exist_ok=True)
    url = f"sqlite+aiosqlite:///{p}"
    engine = create_async_engine(url, echo=False, future=True)
    _install_foreign_keys_pragma(engine)
    return engine


def make_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Build the async session factory used by CLI + tests + future FastAPI deps."""
    return async_sessionmaker(engine, expire_on_commit=False)


def _install_foreign_keys_pragma(engine: AsyncEngine) -> None:
    """Attach an event listener on the underlying sync engine that issues
    ``PRAGMA foreign_keys=ON`` for every new DB-API connection."""

    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragma(dbapi_connection: Any, _connection_record: Any) -> None:
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
        finally:
            cursor.close()


async def current_schema_version(session: AsyncSession) -> str | None:
    """Return the head version stored in ``alembic_version``, or ``None`` if the
    table is absent (i.e. no migration has been applied yet)."""
    try:
        result = await session.execute(text("SELECT version_num FROM alembic_version"))
    except Exception:
        return None
    row = result.first()
    if row is None:
        return None
    value = row[0]
    return None if value is None else str(value)


def attach_sync_foreign_keys(sync_engine: Engine) -> None:
    """Same FK-PRAGMA hook but for a sync engine. Used by Alembic's offline/online
    migration runners which operate against a sync connection."""

    @event.listens_for(sync_engine, "connect")
    def _set_sqlite_pragma(dbapi_connection: Any, _connection_record: Any) -> None:
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
        finally:
            cursor.close()


__all__ = [
    "ALEMBIC_HEAD",
    "attach_sync_foreign_keys",
    "current_schema_version",
    "make_engine",
    "make_session_factory",
]
