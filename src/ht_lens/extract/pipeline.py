"""End-to-end extraction pipeline."""

from __future__ import annotations

import contextlib
import hashlib
import os
import shutil
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from math import ceil
from pathlib import Path

from ht_lens.__version__ import __version__
from ht_lens.errors import OutputDirNotEmptyError
from ht_lens.extract._fitz import RawPage, iter_pages, open_pdf
from ht_lens.extract.blocks import GroupedBlock, group_page
from ht_lens.extract.language import LangGuess, aggregate_doc_lang, detect_page_lang
from ht_lens.extract.models import Block, DocMeta, PageDoc, RenderInfo
from ht_lens.extract.normalize import round_bbox
from ht_lens.extract.reading_order import order_blocks
from ht_lens.extract.render import render_page_png

_MANAGED_NAMES = {"pages", "images", "doc_meta.json"}


@dataclass(frozen=True)
class ExtractResult:
    out_dir: Path
    num_pages: int
    lang_guess: LangGuess
    page_block_counts: tuple[int, ...]


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _atomic_write_json(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f"{path.stem}.", suffix=".json.tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(payload)
        os.replace(tmp, path)
    except Exception:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(tmp)
        raise


def _clear_managed(out_dir: Path) -> None:
    for name in _MANAGED_NAMES:
        target = out_dir / name
        if target.is_dir():
            shutil.rmtree(target)
        elif target.exists():
            target.unlink()


def _ensure_out_dir(out_dir: Path, *, overwrite: bool) -> None:
    if not out_dir.exists():
        out_dir.mkdir(parents=True, exist_ok=True)
        return
    if not out_dir.is_dir():
        raise OutputDirNotEmptyError(f"output path exists and is not a directory: {out_dir}")
    if any(out_dir.iterdir()):
        if not overwrite:
            raise OutputDirNotEmptyError(
                f"output directory not empty: {out_dir} (use --overwrite to replace)"
            )
        _clear_managed(out_dir)


def _build_page_doc(
    raw: RawPage,
    ordered: list[GroupedBlock],
    dpi: int,
) -> PageDoc:
    scale = dpi / 72.0
    if raw.rotation in (90, 270):
        # rendered pixels swap when rotation is portrait/landscape transition
        pixel_w = ceil(raw.height * scale)
        pixel_h = ceil(raw.width * scale)
    else:
        pixel_w = ceil(raw.width * scale)
        pixel_h = ceil(raw.height * scale)

    blocks: list[Block] = []
    for idx, gb in enumerate(ordered, start=1):
        blocks.append(
            Block(
                id=f"p{raw.page_num}_b{idx:03d}",
                type=gb.type,
                bbox=round_bbox(gb.bbox),
                order=idx,
                text=gb.text,
            )
        )

    return PageDoc(
        page_num=raw.page_num,
        width=round(raw.width, 1),
        height=round(raw.height, 1),
        rotation=raw.rotation,
        render=RenderInfo(
            dpi=dpi,
            pixel_width=pixel_w,
            pixel_height=pixel_h,
            scale=round(scale, 3),
        ),
        unit="pt",
        blocks=blocks,
    )


def extract_pdf(
    pdf_path: Path,
    out_dir: Path,
    *,
    dpi: int = 200,
    save_images: bool = False,
    overwrite: bool = False,
) -> ExtractResult:
    """Extract a PDF into ``out_dir``: page PNGs, page JSONs, doc_meta.json."""
    if not pdf_path.exists() or not pdf_path.is_file():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    _ensure_out_dir(out_dir, overwrite=overwrite)
    pages_dir = out_dir / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "images").mkdir(parents=True, exist_ok=True)

    sha256 = _sha256_file(pdf_path)
    page_langs: list[LangGuess] = []
    page_block_counts: list[int] = []

    with open_pdf(pdf_path) as doc:
        for raw in iter_pages(doc):
            page_idx = raw.page_num - 1
            png_path = pages_dir / f"page_{raw.page_num:04d}.png"
            render_page_png(doc, page_idx, png_path, dpi=dpi)

            grouped = group_page(raw)
            ordered = order_blocks(grouped, page_width=raw.width)
            page_doc = _build_page_doc(raw, ordered, dpi=dpi)

            json_path = pages_dir / f"page_{raw.page_num:04d}.json"
            _atomic_write_json(json_path, page_doc.model_dump_json(indent=2))

            page_text = "\n".join(b.text for b in ordered if b.text)
            page_langs.append(detect_page_lang(page_text))
            page_block_counts.append(len(ordered))

    lang_guess = aggregate_doc_lang(page_langs)
    meta = DocMeta(
        filename=pdf_path.name,
        num_pages=len(page_langs),
        lang_guess=lang_guess,
        src_pdf_sha256=sha256,
        extracted_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        extractor_version=__version__,
    )
    _atomic_write_json(out_dir / "doc_meta.json", meta.model_dump_json(indent=2))

    return ExtractResult(
        out_dir=out_dir,
        num_pages=meta.num_pages,
        lang_guess=lang_guess,
        page_block_counts=tuple(page_block_counts),
    )
