"""Phase 8e-7 — merge split MinerU outputs into one ingestable content_list.

A PDF too large for a single CPU extraction (book2 1370p exceeded the 12h
``extract-mineru`` cap) is split into physical part PDFs, each extracted
separately. This module stitches those part outputs back into a single
MinerU-shaped output dir so the **existing** ``ingest_mineru_output()`` can
ingest them as one document - no parallel ingest path, so all the 8a
invariants (schema-head guard, filename-scoped overwrite, rollback, 1.x
coexistence, image cleanup) are inherited unchanged (challenge R1).

Merge rules (challenge R2-R6):
- ``page_idx += offset`` where ``offset`` = cumulative **source-PDF page count**
  of the earlier parts (read from each part's ``*_origin.pdf`` — NOT
  ``max(page_idx)+1``, which would drop trailing blank pages and corrupt the
  boundary). So the merged ``page_idx`` equals the absolute page in the full
  PDF — compare-mode renders and repair clips line up.
- Each part's ``page_idx`` is validated to be in ``[0, part_page_count)`` before
  offsetting (out-of-bounds → reject before any DB write).
- Image files are **namespaced per part** (``part{NNN}__{basename}``) so two
  parts with the same MinerU basename but different bytes can't overwrite each
  other (the basenames are NOT guaranteed content hashes).
- **Provenance** = the FULL source PDF, copied into the merged dir as
  ``<stem>_origin.pdf`` with ``markdown_path`` pointing beside it, so
  ``detect-repairs``/``repair-images`` clip the correct absolute page (never a
  part PDF).
- ``order_idx`` is NOT offset here: the merged content_list is concatenated in
  part order and ``parse_content_list`` assigns ``order_idx`` sequentially over
  the whole list at ingest time.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from ht_lens.errors import IngestError
from ht_lens.extract_mineru.runner import _discover_outputs


@dataclass
class MergePart:
    content_list_path: Path
    images_dir: Path | None
    origin_pdf: Path
    page_count: int


@dataclass
class MergedOutput:
    content_list_path: Path
    images_dir: Path
    markdown_path: Path


def _origin_pdf(auto_dir: Path) -> Path:
    cands = sorted(auto_dir.glob("*_origin.pdf"))
    if not cands:
        raise IngestError(f"no *_origin.pdf in {auto_dir} (needed for page-count offset)")
    return cands[0]


def discover_part(part_dir: Path) -> MergePart:
    """Discover one part's MinerU output (content_list + images + origin.pdf).
    ``part_dir`` may be the ``auto/`` dir or its parent (reuses the same
    discovery as ``ingest-mineru``). The page count comes from the part's
    source PDF, the authoritative boundary."""
    import fitz  # type: ignore[import-untyped]

    found = _discover_outputs(Path(part_dir))
    origin = _origin_pdf(found.content_list_path.parent)
    doc = fitz.open(str(origin))
    try:
        page_count = doc.page_count
    finally:
        doc.close()
    return MergePart(found.content_list_path, found.images_dir, origin, page_count)


def offset_items(
    items: list[dict[str, object]],
    *,
    page_offset: int,
    part_index: int,
    page_count: int,
) -> tuple[list[dict[str, object]], list[tuple[str, str]]]:
    """Pure: offset ``page_idx`` and namespace ``img_path`` for one part's raw
    content_list items. Returns ``(new_items, image_renames)`` where each rename
    is ``(original_basename, namespaced_basename)``. Raises ``IngestError`` on a
    ``page_idx`` outside ``[0, page_count)`` (challenge R4)."""
    out: list[dict[str, object]] = []
    renames: list[tuple[str, str]] = []
    for pos, item in enumerate(items):
        new = dict(item)
        raw_pi = new.get("page_idx")
        if not isinstance(raw_pi, int) or isinstance(raw_pi, bool):
            raise IngestError(f"part {part_index} item #{pos}: non-int page_idx {raw_pi!r}")
        if raw_pi < 0 or raw_pi >= page_count:
            raise IngestError(
                f"part {part_index} item #{pos}: page_idx {raw_pi} out of bounds "
                f"[0,{page_count}) — wrong part PDF or page range?"
            )
        new["page_idx"] = raw_pi + page_offset
        img = new.get("img_path")
        if isinstance(img, str) and img:
            base = Path(img).name
            ns = f"part{part_index:03d}__{base}"
            new["img_path"] = f"images/{ns}"
            renames.append((base, ns))
        out.append(new)
    return out, renames


def build_merged_output(
    parts: list[MergePart],
    *,
    dest_dir: Path,
    source_pdf: Path,
    filename_stem: str,
) -> MergedOutput:
    """Stitch ``parts`` (in order) into a MinerU-shaped output under
    ``dest_dir`` and return its content_list/images/markdown paths, ready for
    ``ingest_mineru_output``. Part order is the caller's contract; offsets are
    cumulative source-PDF page counts."""
    if not parts:
        raise IngestError("no parts to merge")
    dest_dir = Path(dest_dir)
    images_out = dest_dir / "images"
    images_out.mkdir(parents=True, exist_ok=True)

    merged: list[dict[str, object]] = []
    page_offset = 0
    for k, part in enumerate(parts):
        raw = json.loads(Path(part.content_list_path).read_text())
        if not isinstance(raw, list):
            raise IngestError(f"part {k} content_list is not a list: {part.content_list_path}")
        new_items, renames = offset_items(
            raw, page_offset=page_offset, part_index=k, page_count=part.page_count
        )
        for orig_base, ns_base in renames:
            if part.images_dir is None:
                raise IngestError(f"part {k} references images but has no images dir")
            src = Path(part.images_dir) / orig_base
            if not src.is_file():
                raise IngestError(f"part {k} image missing: {src}")
            shutil.copy2(src, images_out / ns_base)
        merged.extend(new_items)
        page_offset += part.page_count

    cl_path = dest_dir / f"{filename_stem}_content_list.json"
    cl_path.write_text(json.dumps(merged, ensure_ascii=False))
    # Provenance: the FULL source PDF as *_origin.pdf so repair tooling clips the
    # correct absolute page; markdown_path lives beside it.
    origin_dest = dest_dir / f"{filename_stem}_origin.pdf"
    if Path(source_pdf).resolve() != origin_dest.resolve():
        shutil.copy2(source_pdf, origin_dest)
    md_path = dest_dir / f"{filename_stem}.md"
    if not md_path.exists():
        md_path.write_text(f"# {filename_stem} (merged from {len(parts)} parts)\n")
    return MergedOutput(cl_path, images_out, md_path)


__all__ = [
    "MergePart",
    "MergedOutput",
    "build_merged_output",
    "discover_part",
    "offset_items",
]
