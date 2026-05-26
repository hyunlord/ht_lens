"""Phase 7a R2 Planner-directed fix — upload pipeline auto-embed.

ROADMAP Phase 7a DoD requires the upload chain
(extract → ingest → translate → embed) to populate ``block_embeddings``
automatically so freshly uploaded PDFs are immediately retrievable by
cross-doc RAG. This test drives ``process_upload_job`` end-to-end with
the heavy stages monkeypatched, then asserts ``block_embeddings`` rows
exist for the new document.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ht_lens.db.base import Base
from ht_lens.db.models import (
    Block,
    BlockEmbedding,
    Document,
    Job,
    Page,
    Translation,
)
from ht_lens.db.session import make_engine, make_session_factory
from ht_lens.embedding.service import MockEmbeddingClient


@pytest_asyncio.fixture
async def db_factory(tmp_path: Path):
    db_path = tmp_path / "auto_embed.db"
    engine = make_engine(db_path)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = make_session_factory(engine)
    try:
        yield factory
    finally:
        await engine.dispose()


async def _seed_doc_with_translations(
    session: AsyncSession,
    *,
    filename: str = "sample.pdf",
    sha256: str = "f" * 64,
) -> int:
    """Seed a Document + Page + two translated text blocks. Returns doc_id."""
    doc = Document(
        filename=filename,
        src_lang="en",
        tgt_lang="ko",
        status="translated",
        created_at=datetime.now(UTC),
        src_pdf_sha256=sha256,
    )
    session.add(doc)
    await session.flush()
    page = Page(
        doc_id=doc.id,
        page_num=1,
        width=500.0,
        height=700.0,
        bg_image_path="/tmp/x.png",
        rotation=0,
        render_dpi=200,
        pixel_width=1000,
        pixel_height=1400,
    )
    session.add(page)
    await session.flush()
    texts = [
        "A long enough paragraph for auto-embed integration assertion.",
        "Another suitably long paragraph that should be embedded by backfill.",
    ]
    for i, text in enumerate(texts):
        blk = Block(
            page_id=page.id,
            block_local_id=f"b{i:03d}",
            type="text",
            bbox_json=json.dumps([0.0, float(i), 100.0, float(i + 15)]),
            order_idx=i,
            original_text=text,
        )
        session.add(blk)
        await session.flush()
        session.add(
            Translation(
                block_id=blk.id,
                translated_text=f"[KO] {text}",
                model="mock",
                status="translated",
                updated_at=datetime.now(UTC),
            )
        )
    await session.commit()
    return doc.id


async def _seed_pending_job(
    factory: async_sessionmaker[AsyncSession],
    upload_path: Path,
    sha256: str,
) -> int:
    """Create a pending Job row backed by a real file on disk."""
    async with factory() as session:
        job = Job(
            type="process_upload",
            status="pending",
            progress_pct=0,
            upload_path=str(upload_path),
            upload_filename=upload_path.name,
            upload_sha256=sha256,
            created_at=datetime.utcnow(),
        )
        session.add(job)
        await session.flush()
        job_id = job.id
        await session.commit()
    return job_id


def _build_fake_app(
    factory: async_sessionmaker[AsyncSession],
    *,
    embedding_client,
) -> SimpleNamespace:
    """Minimal fake FastAPI app: only ``app.state`` access matters here."""

    class _Sem:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

    state = SimpleNamespace(
        session_factory=factory,
        translate_llm=object(),
        chat_llm=object(),
        embedding_client=embedding_client,
        chat_semaphore=_Sem(),
    )
    return SimpleNamespace(state=state)


@pytest.mark.asyncio
async def test_process_upload_job_auto_embeds_after_translate(
    db_factory: async_sessionmaker[AsyncSession],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Auto-embed runs as part of the upload pipeline and produces
    ``block_embeddings`` rows for the new document."""
    from ht_lens.jobs import pipeline as job_pipeline

    sha256 = "a" * 64
    upload_path = tmp_path / "uploads" / sha256 / "doc.pdf"
    upload_path.parent.mkdir(parents=True, exist_ok=True)
    upload_path.write_bytes(b"%PDF-fake")

    job_id = await _seed_pending_job(db_factory, upload_path, sha256)

    # Pre-seed translated doc so backfill has candidate blocks.
    async with db_factory() as session:
        doc_id = await _seed_doc_with_translations(session, filename="doc.pdf", sha256=sha256)

    # Heavy stages: monkeypatch to no-op / shortcut, returning the seeded doc.
    async def _fake_to_thread(fn, *args, **kwargs):
        return None

    monkeypatch.setattr(job_pipeline.asyncio, "to_thread", _fake_to_thread)

    async def _fake_ingest(*args, **kwargs):
        return SimpleNamespace(document_id=doc_id)

    monkeypatch.setattr(job_pipeline, "ingest_extract_dir", _fake_ingest)

    async def _fake_translate(*args, **kwargs):
        return None

    monkeypatch.setattr(job_pipeline, "translate_document", _fake_translate)

    async def _fake_summarize(*args, **kwargs):
        return "요약"

    monkeypatch.setattr(job_pipeline, "summarize_document", _fake_summarize)

    embed_client = MockEmbeddingClient(dim=8)
    app = _build_fake_app(db_factory, embedding_client=embed_client)

    await job_pipeline.process_upload_job(job_id, app)

    # Job reached terminal ``done`` state.
    async with db_factory() as session:
        job = await session.get(Job, job_id)
        assert job is not None
        assert job.status == "done", (
            f"job did not reach done: status={job.status} err={job.error_message}"
        )
        # block_embeddings rows exist for this doc.
        count = (
            await session.execute(
                select(func.count())
                .select_from(BlockEmbedding)
                .join(Block, Block.id == BlockEmbedding.block_id)
                .join(Page, Page.id == Block.page_id)
                .where(Page.doc_id == doc_id)
            )
        ).scalar_one()
    assert count == 2, f"expected 2 auto-embedded blocks, got {count}"


