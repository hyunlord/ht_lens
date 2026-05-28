"""Phase 6h-1 — backfill CLI surface (Codex R2 §4 #4).

The plan delivers ``scripts/backfill_block_text.py`` as a CLI. Round 2
verify-cross pointed out that ``_async_main()`` / ``main()`` had no
test coverage: nobody asserted the exit codes, stderr/stdout contracts,
or that ``--dry-run`` produces zero writes. These tests drive the
script in-process via ``main()`` and capture its streams.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import fitz  # type: ignore[import-untyped]
import pytest
from sqlalchemy import select

from ht_lens.db.base import Base
from ht_lens.db.models import Block, Document, Page
from ht_lens.db.session import ALEMBIC_HEAD, make_engine, make_session_factory
from scripts.backfill_block_text import main as backfill_main


def _build_match_pdf(pdf: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((80, 100), "22.4.3", fontsize=12, fontname="helv")
    page.insert_text((150, 100), "Other applications", fontsize=12, fontname="helv")
    doc.save(str(pdf))
    doc.close()


def _seed_synced_db(db_path: Path, pdf: Path) -> tuple[int, list[int]]:
    """Initialise a sync sqlite at ``db_path`` whose Block rows match the
    extractor's output for ``pdf``. Returns (doc_id, [block_ids])."""
    import asyncio

    from ht_lens.extract._fitz import iter_pages, open_pdf
    from ht_lens.extract.blocks import group_page
    from ht_lens.extract.reading_order import order_blocks

    with open_pdf(pdf) as fdoc:
        raw = next(iter(iter_pages(fdoc)))
    extracted = order_blocks(group_page(raw))
    if not extracted:
        pytest.skip("PyMuPDF could not extract text from the synthetic PDF")

    holder: dict = {}

    async def _seed() -> None:
        engine = make_engine(db_path)
        async with engine.begin() as conn:
            from sqlalchemy import text

            await conn.run_sync(Base.metadata.create_all)
            await conn.execute(
                text(
                    "CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32) NOT NULL)"
                )
            )
            await conn.execute(text(f"INSERT INTO alembic_version VALUES ('{ALEMBIC_HEAD}')"))
        factory = make_session_factory(engine)
        async with factory() as session:
            d = Document(
                filename="cli.pdf",
                src_lang="en",
                tgt_lang="ko",
                status="ready_for_translation",
                created_at=datetime.now(UTC),
                src_pdf_sha256="d" * 64,
            )
            session.add(d)
            await session.flush()
            page_row = Page(
                doc_id=d.id,
                page_num=1,
                width=612.0,
                height=792.0,
                bg_image_path="/tmp/x.png",
                rotation=0,
                render_dpi=200,
                pixel_width=1700,
                pixel_height=2200,
            )
            session.add(page_row)
            await session.flush()
            for i, eb in enumerate(extracted):
                session.add(
                    Block(
                        page_id=page_row.id,
                        block_local_id=f"p1_b{i:03d}",
                        type=eb.type,
                        bbox_json=json.dumps(list(eb.bbox)),
                        order_idx=i,
                        original_text="STALE\nTEXT",
                    )
                )
            await session.commit()
            holder["doc_id"] = int(d.id)
            holder["block_ids"] = [
                b.id for b in (await session.execute(select(Block))).scalars().all()
            ]
        await engine.dispose()

    asyncio.run(_seed())
    return holder["doc_id"], holder["block_ids"]


def _read_all_blocks(db_path: Path) -> list[tuple[int, str, str]]:
    import asyncio

    rows_holder: list[tuple[int, str, str]] = []

    async def _read() -> None:
        engine = make_engine(db_path)
        factory = make_session_factory(engine)
        async with factory() as session:
            rows = (await session.execute(select(Block))).scalars().all()
            rows_holder.extend((b.id, b.original_text, b.bbox_json) for b in rows)
        await engine.dispose()

    asyncio.run(_read())
    return rows_holder


def test_backfill_cli_dry_run_exit_zero_no_writes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """``--dry-run`` must exit 0 and leave the DB untouched."""
    pdf = tmp_path / "match.pdf"
    db = tmp_path / "ht_lens.db"
    _build_match_pdf(pdf)
    doc_id, _ = _seed_synced_db(db, pdf)

    before = _read_all_blocks(db)
    rc = backfill_main(["--doc-id", str(doc_id), "--pdf", str(pdf), "--db", str(db), "--dry-run"])
    captured = capsys.readouterr()
    after = _read_all_blocks(db)

    assert rc == 0, (rc, captured.out, captured.err)
    assert after == before, "dry-run must not change any DB row"
    assert "dry-run OK" in captured.out
    assert "would update" in captured.out


