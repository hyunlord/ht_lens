"""Phase 8e-3 — cutover guards: root redirect, schema allow-list, malformed env.

Locks the prod-cutover contract:
- ``/`` redirects to the 2.0 document list (default landing).
- the API STARTS against a 1.x (0004) DB so an env-flip rollback works, but
  rejects an UNKNOWN schema version (allow-list {0004, 0007}).
- a malformed ``HT_LENS_DB_URL`` fails loud instead of silently serving 1.x.
- the shared schema_guard raises on a non-head DB.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from sqlalchemy import text

from ht_lens.db.base import Base
from ht_lens.db.session import ALEMBIC_HEAD, make_engine, make_session_factory
from ht_lens.errors import SchemaVersionMismatch

from ._api_helpers import make_test_client


def _make_db_at_version(tmp_path: Path, version: str, name: str = "db.db") -> Path:
    """Create a DB with the full schema (all tables) but a chosen alembic_version."""
    db_path = tmp_path / name

    async def _seed() -> None:
        engine = make_engine(db_path)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.execute(
                text(
                    "CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32) NOT NULL)"
                )
            )
            await conn.execute(text(f"INSERT INTO alembic_version VALUES ('{version}')"))
        await engine.dispose()

    asyncio.run(_seed())
    return db_path


# --------------------------------------------------------------------------- #
# Root redirect (default landing = 2.0 document list)
# --------------------------------------------------------------------------- #
def test_root_redirects_to_document_list(api_db_path: Path) -> None:
    with make_test_client(api_db_path) as client:
        r = client.get("/", follow_redirects=False)
    assert r.status_code in (302, 307, 308)
    assert r.headers["location"].endswith("/static/index.html")


# --------------------------------------------------------------------------- #
# Schema allow-list {0004, 0007} (env-flip rollback to 1.x must start)
# --------------------------------------------------------------------------- #
def test_api_starts_on_1x_0004_db_for_rollback(tmp_path: Path) -> None:
    """verify-cross 8e-3 §2 (CRITICAL): an env flip back to the 1.x prod DB
    (alembic 0004) must START, not crash — otherwise '즉시 롤백' is false."""
    db = _make_db_at_version(tmp_path, "0004", "rollback_1x.db")
    with make_test_client(db) as client:
        # a 1.x route is reachable (startup succeeded); empty list is fine.
        r = client.get("/documents")
        assert r.status_code == 200


def test_api_rejects_unknown_schema_version(tmp_path: Path) -> None:
    """An UNKNOWN version (not in the cutover allow-list) is still rejected."""
    db = _make_db_at_version(tmp_path, "0003", "unknown.db")
    with pytest.raises(SchemaVersionMismatch), make_test_client(db):
        pass


def test_api_starts_on_2x_head(tmp_path: Path) -> None:
    db = _make_db_at_version(tmp_path, ALEMBIC_HEAD, "head.db")
    with make_test_client(db) as client:
        assert client.get("/documents").status_code == 200


# --------------------------------------------------------------------------- #
# Malformed HT_LENS_DB_URL fails loud (no silent 1.x fallback)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "bad_url",
    ["sqlite:///data/x.db", "sqlite+aiosqlite://data/x.db", "/data/x.db", "  spaced  "],
)
def test_db_path_from_env_rejects_malformed_url(
    bad_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    import ht_lens.api.app as app_mod
    import ht_lens.cli as cli_mod

    monkeypatch.setenv("HT_LENS_DB_URL", bad_url)
    for fn in (app_mod._db_path_from_env, cli_mod._db_path_from_env):
        with pytest.raises(ValueError, match="HT_LENS_DB_URL"):
            fn()


def test_db_path_from_env_empty_uses_default(monkeypatch: pytest.MonkeyPatch) -> None:
    import ht_lens.api.app as app_mod

    monkeypatch.delenv("HT_LENS_DB_URL", raising=False)
    assert app_mod._db_path_from_env() == app_mod._DEFAULT_DB


# --------------------------------------------------------------------------- #
# Shared schema_guard
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_require_schema_head_raises_on_stale(tmp_path: Path) -> None:
    from ht_lens.db.schema_guard import require_schema_head

    # Seed inline with await — this test already runs inside an event loop, so
    # the asyncio.run-based _make_db_at_version helper would error.
    engine = make_engine(tmp_path / "stale.db")
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.execute(
                text(
                    "CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32) NOT NULL)"
                )
            )
            await conn.execute(text("INSERT INTO alembic_version VALUES ('0004')"))
        async with make_session_factory(engine)() as session:
            with pytest.raises(SchemaVersionMismatch):
                await require_schema_head(session)
    finally:
        await engine.dispose()
