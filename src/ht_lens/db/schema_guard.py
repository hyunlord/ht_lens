"""Shared DB schema-version guards (Phase 8e-3).

Before 8e-3 the head check lived as a private ``_require_schema_head`` inside
``translate.chunk_pipeline``; the 8d-2c ``retranslate_short`` path skipped it
(verify-cross debt), and the CLI ran it after the LLM health check. This module
centralises the contract so every write path (translate, retranslate, ingest)
fails the same clean way — ``SchemaVersionMismatch`` — on a stale DB.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from ht_lens.db.session import ALEMBIC_HEAD, current_schema_version
from ht_lens.errors import SchemaVersionMismatch


async def require_schema_head(session: AsyncSession) -> None:
    """Raise ``SchemaVersionMismatch`` unless the DB is at the 2.0 head.

    Used by write paths (chunk translation, short re-translation) that assume
    the 2.0 chunk schema. Pointing them at a stale/1.x DB must fail with a
    clear, actionable error rather than a raw OperationalError."""
    version = await current_schema_version(session)
    if version != ALEMBIC_HEAD:
        msg = "missing alembic_version" if version is None else f"version {version!r}"
        raise SchemaVersionMismatch(
            f"DB schema mismatch ({msg}; head={ALEMBIC_HEAD!r}). Run: uv run alembic upgrade head"
        )


__all__ = ["require_schema_head"]
