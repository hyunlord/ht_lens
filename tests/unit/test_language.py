"""Language detection wrapper around langdetect."""

from __future__ import annotations

from ht_lens.extract.language import aggregate_doc_lang, detect_page_lang


def test_short_text_is_unknown() -> None:
    assert detect_page_lang("short") == "unknown"
    assert detect_page_lang("") == "unknown"


def test_english_paragraph_detected() -> None:
    text = (
        "The quick brown fox jumps over the lazy dog. " * 4
    )
    assert detect_page_lang(text) == "en"


def test_korean_paragraph_detected() -> None:
    text = "한국어 텍스트를 검출합니다. " * 10
    assert detect_page_lang(text) == "ko"


def test_aggregate_majority_english_below_mixed_threshold() -> None:
    # 1 ko among 6 detectable (~0.167) is below the 0.20 mixed threshold.
    assert (
        aggregate_doc_lang(["en", "en", "en", "en", "en", "ko", "unknown"]) == "en"
    )


def test_aggregate_pure_korean() -> None:
    assert aggregate_doc_lang(["ko", "ko", "ko", "ko"]) == "ko"


def test_aggregate_mixed_triggers_when_minority_above_threshold() -> None:
    # 1 of 5 detectable = 20% → mixed (boundary inclusive)
    assert aggregate_doc_lang(["en", "en", "en", "en", "ko"]) == "mixed"


def test_aggregate_unknown_when_no_detectable_pages() -> None:
    assert aggregate_doc_lang(["unknown", "unknown"]) == "unknown"
    assert aggregate_doc_lang([]) == "unknown"
