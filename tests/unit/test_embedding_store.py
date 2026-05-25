"""Unit tests for ``vector_to_bytes`` / ``vector_from_bytes`` round-trip."""

from __future__ import annotations

import numpy as np
import pytest

from ht_lens.embedding.store import vector_from_bytes, vector_to_bytes


def test_round_trip_preserves_values() -> None:
    rng = np.random.default_rng(42)
    v = rng.standard_normal(1024).astype(np.float32)
    b = vector_to_bytes(v)
    back = vector_from_bytes(b, dim=1024)
    assert np.array_equal(v, back)


def test_round_trip_dtype_is_float32() -> None:
    v = np.array([0.1, 0.2, 0.3], dtype=np.float32)
    back = vector_from_bytes(vector_to_bytes(v), dim=3)
    assert back.dtype == np.float32


def test_round_trip_handles_l2_normalized() -> None:
    v = np.array([0.5, 0.5, 0.5, 0.5], dtype=np.float32)  # norm 1
    back = vector_from_bytes(vector_to_bytes(v), dim=4)
    assert np.isclose(float(np.linalg.norm(back)), 1.0)


def test_byte_length_matches_dim_times_four() -> None:
    v = np.zeros(7, dtype=np.float32)
    assert len(vector_to_bytes(v)) == 7 * 4


def test_from_bytes_rejects_dim_mismatch() -> None:
    v = np.zeros(5, dtype=np.float32)
    blob = vector_to_bytes(v)
    with pytest.raises(ValueError, match="does not match expected dim"):
        vector_from_bytes(blob, dim=8)
