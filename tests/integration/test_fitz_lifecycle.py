"""Resource lifecycle guarantees for the PyMuPDF wrapper."""

from __future__ import annotations

from pathlib import Path

import pytest

from ht_lens.extract._fitz import is_closed, iter_pages, open_pdf

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def test_open_pdf_closes_on_normal_exit() -> None:
    with open_pdf(FIXTURES / "sample_en.pdf") as doc:
        assert not is_closed(doc)
    assert is_closed(doc)


def test_open_pdf_close_on_exception() -> None:
    captured = []
    with pytest.raises(RuntimeError, match="boom"), open_pdf(FIXTURES / "sample_en.pdf") as doc:
        captured.append(doc)
        # iterate one page to ensure the document is in active use
        next(iter_pages(doc))
        raise RuntimeError("boom")
    assert captured
    assert is_closed(captured[0])