def test_backfill_cli_apply_exit_zero_with_refresh_hint(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Apply mode must exit 0 and print the embedding-refresh reminder."""
    pdf = tmp_path / "match.pdf"
    db = tmp_path / "ht_lens.db"
    _build_match_pdf(pdf)
    doc_id, _ = _seed_synced_db(db, pdf)

    rc = backfill_main(["--doc-id", str(doc_id), "--pdf", str(pdf), "--db", str(db)])
    out = capsys.readouterr().out

    assert rc == 0
    assert "applied" in out and "updates" in out
    # The reminder must reference both the refresh command and the
    # specific doc id so the operator knows what to run.
    assert "ht-lens embed" in out
    assert f"--doc-id {doc_id}" in out


def test_backfill_cli_aborts_with_exit_two_on_mismatch(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Any abort (block count / page-set / bbox drift) must exit 2 and
    write the reason to stderr."""
    # PDF has 1 page; DB will have 2 — forces page-set abort.
    pdf = tmp_path / "single_page.pdf"
    _build_match_pdf(pdf)

    db = tmp_path / "ht_lens.db"
    pdf_2page = tmp_path / "two_page.pdf"
    # Build a 2-page PDF, seed the DB from it, then point CLI at the
    # 1-page PDF so the DB has an extra page that the PDF lacks.
    doc = fitz.open()
    for _ in range(2):
        page = doc.new_page(width=612, height=792)
        page.insert_text((80, 100), "22.4.3", fontsize=12, fontname="helv")
        page.insert_text((150, 100), "Other applications", fontsize=12, fontname="helv")
    doc.save(str(pdf_2page))
    doc.close()
    doc_id, _ = _seed_synced_db_2page(db, pdf_2page)

    before = _read_all_blocks(db)
    rc = backfill_main(["--doc-id", str(doc_id), "--pdf", str(pdf), "--db", str(db)])
    captured = capsys.readouterr()
    after = _read_all_blocks(db)

    assert rc == 2
    assert "ABORT" in captured.err
    assert after == before


def _seed_synced_db_2page(db_path: Path, pdf: Path) -> tuple[int, list[int]]:
    """Variant of ``_seed_synced_db`` that mirrors a 2-page PDF into the DB."""
    import asyncio

    from ht_lens.extract._fitz import iter_pages, open_pdf
    from ht_lens.extract.blocks import group_page
    from ht_lens.extract.reading_order import order_blocks

    with open_pdf(pdf) as fdoc:
        raw_pages = list(iter_pages(fdoc))
    extracted_by_page = [order_blocks(group_page(rp)) for rp in raw_pages]
    if not any(extracted_by_page):
        pytest.skip("PyMuPDF could not extract text from the synthetic PDF")

    holder: dict = {}

    async def _seed() -> None:
        engine = make_engine(db_path)
        async with engine.begin() as conn:
            from sqlalchemy import text

            await conn.run_sync(Base.metadata.create_all)
            await conn.execute(
                text(
                    "CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32) NOT NULL)"
                )
            )
            await conn.execute(text(f"INSERT INTO alembic_version VALUES ('{ALEMBIC_HEAD}')"))
        factory = make_session_factory(engine)
        async with factory() as session:
            d = Document(
                filename="cli2.pdf",
                src_lang="en",
                tgt_lang="ko",
                status="ready_for_translation",
                created_at=datetime.now(UTC),
                src_pdf_sha256="e" * 64,
            )
            session.add(d)
            await session.flush()
            for page_idx, extracted in enumerate(extracted_by_page, start=1):
                page_row = Page(
                    doc_id=d.id,
                    page_num=page_idx,
                    width=612.0,
                    height=792.0,
                    bg_image_path="/tmp/x.png",
                    rotation=0,
                    render_dpi=200,
                    pixel_width=1700,
                    pixel_height=2200,
                )
                session.add(page_row)
                await session.flush()
                for i, eb in enumerate(extracted):
                    session.add(
                        Block(
                            page_id=page_row.id,
                            block_local_id=f"p{page_idx}_b{i:03d}",
                            type=eb.type,
                            bbox_json=json.dumps(list(eb.bbox)),
                            order_idx=i,
                            original_text="STALE\nTEXT",
                        )
                    )
            await session.commit()
            holder["doc_id"] = int(d.id)
            holder["block_ids"] = [
                b.id for b in (await session.execute(select(Block))).scalars().all()
            ]
        await engine.dispose()

    asyncio.run(_seed())
    return holder["doc_id"], holder["block_ids"]