@pytest.mark.asyncio
async def test_process_upload_job_survives_embed_failure(
    db_factory: async_sessionmaker[AsyncSession],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If the embedding step raises, the job still finishes ``done`` and
    records a non-fatal warning in ``error_message`` (graceful degradation).
    """
    from ht_lens.jobs import pipeline as job_pipeline

    sha256 = "b" * 64
    upload_path = tmp_path / "uploads" / sha256 / "doc.pdf"
    upload_path.parent.mkdir(parents=True, exist_ok=True)
    upload_path.write_bytes(b"%PDF-fake")

    job_id = await _seed_pending_job(db_factory, upload_path, sha256)
    async with db_factory() as session:
        doc_id = await _seed_doc_with_translations(session, filename="doc.pdf", sha256=sha256)

    async def _fake_to_thread(fn, *args, **kwargs):
        return None

    monkeypatch.setattr(job_pipeline.asyncio, "to_thread", _fake_to_thread)

    async def _fake_ingest(*args, **kwargs):
        return SimpleNamespace(document_id=doc_id)

    monkeypatch.setattr(job_pipeline, "ingest_extract_dir", _fake_ingest)

    async def _fake_translate(*args, **kwargs):
        return None

    monkeypatch.setattr(job_pipeline, "translate_document", _fake_translate)

    async def _fake_summarize(*args, **kwargs):
        return "요약"

    monkeypatch.setattr(job_pipeline, "summarize_document", _fake_summarize)

    class _BrokenEmbeddingClient:
        model_name = "broken"
        dim = 8

        def encode(self, texts):
            raise RuntimeError("simulated embed failure")

    app = _build_fake_app(db_factory, embedding_client=_BrokenEmbeddingClient())

    await job_pipeline.process_upload_job(job_id, app)

    async with db_factory() as session:
        job = await session.get(Job, job_id)
        assert job is not None
        assert job.status == "done", f"embed failure must not block job done; status={job.status}"
        assert job.error_message is not None
        assert "임베딩 실패" in job.error_message, (
            f"expected embedding warning in error_message; got {job.error_message!r}"
        )


@pytest.mark.asyncio
async def test_process_upload_job_skips_embed_when_client_unavailable(
    db_factory: async_sessionmaker[AsyncSession],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """RAG_DISABLED / bge-m3 init failed → ``embedding_client is None``.
    Job still finishes ``done`` with no block_embeddings created."""
    from ht_lens.jobs import pipeline as job_pipeline

    sha256 = "c" * 64
    upload_path = tmp_path / "uploads" / sha256 / "doc.pdf"
    upload_path.parent.mkdir(parents=True, exist_ok=True)
    upload_path.write_bytes(b"%PDF-fake")

    job_id = await _seed_pending_job(db_factory, upload_path, sha256)
    async with db_factory() as session:
        doc_id = await _seed_doc_with_translations(session, filename="doc.pdf", sha256=sha256)

    async def _fake_to_thread(fn, *args, **kwargs):
        return None

    monkeypatch.setattr(job_pipeline.asyncio, "to_thread", _fake_to_thread)

    async def _fake_ingest(*args, **kwargs):
        return SimpleNamespace(document_id=doc_id)

    monkeypatch.setattr(job_pipeline, "ingest_extract_dir", _fake_ingest)

    async def _fake_translate(*args, **kwargs):
        return None

    monkeypatch.setattr(job_pipeline, "translate_document", _fake_translate)

    async def _fake_summarize(*args, **kwargs):
        return "요약"

    monkeypatch.setattr(job_pipeline, "summarize_document", _fake_summarize)

    app = _build_fake_app(db_factory, embedding_client=None)

    await job_pipeline.process_upload_job(job_id, app)

    async with db_factory() as session:
        job = await session.get(Job, job_id)
        assert job is not None
        assert job.status == "done"
        count = (
            await session.execute(select(func.count()).select_from(BlockEmbedding))
        ).scalar_one()
    assert count == 0, f"no embedding client → no embeddings, got {count}"
