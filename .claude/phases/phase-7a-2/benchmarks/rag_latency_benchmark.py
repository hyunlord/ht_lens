"""Phase 7a-2 verify — RAG query-vector lookup benchmark.

Measures only the ``get_or_encode_block_vector()`` helper (the optimization
target), comparing the stored-vector hit path against the encode() fallback.
This is NOT an end-to-end ``/blocks/{id}/related`` or ``/threads/{id}/explain``
benchmark — those routes also run cross-doc search and prompt assembly. The
end-to-end behavior (encode() call_count == 0 on the actual routes) is
locked by ``tests/integration/test_api_related.py`` and
``tests/integration/test_api_messages.py::test_explain_reuses_stored_vector_no_encode_call``
instead.

The helper measurement here demonstrates the relative speedup
(575ms cold encode vs ~0.2ms stored read) using a ``SlowEmbeddingClient``
that simulates real bge-m3 CPU latency. Live bge-m3 measurements are out
of scope for this benchmark (deferred to doc 7 retranslate run).
"""

from __future__ import annotations

import asyncio
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
from PIL import Image
from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ht_lens.db.base import Base
from ht_lens.db.models import Block, BlockEmbedding, Document, Page, Translation
from ht_lens.db.session import ALEMBIC_HEAD, make_engine, make_session_factory
from ht_lens.embedding.lookup import get_or_encode_block_vector
from ht_lens.embedding.service import MockEmbeddingClient, text_source_hash
from ht_lens.embedding.store import upsert_embedding


class SlowEmbeddingClient(MockEmbeddingClient):
    """MockEmbeddingClient that simulates bge-m3 CPU latency (575ms / call)."""

    def __init__(self, dim: int = 32, encode_latency_s: float = 0.575) -> None:
        super().__init__(dim=dim)
        self.encode_latency_s = encode_latency_s
        self.encode_count = 0

    def encode(self, texts: list[str]) -> np.ndarray:
        self.encode_count += len(texts)
        time.sleep(self.encode_latency_s)
        return super().encode(texts)


async def _seed(factory: async_sessionmaker[AsyncSession], tmp_dir: Path) -> int:
    """Seed 1 doc, 5 blocks, with embeddings stored. Returns doc_id."""
    img = tmp_dir / "p.png"
    Image.new("RGB", (200, 300), color="white").save(img, "PNG")

    client = MockEmbeddingClient(dim=32)
    async with factory() as session:
        doc = Document(
            filename="rag.pdf",
            src_lang="en",
            tgt_lang="ko",
            status="translated",
            created_at=datetime.now(UTC),
            src_pdf_sha256="r" * 64,
        )
        session.add(doc)
        await session.flush()
        page = Page(
            doc_id=doc.id,
            page_num=1,
            width=500.0,
            height=700.0,
            bg_image_path=str(img),
            rotation=0,
            render_dpi=200,
            pixel_width=1000,
            pixel_height=1400,
        )
        session.add(page)
        await session.flush()
        for i in range(5):
            content = (
                f"Distinct paragraph index {i} long enough for embedding benchmark, "
                "with stable text matched against the stored hash."
            )
            blk = Block(
                page_id=page.id,
                block_local_id=f"b{i:03d}",
                type="text",
                bbox_json=json.dumps([0.0, float(i * 20), 100.0, float(i * 20 + 15)]),
                order_idx=i,
                original_text=content,
            )
            session.add(blk)
            await session.flush()
            session.add(
                Translation(
                    block_id=blk.id,
                    translated_text=f"[KO] {content}",
                    model="mock",
                    status="translated",
                    updated_at=datetime.now(UTC),
                )
            )
            vec = client.encode([content])[0]
            await upsert_embedding(
                session,
                block_id=blk.id,
                vector=vec,
                model=client.model_name,
                dim=client.dim,
                source_hash=text_source_hash(content),
            )
        await session.commit()
        return int(doc.id)


async def _measure(factory: async_sessionmaker[AsyncSession], n_samples: int = 3) -> dict:
    """Measure get_or_encode_block_vector latency on 5 blocks x n_samples each.

    Compares stored-vector hit path vs fallback (after deleting the row).
    """
    client = SlowEmbeddingClient(dim=32, encode_latency_s=0.575)

    async with factory() as session:
        blocks = (await session.execute(text("SELECT id FROM blocks"))).all()
        block_ids = [r[0] for r in blocks]

    # --- Stored vector reuse (hit) ---
    hit_latencies: list[float] = []
    async with factory() as session:
        for _sample in range(n_samples):
            for bid in block_ids:
                blk = await session.get(Block, bid)
                assert blk is not None
                start = time.monotonic()
                await get_or_encode_block_vector(session, client, blk)
                hit_latencies.append((time.monotonic() - start) * 1000)
    encode_count_hit = client.encode_count

    # --- Fallback (after deleting embeddings) ---
    async with factory() as session:
        await session.execute(delete(BlockEmbedding))
        await session.commit()

    miss_latencies: list[float] = []
    async with factory() as session:
        for bid in block_ids:
            blk = await session.get(Block, bid)
            assert blk is not None
            start = time.monotonic()
            await get_or_encode_block_vector(session, client, blk)
            miss_latencies.append((time.monotonic() - start) * 1000)
    encode_count_miss = client.encode_count - encode_count_hit

    def stats(xs: list[float]) -> dict:
        xs = sorted(xs)
        n = len(xs)
        return {
            "n": n,
            "p50": xs[n // 2],
            "p95": xs[max(0, int(n * 0.95) - 1)],
            "max": xs[-1],
            "mean": sum(xs) / n,
        }

    return {
        "hit": stats(hit_latencies),
        "hit_encode_count": encode_count_hit,
        "miss": stats(miss_latencies),
        "miss_encode_count": encode_count_miss,
    }


async def main() -> None:
    with TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "rag_bench.db"
        engine = make_engine(db_path)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.execute(
                text(
                    "CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32) NOT NULL)"
                )
            )
            await conn.execute(text(f"INSERT INTO alembic_version VALUES ('{ALEMBIC_HEAD}')"))
        factory = make_session_factory(engine)
        await _seed(factory, Path(tmp))
        results = await _measure(factory, n_samples=3)
        await engine.dispose()

    print("\nStored-vector reuse (15 samples = 5 blocks x 3):")
    h = results["hit"]
    print(
        f"  p50={h['p50']:.2f}ms  p95={h['p95']:.2f}ms  "
        f"max={h['max']:.2f}ms  mean={h['mean']:.2f}ms"
    )
    print(f"  encode() calls during hit phase: {results['hit_encode_count']} (expected 0)")
    print("\nFallback / cold encode (5 samples after deletion):")
    m = results["miss"]
    print(
        f"  p50={m['p50']:.2f}ms  p95={m['p95']:.2f}ms  "
        f"max={m['max']:.2f}ms  mean={m['mean']:.2f}ms"
    )
    print(f"  encode() calls during miss phase: {results['miss_encode_count']} (expected 5)")
    verdict = "PASS" if h["p95"] < 500 else "FAIL"
    print(
        f"\nHelper-level p95 < 500ms (stored vector hit path): {verdict}\n"
        "Note: end-to-end /explain p95 includes search + prompt assembly. "
        "See tests/integration/test_api_messages.py for the route-level lock."
    )


if __name__ == "__main__":
    asyncio.run(main())
