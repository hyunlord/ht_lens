"""Unit tests for translate.cache.cache_key."""

from __future__ import annotations

from ht_lens.translate.cache import cache_key


def test_same_inputs_produce_same_digest() -> None:
    k1 = cache_key("hello", "en", "ko", "model-x")
    k2 = cache_key("hello", "en", "ko", "model-x")
    assert k1 == k2


def test_different_text_produces_different_digest() -> None:
    assert cache_key("hello", "en", "ko", "m") != cache_key("world", "en", "ko", "m")


def test_different_src_produces_different_digest() -> None:
    assert cache_key("hello", "en", "ko", "m") != cache_key("hello", "ko", "ko", "m")


def test_different_tgt_produces_different_digest() -> None:
    assert cache_key("hello", "en", "ko", "m") != cache_key("hello", "en", "en", "m")


def test_different_model_produces_different_digest() -> None:
    assert cache_key("hello", "en", "ko", "a") != cache_key("hello", "en", "ko", "b")


def test_nul_separator_prevents_collisions() -> None:
    # Without NUL separator, "ab"+"cd" could collide with "a"+"bcd"
    assert cache_key("ab", "cd", "ef", "g") != cache_key("a", "bcd", "ef", "g")


def test_output_is_64_hex_chars() -> None:
    k = cache_key("text", "en", "ko", "model")
    assert len(k) == 64
    assert all(c in "0123456789abcdef" for c in k)
