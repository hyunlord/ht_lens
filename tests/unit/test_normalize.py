"""Snapshot normalization for deterministic comparisons."""

from __future__ import annotations

from typing import Any

from ht_lens.extract.normalize import (
    REDACTED,
    normalize_doc_meta,
    normalize_page,
    round_bbox,
)


def test_round_bbox_to_one_decimal() -> None:
    assert round_bbox((1.234, 2.5678, 3.911, 4.0)) == (1.2, 2.6, 3.9, 4.0)


def test_normalize_page_rounds_block_bboxes() -> None:
    page: dict[str, Any] = {
        "page_num": 1,
        "width": 612.0,
        "height": 792.0,
        "blocks": [
            {
                "id": "p1_b001",
                "type": "text",
                "bbox": [72.123, 90.999, 540.0, 105.555],
                "order": 1,
                "text": "x",
            }
        ],
    }
    out = normalize_page(page)
    assert out["blocks"][0]["bbox"] == [72.1, 91.0, 540.0, 105.6]
    # Original input must not be mutated.
    assert page["blocks"][0]["bbox"] == [72.123, 90.999, 540.0, 105.555]


def test_normalize_doc_meta_redacts_nondeterministic_fields() -> None:
    meta: dict[str, Any] = {
        "filename": "x.pdf",
        "num_pages": 3,
        "lang_guess": "en",
        "src_pdf_sha256": "abc",
        "extracted_at": "2026-01-01T00:00:00Z",
        "extractor_version": "0.0.0",
    }
    out = normalize_doc_meta(meta)
    assert out["src_pdf_sha256"] == REDACTED
    assert out["extracted_at"] == REDACTED
    assert out["extractor_version"] == REDACTED
    assert out["filename"] == "x.pdf"
    assert out["num_pages"] == 3
    assert out["lang_guess"] == "en"
