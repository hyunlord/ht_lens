r"""Math placeholder protection for chunk translation (Phase 8b).

Round-trips every ``$$...$$`` / ``$...$`` run through an opaque
``⟦MATHi⟧`` placeholder so the LLM never sees — and therefore cannot
mangle — LaTeX. Validated in the ``~/mineru_test`` sandbox: KaTeX-valid
output, ``\operatorname*`` / ``\textstyle`` preserved byte-identical.

Contract (challenge §1, post-debate):
- ``protect_math(text) -> (protected, store)``.
- ``restore_math(protected_translation, store) -> (restored, missing)``
  where ``missing`` lists store indices the LLM dropped/corrupted.
- The caller marks a chunk ``failed`` when ``missing`` is non-empty — we
  do NOT append lost formulas as comments (that would corrupt reading
  order and only fake byte-identity). A successful translation is
  byte-identical in its math; a lossy one is flagged, not mutated.

Known, intentional limits (locked by tests):
- A lone ``$`` (currency ``$5``) is not protected — the inline pattern
  requires a closing ``$``. A currency *pair* (``$5 to $10``) may match
  as one run; that is safe because restore is byte-identical (the run is
  simply left untranslated, never corrupted).
- ``\(...\)`` / ``\[...\]`` are not handled; MinerU emits inline math as
  ``$...$`` and display equations as standalone ``equation`` chunks
  (passthrough, never protected).
"""

from __future__ import annotations

import re

PH_OPEN = "⟦"
PH_CLOSE = "⟧"

_DISPLAY_RE = re.compile(r"\$\$[\s\S]+?\$\$")
_INLINE_RE = re.compile(r"(?<!\$)\$[^$\n]+?\$(?!\$)")
# Detects a pre-existing placeholder-shaped token in source (collision guard).
_PLACEHOLDER_RE = re.compile(rf"{PH_OPEN}MATH\d+{PH_CLOSE}")


def source_has_placeholder_collision(text: str) -> bool:
    """True if ``text`` already contains a ``⟦MATHi⟧``-shaped token, which
    would collide with our restore indexing (challenge §3)."""
    return bool(_PLACEHOLDER_RE.search(text))


def protect_math(text: str) -> tuple[str, list[str]]:
    """Replace every ``$$...$$`` then ``$...$`` run with ``⟦MATHi⟧``.

    Order matters: display first so ``$$`` is not split by the inline
    pattern. Returns ``(protected_text, store)`` where ``store[i]`` is the
    raw (delimiters included) i-th math run.
    """
    store: list[str] = []

    def take(m: re.Match[str]) -> str:
        store.append(m.group(0))
        return f"{PH_OPEN}MATH{len(store) - 1}{PH_CLOSE}"

    text = _DISPLAY_RE.sub(take, text)
    text = _INLINE_RE.sub(take, text)
    return text, store


def restore_math(text: str, store: list[str]) -> tuple[str, list[int]]:
    """Restore placeholders to their raw math. Returns ``(restored,
    missing)`` where ``missing`` is the list of store indices whose
    placeholder was absent from ``text`` (LLM dropped/corrupted it)."""
    missing: list[int] = []
    for i, raw in enumerate(store):
        token = f"{PH_OPEN}MATH{i}{PH_CLOSE}"
        if token in text:
            text = text.replace(token, raw)
        else:
            missing.append(i)
    return text, missing


def has_math(text: str) -> bool:
    """Cheap check: does ``text`` contain any paired ``$...$`` / ``$$...$$``?"""
    return bool(_DISPLAY_RE.search(text) or _INLINE_RE.search(text))


__all__ = [
    "PH_CLOSE",
    "PH_OPEN",
    "has_math",
    "protect_math",
    "restore_math",
    "source_has_placeholder_collision",
]
