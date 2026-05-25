"""Embedding clients — Phase 7a.

``EmbeddingClient`` protocol abstracts the encoder so tests can substitute
``MockEmbeddingClient`` without loading bge-m3 (a 2GB model download on
first run). The production implementation is ``BgeM3Client``, which uses
``sentence_transformers.SentenceTransformer`` to load BAAI/bge-m3 with
its official pooling/normalization recipe (Codex debate §2: avoid
manual ``last_hidden_state`` mean-pooling).
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Protocol

import numpy as np


def text_source_hash(text: str) -> str:
    """SHA-256 hex of the source text used for an embedding."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class EmbeddingClient(Protocol):
    """Embeds batches of text into L2-normalized float32 vectors."""

    @property
    def model_name(self) -> str: ...

    @property
    def dim(self) -> int: ...

    def encode(self, texts: list[str]) -> np.ndarray:
        """Returns ``(len(texts), dim)`` float32 array, L2-normalized."""
        ...


class BgeM3Client:
    """``BAAI/bge-m3`` via ``sentence-transformers`` (CPU by default).

    Phase 7a uses CPU to avoid GPU contention with the qwen sglang
    container (which holds ~90 GB on the shared GB10). The model itself
    is ~2 GB and downloads on first instantiation; pass ``cache_dir`` to
    pin the cache location for tests or offline mounts.
    """

    def __init__(
        self,
        device: str = "cpu",
        cache_dir: Path | None = None,
    ) -> None:
        from sentence_transformers import SentenceTransformer

        self._model_name = "BAAI/bge-m3"
        self._model = SentenceTransformer(
            self._model_name,
            device=device,
            cache_folder=str(cache_dir) if cache_dir else None,
        )
        d = self._model.get_sentence_embedding_dimension()
        if d is None:
            raise RuntimeError("bge-m3 reported no embedding dimension")
        self._dim = int(d)

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dim(self) -> int:
        return self._dim

    def encode(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self._dim), dtype=np.float32)
        out = self._model.encode(
            texts,
            batch_size=16,
            normalize_embeddings=True,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        return out.astype(np.float32, copy=False)


class MockEmbeddingClient:
    """Deterministic encoder for tests.

    Maps each input to a hash-seeded random unit vector. Two identical
    strings always produce the same vector; different strings produce
    different (and usually low-similarity) vectors. Does not require
    torch/sentence-transformers and downloads nothing.
    """

    def __init__(self, dim: int = 16, model_name: str = "mock-embed") -> None:
        self._dim = dim
        self._model_name = model_name

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dim(self) -> int:
        return self._dim

    def encode(self, texts: list[str]) -> np.ndarray:
        out = np.zeros((len(texts), self._dim), dtype=np.float32)
        for i, t in enumerate(texts):
            seed = int.from_bytes(
                hashlib.sha256(t.encode("utf-8")).digest()[:8], "big", signed=False
            )
            rng = np.random.default_rng(seed)
            v = rng.standard_normal(self._dim).astype(np.float32)
            n = float(np.linalg.norm(v))
            if n > 0:
                v /= n
            out[i] = v
        return out


__all__ = [
    "BgeM3Client",
    "EmbeddingClient",
    "MockEmbeddingClient",
    "text_source_hash",
]
