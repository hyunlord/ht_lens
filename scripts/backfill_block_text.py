"""Phase 6h-1 — backfill Block.original_text + bbox for one document.

The Phase 6h-1 fix in ``src/ht_lens/extract/blocks.py`` changes how
multi-fragment same-visual-line text is stored: pre-fix ``"22.4.3\\n
Other applications"`` becomes ``"22.4.3 Other applications"``. The fix
only affects newly extracted documents; this script re-runs the
extraction against the original PDF and rewrites ``Block.original_text``
+ ``Block.bbox_json`` in place, preserving every ``Block.id`` (so the
existing ``translations`` and ``block_embeddings`` rows stay attached).

Per Codex debate §3.4, the rewrite is *per-document atomic*: every
page of the document must match by block-count and bbox-proximity
before any DB write happens. Any mismatch aborts the whole document
without touching the database. Run with ``--dry-run`` first to inspect
the proposed updates.

After applying the fix, the stored ``text_source_hash`` for affected
blocks changes; the existing ``block_embeddings`` rows are now stale.
The script prints a reminder to refresh embeddings via
``ht-lens embed --doc-id N`` (Phase 7a auto-detects source_hash
mismatch).

Usage:
  uv run python scripts/backfill_block_text.py --doc-id 7 --pdf book2.pdf --dry-run
  uv run python scripts/backfill_block_text.py --doc-id 7 --pdf book2.pdf
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ht_lens.db.models import Block, Document, Page
from ht_lens.db.session import make_engine, make_session_factory
from ht_lens.extract._fitz import iter_pages, open_pdf
from ht_lens.extract.blocks import GroupedBlock, group_page
from ht_lens.extract.reading_order import order_blocks

_BBOX_DRIFT_TOLERANCE_PT = 20.0
_DEFAULT_DB = Path("data/ht_lens.db")


@dataclass(frozen=True)
class ProposedUpdate:
    block_id: int
    page_num: int
    new_bbox: tuple[float, float, float, float]
    new_text: str


@dataclass(frozen=True)
class BackfillResult:
    status: str  # "ok" | "dry_run" | "abort"
    reason: str | None
    proposed: tuple[ProposedUpdate, ...]
    pages_checked: int


def _db_path_from_env() -> Path:
    url = os.environ.get("HT_LENS_DB_URL", "")
    if url.startswith("sqlite+aiosqlite:///"):
        return Path(url.removeprefix("sqlite+aiosqlite:///"))
    return _DEFAULT_DB


def _center(bbox: Sequence[float]) -> tuple[float, float]:
    return ((bbox[0] + bbox[2]) / 2.0, (bbox[1] + bbox[3]) / 2.0)


def _extract_grouped_pages(pdf_path: Path) -> list[tuple[int, list[GroupedBlock]]]:
    """Return [(page_num_1_indexed, [GroupedBlock in reading order]), ...]."""
    pages: list[tuple[int, list[GroupedBlock]]] = []
    with open_pdf(pdf_path) as doc:
        for raw_page in iter_pages(doc):
            grouped = group_page(raw_page)
            ordered = order_blocks(grouped)
            pages.append((raw_page.page_num, list(ordered)))
    return pages


async def _load_doc_pages(
    factory: async_sessionmaker[AsyncSession], doc_id: int
) -> dict[int, list[Block]]:
    """Return {page_num: [Block sorted by order_idx]}."""
    async with factory() as session:
        # Document must exist.
        doc = await session.get(Document, doc_id)
        if doc is None:
            raise ValueError(f"document {doc_id} not found")
        rows = await session.execute(
            select(Block, Page.page_num)
            .join(Page, Page.id == Block.page_id)
            .where(Page.doc_id == doc_id)
            .order_by(Page.page_num, Block.order_idx)
        )
        out: dict[int, list[Block]] = {}
        for blk, page_num in rows.all():
            out.setdefault(page_num, []).append(blk)
        return out


async def backfill_doc(
    factory: async_sessionmaker[AsyncSession],
    doc_id: int,
    pdf_path: Path,
    *,
    dry_run: bool,
) -> BackfillResult:
    """Per-doc atomic backfill: validate all pages first, then commit."""
    db_pages = await _load_doc_pages(factory, doc_id)
    new_pages = _extract_grouped_pages(pdf_path)

    # Phase 6h-1 R1 fix (Codex §4 #1): per-doc atomic means BOTH directions.
    # Reject when the PDF is missing pages that the DB has — a truncated or
    # mismatched PDF cannot validate, so no per-page updates are committed
    # for the pages it does cover.
    new_page_nums = {pn for pn, _ in new_pages}
    db_page_nums = set(db_pages.keys())
    db_only = sorted(db_page_nums - new_page_nums)
    if db_only:
        return BackfillResult(
            status="abort",
            reason=(
                f"PDF is missing {len(db_only)} page(s) that the DB has: "
                f"{db_only[:10]}{'...' if len(db_only) > 10 else ''}"
            ),
            proposed=(),
            pages_checked=0,
        )

    proposed: list[ProposedUpdate] = []
    for page_num, new_blocks in new_pages:
        old_blocks = db_pages.get(page_num)
        if old_blocks is None:
            return BackfillResult(
                status="abort",
                reason=f"DB has no row for page {page_num}",
                proposed=(),
                pages_checked=page_num,
            )
        if len(old_blocks) != len(new_blocks):
            return BackfillResult(
                status="abort",
                reason=(
                    f"block count mismatch at page {page_num}: "
                    f"DB={len(old_blocks)} new={len(new_blocks)}"
                ),
                proposed=(),
                pages_checked=page_num,
            )
        for old, new in zip(old_blocks, new_blocks, strict=True):
            ocx, ocy = _center(old.bbox)
            ncx, ncy = _center(new.bbox)
            if (
                abs(ocx - ncx) > _BBOX_DRIFT_TOLERANCE_PT
                or abs(ocy - ncy) > _BBOX_DRIFT_TOLERANCE_PT
            ):
                return BackfillResult(
                    status="abort",
                    reason=(
                        f"bbox center drift > {_BBOX_DRIFT_TOLERANCE_PT}pt "
                        f"at page {page_num} block id={old.id} "
                        f"(old=({ocx:.1f},{ocy:.1f}) new=({ncx:.1f},{ncy:.1f}))"
                    ),
                    proposed=(),
                    pages_checked=page_num,
                )
            if old.bbox == new.bbox and old.original_text == new.text:
                continue  # no-op
            proposed.append(
                ProposedUpdate(
                    block_id=old.id,
                    page_num=page_num,
                    new_bbox=new.bbox,
                    new_text=new.text,
                )
            )

    if dry_run:
        return BackfillResult(
            status="dry_run",
            reason=None,
            proposed=tuple(proposed),
            pages_checked=len(new_pages),
        )

    async with factory() as session:
        for upd in proposed:
            await session.execute(
                update(Block)
                .where(Block.id == upd.block_id)
                .values(
                    bbox_json=json.dumps(list(upd.new_bbox)),
                    original_text=upd.new_text,
                )
            )
        await session.commit()

    return BackfillResult(
        status="ok",
        reason=None,
        proposed=tuple(proposed),
        pages_checked=len(new_pages),
    )


async def _async_main(args: argparse.Namespace) -> int:
    db_path = Path(args.db) if args.db else _db_path_from_env()
    engine = make_engine(db_path)
    factory = make_session_factory(engine)
    try:
        result = await backfill_doc(factory, args.doc_id, Path(args.pdf), dry_run=args.dry_run)
    finally:
        await engine.dispose()

    if result.status == "abort":
        print(f"[backfill] ABORT (no DB writes): {result.reason}", file=sys.stderr)
        print(f"[backfill] pages checked: {result.pages_checked}", file=sys.stderr)
        return 2

    if result.status == "dry_run":
        print(
            f"[backfill] dry-run OK: would update {len(result.proposed)} blocks "
            f"across {result.pages_checked} pages."
        )
        if result.proposed:
            sample = result.proposed[:5]
            for p in sample:
                print(f"  block_id={p.block_id} page={p.page_num} text={p.new_text[:60]!r}")
        return 0

    print(f"[backfill] applied {len(result.proposed)} updates across {result.pages_checked} pages.")
    if result.proposed:
        print(
            f"[backfill] block_embeddings may now be stale for these blocks. "
            f"Run `ht-lens embed --doc-id {args.doc_id}` to refresh "
            f"(Phase 7a auto-detects source_hash mismatch)."
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else "")
    parser.add_argument("--doc-id", type=int, required=True, help="Document ID to rewrite.")
    parser.add_argument(
        "--pdf",
        type=str,
        required=True,
        help="Path to the original PDF (must match the existing extraction).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate + report proposed updates without writing.",
    )
    parser.add_argument("--db", type=str, default=None, help="DB path (defaults to env).")
    args = parser.parse_args(argv)
    return asyncio.run(_async_main(args))


if __name__ == "__main__":
    raise SystemExit(main())
