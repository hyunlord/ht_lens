"""Phase 7a-2 verify — throughput benchmark.

Runs translate_document on a synthetic 30-block document with a mock LLM
that sleeps 0.1s per call, comparing concurrency=1 (sequential) vs
concurrency=7 (parallel). Reports wall-clock + speedup ratio.
"""

from __future__ import annotations

import asyncio
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ht_lens.db.base import Base
from ht_lens.db.models import Block, Document, Page
from ht_lens.db.session import ALEMBIC_HEAD, make_engine, make_session_factory
from ht_lens.llm.mock import MockLLMClient
from ht_lens.translate.pipeline import translate_document


class SleepyLLM(MockLLMClient):
    model_name = "bench"

    def __init__(self, sleep_s: float) -> None:
        self.sleep_s = sleep_s

    async def translate(self, text: str, src: str, tgt: str, *, context=None) -> str:
        await asyncio.sleep(self.sleep_s)
        return f"[KO] {text}"


async def _seed(factory: async_sessionmaker[AsyncSession], n_blocks: int) -> int:
    async with factory() as session:
        doc = Document(
            filename="bench.pdf",
            src_lang="en",
            tgt_lang="ko",
            status="ready_for_translation",
            created_at=datetime.now(UTC),
            src_pdf_sha256="b" * 64,
        )
        session.add(doc)
        await session.flush()
        page = Page(
            doc_id=doc.id,
            page_num=1,
            width=500.0,
            height=700.0,
            bg_image_path="/tmp/p.png",
            rotation=0,
            render_dpi=200,
            pixel_width=1000,
            pixel_height=1400,
        )
        session.add(page)
        await session.flush()
        for i in range(n_blocks):
            session.add(
                Block(
                    page_id=page.id,
                    block_local_id=f"b{i:03d}",
                    type="text",
                    bbox_json=json.dumps([0.0, float(i * 20), 100.0, float(i * 20 + 15)]),
                    order_idx=i,
                    original_text=f"Distinct paragraph number {i} for throughput benchmark.",
                )
            )
        await session.commit()
        return int(doc.id)


async def _run_once(db_path: Path, concurrency: int, sleep_s: float, n_blocks: int) -> float:
    engine = make_engine(db_path)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(
            text("CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32) NOT NULL)")
        )
        await conn.execute(text(f"INSERT INTO alembic_version VALUES ('{ALEMBIC_HEAD}')"))
    factory = make_session_factory(engine)
    doc_id = await _seed(factory, n_blocks)

    llm = SleepyLLM(sleep_s=sleep_s)
    async with factory() as session:
        start = time.monotonic()
        await translate_document(doc_id, session, llm, concurrency=concurrency)
        elapsed = time.monotonic() - start
    await engine.dispose()
    return elapsed


async def main() -> None:
    N_BLOCKS = 30
    SLEEP_S = 0.1

    results: dict[int, float] = {}
    for c in (1, 7):
        with TemporaryDirectory() as tmp:
            db_path = Path(tmp) / f"bench_c{c}.db"
            elapsed = await _run_once(db_path, c, SLEEP_S, N_BLOCKS)
            results[c] = elapsed
            throughput = (N_BLOCKS / elapsed) * 60
            print(f"  concurrency={c:>2}: {elapsed:.3f}s wall-clock, {throughput:.1f} blocks/min")

    speedup = results[1] / results[7]
    print(f"\n  speedup (c=1 / c=7): {speedup:.2f}x")
    print(f"  theoretical ceiling at c=7 with {SLEEP_S}s/block: {60 / SLEEP_S * 7:.0f} b/min")


if __name__ == "__main__":
    asyncio.run(main())
