"""Phase 6e — verify the LLM-routing split end-to-end.

Covers the R1 missing tests (challenge §5):
1. chat override (``chat_llm_override``) reaches messages chat handler.
2. translate override (``translate_llm_override``) reaches retranslate
   handler.
3. summarize route uses the chat-scoped client.
4. process_upload_job routes summary to chat_llm (uses
   ``chat_llm_override``).

These tests use the new scoped overrides on ``make_test_client`` to prove
the dispatch table at the dependency-injection layer is wired correctly.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from ht_lens.db.models import Block, Document, Page, Thread
from ht_lens.db.session import make_engine, make_session_factory
from ht_lens.llm.mock import MockLLMClient

from ._api_helpers import make_test_client


class _TaggedLLM(MockLLMClient):
    """A mock LLM with a recognisable tag so we can confirm which
    dependency the route actually received."""

    def __init__(self, tag: str) -> None:
        super().__init__()
        self.tag = tag

    async def chat(self, messages, *, system=None):  # type: ignore[override]
        return f"<<{self.tag}_CHAT>>"

    async def translate(self, text, src, tgt, *, context=None):  # type: ignore[override]
        return f"<<{self.tag}_TR>> {text}"


async def _seed_doc_with_thread(db_path: Path) -> tuple[int, int]:
    """Insert one Document + Page + Block + Thread; return (block_id, thread_id)."""
    engine = make_engine(db_path)
    factory = make_session_factory(engine)
    async with factory() as session:
        doc = Document(
            filename="phase6e.pdf",
            src_lang="en",
            tgt_lang="ko",
            status="translated",
            src_pdf_sha256="6" * 64,
            created_at=datetime.utcnow(),
        )
        session.add(doc)
        await session.flush()
        page = Page(
            doc_id=doc.id,
            page_num=1,
            width=600,
            height=800,
            bg_image_path="/tmp/none.png",
            rotation=0,
            render_dpi=200,
            pixel_width=1200,
            pixel_height=1600,
        )
        session.add(page)
        await session.flush()
        block = Block(
            page_id=page.id,
            block_local_id="b1",
            type="text",
            bbox_json="[0,0,100,20]",
            order_idx=0,
            original_text="Hello world.",
        )
        session.add(block)
        await session.flush()
        thread = Thread(
            block_id=block.id,
            title="phase6e thread",
            created_at=datetime.utcnow(),
        )
        session.add(thread)
        await session.commit()
        await session.refresh(block)
        await session.refresh(thread)
        block_id = block.id
        thread_id = thread.id
    await engine.dispose()
    return block_id, thread_id


@pytest.mark.asyncio
async def test_chat_llm_override_reaches_explain_endpoint(api_db_path: Path) -> None:
    """``chat_llm_override`` must replace the chat dependency for the
    explain handler. If the override never reaches it the response would
    come from MockLLMClient's default echo, not our tagged variant."""
    _block_id, thread_id = await _seed_doc_with_thread(api_db_path)
    chat_mock = _TaggedLLM("CHAT_OVERRIDE")
    translate_mock = _TaggedLLM("TRANSLATE_OVERRIDE")
    with make_test_client(
        api_db_path,
        translate_llm_override=translate_mock,
        chat_llm_override=chat_mock,
    ) as client:
        resp = client.post(f"/threads/{thread_id}/explain")
    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["content"] == "<<CHAT_OVERRIDE_CHAT>>"


@pytest.mark.asyncio
async def test_translate_llm_override_reaches_retranslate_endpoint(
    api_db_path: Path,
) -> None:
    """``translate_llm_override`` must replace the translate dependency
    for ``POST /blocks/{id}/retranslate``."""
    block_id, _ = await _seed_doc_with_thread(api_db_path)
    chat_mock = _TaggedLLM("CHAT_OVERRIDE")
    translate_mock = _TaggedLLM("TRANSLATE_OVERRIDE")
    with make_test_client(
        api_db_path,
        translate_llm_override=translate_mock,
        chat_llm_override=chat_mock,
    ) as client:
        resp = client.post(f"/blocks/{block_id}/retranslate")
    assert resp.status_code == 202, resp.text
    body = resp.json()
    # The translation field should carry the translate-mock prefix.
    assert "<<TRANSLATE_OVERRIDE_TR>>" in body["translation"]["translated_text"]


