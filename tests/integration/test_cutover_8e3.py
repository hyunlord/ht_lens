"""Phase 8e-3 — cutover guards: root redirect, strict schema head, malformed env.

Locks the prod-cutover contract:
- ``/`` redirects to the 2.0 document list (default landing).
- the API requires the 2.0 head and rejects any other version (incl. a real 1.x
  0004 DB) — the live finding showed 2.0 code can't serve 0004 (2.0-only columns),
  so rollback is "revert the main merge" + env, NOT env-flip alone.
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
# Strict schema head (rollback is git-revert, not env-flip — see module docstring)
# --------------------------------------------------------------------------- #
def test_api_rejects_non_head_db(tmp_path: Path) -> None:
    """The guard is strict on the 2.0 head: a non-head DB (incl. a real 1.x 0004)
    is rejected at startup. Env-flip to 1.x is NOT a valid 2.0-code rollback (2.0
    queries columns absent at 0004); rollback = revert the main merge + env."""
    for version in ("0004", "0003"):
        db = _make_db_at_version(tmp_path, version, f"v{version}.db")
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


# --------------------------------------------------------------------------- #
# Document list page count for 2.0 docs (verify-cross §4#1)
# --------------------------------------------------------------------------- #
def test_2x_doc_page_count_from_chunks_not_zero(api_db_path: Path) -> None:
    """A 2.0 (MinerU) doc has no Page rows; the document list derives its page
    count from max(chunk.page_idx)+1 (total pages spanned) — including a blank
    middle page with no chunks (verify-cross R2 sparse edge), not '0 pages' (§4#1)."""
    from datetime import UTC, datetime

    from ht_lens.db.models import Chunk, Document

    async def _seed() -> int:
        engine = make_engine(api_db_path)
        factory = make_session_factory(engine)
        async with factory() as s:
            doc = Document(
                filename="twopage.pdf",
                src_lang="en",
                tgt_lang="ko",
                status="translated",
                created_at=datetime.now(UTC),
                extractor="mineru",
            )
            s.add(doc)
            await s.flush()
            for i, pidx in enumerate((0, 0, 2)):  # page 1 blank (no chunk) → max+1 = 3 pages
                s.add(
                    Chunk(
                        doc_id=doc.id,
                        page_idx=pidx,
                        order_idx=i,
                        type="text",
                        bbox_json="[0,0,1,1]",
                        content=f"c{i}",
                    )
                )
            await s.commit()
            did = doc.id
        await engine.dispose()
        return did

    import asyncio as _asyncio

    doc_id = _asyncio.run(_seed())
    with make_test_client(api_db_path) as client:
        listed = {d["id"]: d for d in client.get("/documents").json()}
        assert listed[doc_id]["num_pages"] == 3  # from chunk.page_idx, not 0
        single = client.get(f"/documents/{doc_id}").json()
        assert single["num_pages"] == 3
