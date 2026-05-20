"""Language detection via langdetect (deterministic seed)."""

from __future__ import annotations

from collections import Counter
from typing import Literal, cast

from langdetect import (  # type: ignore[import-untyped]
    DetectorFactory,
    LangDetectException,
    detect,
)

DetectorFactory.seed = 0

LangGuess = Literal["en", "ko", "mixed", "unknown"]

_MIN_CHARS = 50
_MIXED_RATIO = 0.20  # tuned on sample_mixed: 1 ko / 5 detectable pages = 0.20


def detect_page_lang(text: str) -> LangGuess:
    """Detect language for a single page's concatenated text."""
    stripped = text.strip()
    if len(stripped) < _MIN_CHARS:
        return "unknown"
    try:
        code = detect(stripped)
    except LangDetectException:
        return "unknown"
    if code == "ko":
        return "ko"
    if code == "en":
        return "en"
    return "unknown"


def aggregate_doc_lang(page_langs: list[LangGuess]) -> LangGuess:
    """Roll up page languages to a single document-level guess."""
    relevant = [lg for lg in page_langs if lg in ("en", "ko")]
    if not relevant:
        return "unknown"
    counts = Counter(relevant)
    total = sum(counts.values())
    if total == 0:
        return "unknown"
    minor_ratio = (total - max(counts.values())) / total
    if minor_ratio >= _MIXED_RATIO:
        return "mixed"
    top, _ = counts.most_common(1)[0]
    return cast(LangGuess, top)