@pytest.mark.asyncio
async def test_summarize_uses_chat_llm_override(api_db_path: Path, tmp_path: Path) -> None:
    """``POST /documents/{id}/summarize`` must route through the
    chat dependency, not the translate one."""
    from ._api_helpers import seed_minimal_document

    engine = make_engine(api_db_path)
    factory = make_session_factory(engine)
    async with factory() as session:
        seeded = await seed_minimal_document(session, tmp_dir=tmp_path, blocks_per_page=2)
    await engine.dispose()

    chat_mock = _TaggedLLM("CHAT_SUMMARIZE")
    translate_mock = _TaggedLLM("TRANSLATE_SUMMARIZE")
    with make_test_client(
        api_db_path,
        translate_llm_override=translate_mock,
        chat_llm_override=chat_mock,
    ) as client:
        resp = client.post(f"/documents/{seeded.doc_id}/summarize")
    assert resp.status_code == 202, resp.text
    body = resp.json()
    # Summary content should come from the chat mock, not translate.
    assert body["summary"] is not None
    assert "<<CHAT_SUMMARIZE_CHAT>>" in body["summary"]


@pytest.mark.asyncio
async def test_process_upload_job_routes_translate_and_summary_to_distinct_clients(
    api_db_path: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Phase 6e cross-verify R1 §4-1: prove that process_upload_job uses
    app.state.translate_llm for the translate stage and app.state.chat_llm
    for the summarize stage. We patch translate_document + summarize_document
    so the test doesn't depend on extract/ingest mechanics — what we
    actually verify is the dispatch."""
    from datetime import UTC
    from datetime import datetime as _dt
    from types import SimpleNamespace

    from ht_lens.db.models import Job
    from ht_lens.jobs import pipeline as jobs_pipeline

    translate_mock = _TaggedLLM("TR_PIPELINE")
    chat_mock = _TaggedLLM("CHAT_PIPELINE")

    seen: dict[str, object] = {}

    async def fake_translate_document(doc_id, session, llm, *, on_progress=None):
        seen["translate_llm"] = llm
        from ht_lens.translate.pipeline import TranslateStats

        return TranslateStats(document_id=doc_id, translated=1)

    async def fake_summarize_document(doc_id, session, llm):
        seen["summary_llm"] = llm
        return "<<PHASE6E_SUMMARY>>"

    async def fake_to_thread(func, *args, **kwargs):
        # Skip extract_pdf — just no-op to let the pipeline proceed.
        return None

    async def fake_ingest_extract_dir(
        extract_dir, session, *, src, tgt, overwrite, display_filename_override
    ):
        # Insert a Document row inline so summarize has something to query.
        from ht_lens.db.models import Document
        from ht_lens.ingest.pipeline import IngestStats

        doc = Document(
            filename=display_filename_override or "phase6e_fake.pdf",
            src_lang="en",
            tgt_lang="ko",
            status="ready_for_translation",
            src_pdf_sha256="7" * 64,
            created_at=_dt.now(UTC),
        )
        session.add(doc)
        await session.flush()
        return IngestStats(document_id=doc.id, pages=1, blocks=1)

    monkeypatch.setattr(jobs_pipeline, "translate_document", fake_translate_document)
    monkeypatch.setattr(jobs_pipeline, "summarize_document", fake_summarize_document)
    monkeypatch.setattr(jobs_pipeline, "ingest_extract_dir", fake_ingest_extract_dir)
    monkeypatch.setattr(jobs_pipeline.asyncio, "to_thread", fake_to_thread)

    # Set up app.state with the fake clients + a real session factory.
    engine = make_engine(api_db_path)
    factory = make_session_factory(engine)

    # Pre-create the upload file path (process_upload_job checks it exists).
    upload_file = tmp_path / "phase6e_fake.pdf"
    upload_file.write_bytes(b"%PDF-1.4\n")

    # Seed a pending job pointing at the fake file.
    async with factory() as session:
        job = Job(
            type="process_upload",
            status="pending",
            upload_path=str(upload_file),
            upload_filename="phase6e_fake.pdf",
            upload_sha256="7" * 64,
            progress_pct=0,
            created_at=_dt.utcnow(),
        )
        session.add(job)
        await session.commit()
        job_id = job.id

    # Mock FastAPI app with the state attrs process_upload_job reads.
    app = SimpleNamespace(
        state=SimpleNamespace(
            session_factory=factory,
            translate_llm=translate_mock,
            chat_llm=chat_mock,
        )
    )

    await jobs_pipeline.process_upload_job(job_id, app)
    await engine.dispose()

    assert seen.get("translate_llm") is translate_mock, (
        f"translate stage must use translate_llm; got {type(seen.get('translate_llm'))}"
    )
    assert seen.get("summary_llm") is chat_mock, (
        f"summary stage must use chat_llm; got {type(seen.get('summary_llm'))}"
    )

    # Confirm the job reached "done" status with the chat-mock summary.
    async with make_engine(api_db_path).begin() as conn:
        from sqlalchemy import text

        row = (
            await conn.execute(
                text("SELECT status, error_message FROM jobs WHERE id = :id"),
                {"id": job_id},
            )
        ).fetchone()
    assert row is not None
    assert row[0] == "done", f"expected job done, got status={row[0]!r}, err={row[1]!r}"
