"""Embedding client factory — Phase 7a-3.

Used by all three callers that build an :class:`EmbeddingClient`:

- :func:`ht_lens.translate.cli.translate_command` — Phase 7a-3 auto-embed
  chain.
- :func:`ht_lens.cli.embed_command` — consistency with the auto-embed path.
- :func:`ht_lens.api.app._lifespan` — consistency for the long-running
  process.

Returns ``None`` when ``RAG_DISABLED`` is set so callers can short-circuit
without instantiating :class:`BgeM3Client` (which downloads ~2 GB on first
run).
"""

from __future__ import annotations

import os

from ht_lens.embedding.service import (
    BgeM3Client,
    EmbeddingClient,
    MockEmbeddingClient,
)


def from_env_embedding() -> EmbeddingClient | None:
    """Build an :class:`EmbeddingClient` from environment.

    Resolution order:

    1. ``RAG_DISABLED`` ∈ ``{"1", "true", "yes"}`` (case-insensitive) →
       returns ``None``. The caller is responsible for surfacing this as
       a non-fatal skip (CLI prints ``embed: skipped (RAG_DISABLED)``,
       API leaves ``app.state.embedding_client = None``).
    2. ``EMBEDDING_PROVIDER=mock`` → :class:`MockEmbeddingClient` (dim=32).
       **Test/dev only**: do not set this against a production DB that
       already has 1024-dim bge-m3 rows — the resulting dim mix degrades
       cross-doc RAG retrieval. See ``embedding/store.py::load_all`` for
       the majority-dim heuristic that drops the minority.
    3. default → :class:`BgeM3Client` (downloads ~2 GB on first
       invocation; may raise on offline / missing-torch / bad-cache).
       Callers must handle init failure (see CLI graceful-degradation
       in :func:`translate_command`).
    """
    if os.environ.get("RAG_DISABLED", "").lower() in ("1", "true", "yes"):
        return None
    if os.environ.get("EMBEDDING_PROVIDER", "").lower() == "mock":
        return MockEmbeddingClient(dim=32)
    return BgeM3Client()


__all__ = ["from_env_embedding"]
