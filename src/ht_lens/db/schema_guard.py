"""Shared DB schema-version guard (Phase 8e-3).

The head check lives as a private ``_require_schema_head`` in several write
pipelines (translate, ingest). The 8d-2c ``retranslate_short`` path skipped it
(verify-cross debt) and the CLI ran it after the LLM health check. This module
provides the canonical, reusable guard now adopted by ``retranslate_short`` and
the ``translate-chunks`` CLI; the pre-existing private copies are left in place
(not a runtime issue) and can migrate to this helper in a later cleanup.
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
