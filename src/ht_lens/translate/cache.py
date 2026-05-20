"""Translation cache-key helper — Phase 2b."""

from __future__ import annotations

import hashlib


def cache_key(text: str, src: str, tgt: str, model: str) -> str:
    """SHA-256 of NUL-delimited (text, src, tgt, model)."""
    blob = "\x00".join([text, src, tgt, model])
    return hashlib.sha256(blob.encode()).hexdigest()


__all__ = ["cache_key"]
