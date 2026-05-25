"""Unit tests for the embedding service abstractions — Phase 7a."""

from __future__ import annotations

import numpy as np

from ht_lens.embedding.service import (
    MockEmbeddingClient,
    text_source_hash,
)


def test_mock_client_produces_correct_shape() -> None:
    client = MockEmbeddingClient(dim=32)
    out = client.encode(["foo", "bar", "baz"])
    assert out.shape == (3, 32)
    assert out.dtype == np.float32


def test_mock_client_is_deterministic() -> None:
    client = MockEmbeddingClient(dim=16)
    a = client.encode(["same text"])[0]
    b = client.encode(["same text"])[0]
    assert np.allclose(a, b), "identical input must produce identical vectors"


def test_mock_client_returns_unit_vectors() -> None:
    client = MockEmbeddingClient(dim=24)
    out = client.encode(["alpha", "beta"])
    norms = np.linalg.norm(out, axis=1)
    assert np.allclose(norms, 1.0, atol=1e-5), f"non-unit norms: {norms}"


def test_mock_client_empty_batch() -> None:
    client = MockEmbeddingClient(dim=8)
    out = client.encode([])
    assert out.shape == (0, 8)


def test_mock_client_different_texts_have_low_similarity() -> None:
    """Random unit vectors should be roughly orthogonal in high dim."""
    client = MockEmbeddingClient(dim=128)
    a, b = client.encode(["completely different text one", "totally unrelated payload two"])
    sim = float(np.dot(a, b))
    # Random 128-d unit vectors typically have |dot| < 0.2.
    assert abs(sim) < 0.3, f"unexpectedly high similarity for unrelated texts: {sim}"


def test_text_source_hash_is_deterministic() -> None:
    h1 = text_source_hash("hello")
    h2 = text_source_hash("hello")
    assert h1 == h2
    assert len(h1) == 64  # sha256 hex


def test_text_source_hash_differs_for_different_input() -> None:
    assert text_source_hash("a") != text_source_hash("b")
