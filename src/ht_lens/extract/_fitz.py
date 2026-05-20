"""PyMuPDF isolation layer.

This is the ONLY module allowed to import `fitz`. All other extract modules
consume the typed dataclasses defined here. ``# type: ignore`` and ``cast``
to PyMuPDF types are confined to this file.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, NewType, cast

import fitz  # type: ignore[import-untyped]

from ht_lens.errors import CorruptedPDFError, EncryptedPDFError

FitzDoc = NewType("FitzDoc", object)


@dataclass(frozen=True)
class RawSpan:
    text: str
    bbox: tuple[float, float, float, float]
    font: str
    size: float
    flags: int


@dataclass(frozen=True)
class RawLine:
    bbox: tuple[float, float, float, float]
    spans: tuple[RawSpan, ...]
    direction: tuple[float, float]


@dataclass(frozen=True)
class RawBlock:
    bbox: tuple[float, float, float, float]
    block_type: Literal["text", "image"]
    lines: tuple[RawLine, ...]


@dataclass(frozen=True)
class RawPage:
    page_num: int
    width: float
    height: float
    rotation: int
    blocks: tuple[RawBlock, ...]


def _as_bbox(seq: Any) -> tuple[float, float, float, float]:
    x0, y0, x1, y1 = (float(v) for v in seq)
    return (x0, y0, x1, y1)


@contextmanager
def open_pdf(path: Path) -> Iterator[FitzDoc]:
    """Open a PDF, raising domain errors for encryption/corruption.

    Always closes the document on exit, including on exceptions raised by
    callers iterating pages.
    """
    try:
        doc = fitz.open(str(path))
    except fitz.FileDataError as exc:
        raise CorruptedPDFError(f"failed to parse PDF: {path}") from exc
    except RuntimeError as exc:
        raise CorruptedPDFError(f"failed to open PDF: {path}: {exc}") from exc

    try:
        if doc.needs_pass:
            raise EncryptedPDFError(f"PDF is encrypted: {path}")
        yield cast(FitzDoc, doc)
    finally:
        try:
            doc.close()
        except Exception:  # noqa: BLE001 — close must not raise
            pass


def is_closed(doc: FitzDoc) -> bool:
    return bool(cast(Any, doc).is_closed)


def render_png(doc: FitzDoc, page_idx: int, dpi: int) -> bytes:
    """Render a single page (0-indexed) to PNG bytes at the given dpi."""
    page = cast(Any, doc).load_page(page_idx)
    pix = page.get_pixmap(dpi=dpi, alpha=False)
    data: bytes = pix.tobytes("png")
    return data


def iter_pages(doc: FitzDoc) -> Iterator[RawPage]:
    """Yield RawPage for each page, in document order (1-indexed page_num)."""
    fdoc = cast(Any, doc)
    for idx in range(fdoc.page_count):
        page = fdoc.load_page(idx)
        page_dict = page.get_text("dict", sort=True)
        width = float(page_dict.get("width", page.rect.width))
        height = float(page_dict.get("height", page.rect.height))
        rotation = int(page.rotation or 0)

        raw_blocks: list[RawBlock] = []
        for blk in page_dict.get("blocks", []):
            btype = blk.get("type", 0)
            bbox = _as_bbox(blk["bbox"])
            if btype == 1:
                raw_blocks.append(
                    RawBlock(bbox=bbox, block_type="image", lines=())
                )
                continue

            raw_lines: list[RawLine] = []
            for line in blk.get("lines", []):
                spans: list[RawSpan] = []
                for sp in line.get("spans", []):
                    spans.append(
                        RawSpan(
                            text=str(sp.get("text", "")),
                            bbox=_as_bbox(sp["bbox"]),
                            font=str(sp.get("font", "")),
                            size=float(sp.get("size", 0.0)),
                            flags=int(sp.get("flags", 0)),
                        )
                    )
                direction_raw = line.get("dir", (1.0, 0.0))
                direction = (float(direction_raw[0]), float(direction_raw[1]))
                raw_lines.append(
                    RawLine(
                        bbox=_as_bbox(line["bbox"]),
                        spans=tuple(spans),
                        direction=direction,
                    )
                )
            raw_blocks.append(
                RawBlock(bbox=bbox, block_type="text", lines=tuple(raw_lines))
            )

        yield RawPage(
            page_num=idx + 1,
            width=width,
            height=height,
            rotation=rotation,
            blocks=tuple(raw_blocks),
        )
