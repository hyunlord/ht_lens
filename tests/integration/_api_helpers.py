"""Shared helpers for Phase 3 API integration tests.

- ``seed_minimal_document``: insert one Document + N Pages + M Blocks per page
  + optional Translation rows + a PNG file on disk for each page.
- ``make_test_client``: build a FastAPI TestClient bound to ``api_db_path`` with
  an optional dependency override for the LLM client.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession

from ht_lens.db.models import Block, Document, Page, Translation


@dataclass
class SeededDoc:
    doc_id: int
    page_ids: list[int]
    block_ids: list[int]  # flattened, page-major
    image_paths: list[Path]


async def seed_minimal_document(
    session: AsyncSession,
    *,
    tmp_dir: Path,
    filename: str = "sample.pdf",
    blocks_per_page: int = 4,
    num_pages: int = 1,
    with_translations: bool = True,
    block_types: tuple[str, ...] | None = None,
) -> SeededDoc:
    """Insert one Document with pages, blocks (+optional translations) and PNGs.

    Blocks default to type='text'; ``block_types`` overrides per-block when len matches.
    """
    doc = Document(
        filename=filename,
        src_lang="en",
        tgt_lang="ko",
        status="translated" if with_translations else "ingested",
        created_at=datetime.utcnow(),
        src_pdf_sha256="0" * 64,
    )
    session.add(doc)
    await session.flush()

    page_ids: list[int] = []
    block_ids: list[int] = []
    image_paths: list[Path] = []

    for p in range(1, num_pages + 1):
        img_path = tmp_dir / f"p{p}.png"
        Image.new("RGB", (200, 300), color="white").save(img_path, "PNG")
        image_paths.append(img_path)
        page = Page(
            doc_id=doc.id,
            page_num=p,
            width=612.0,
            height=792.0,
            bg_image_path=str(img_path),
            rotation=0,
            render_dpi=200,
            pixel_width=200,
            pixel_height=300,
        )
        session.add(page)
        await session.flush()
        page_ids.append(page.id)

        for b in range(blocks_per_page):
            btype = "text"
            if block_types is not None and b < len(block_types):
                btype = block_types[b]
            block = Block(
                page_id=page.id,
                block_local_id=f"p{p}_b{b + 1:03d}",
                type=btype,
                bbox_json=json.dumps([10.0, 10.0 + b * 20, 200.0, 30.0 + b * 20]),
                order_idx=b,
                original_text=f"Page {p} Block {b + 1} original text",
            )
            session.add(block)
            await session.flush()
            block_ids.append(block.id)

            if with_translations and btype != "image":
                tr = Translation(
                    block_id=block.id,
                    translated_text=f"페이지 {p} 블록 {b + 1} 번역",
                    model="mock",
                    cache_key=f"key-{p}-{b + 1}",
                    status="translated",
                    updated_at=datetime.utcnow(),
                )
                session.add(tr)

    await session.commit()
    return SeededDoc(
        doc_id=doc.id,
        page_ids=page_ids,
        block_ids=block_ids,
        image_paths=image_paths,
    )


@contextmanager
def make_test_client(
    db_path: Path,
    *,
    llm_override: Any | None = None,
    skip_llm_check: bool = True,
) -> Iterator[TestClient]:
    """Return a TestClient with lifespan executed (DB path via env)."""
    prev_db = os.environ.get("HT_LENS_DB_URL")
    prev_skip = os.environ.get("HT_LENS_SKIP_LLM_CHECK")
    os.environ["HT_LENS_DB_URL"] = f"sqlite+aiosqlite:///{db_path}"
    if skip_llm_check:
        os.environ["HT_LENS_SKIP_LLM_CHECK"] = "1"
    try:
        from ht_lens.api.app import create_app
        from ht_lens.api.deps import get_llm_client

        app = create_app()
        if llm_override is not None:
            app.dependency_overrides[get_llm_client] = lambda: llm_override
        with TestClient(app) as client:
            yield client
    finally:
        if prev_db is None:
            os.environ.pop("HT_LENS_DB_URL", None)
        else:
            os.environ["HT_LENS_DB_URL"] = prev_db
        if prev_skip is None:
            os.environ.pop("HT_LENS_SKIP_LLM_CHECK", None)
        else:
            os.environ["HT_LENS_SKIP_LLM_CHECK"] = prev_skip


__all__ = ["SeededDoc", "make_test_client", "seed_minimal_document"]
