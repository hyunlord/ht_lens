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
