"""Phase 8d-2a — /v2/threads + /v2/pins API tests (mock chat LLM)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from ht_lens.db.models import Chunk, ChunkMessage, ChunkThread, Document, Thread
from ht_lens.db.session import make_engine, make_session_factory
from ht_lens.llm.client import Message as LLMMessage

from ._api_helpers import make_test_client


class RecordingLLM:
    model_name = "recorder"

    def __init__(self, reply: str = "답변입니다") -> None:
        self.calls: list[tuple[list[LLMMessage], str | None]] = []
        self.reply = reply

    async def chat(self, messages: list[LLMMessage], *, system: str | None = None) -> str:
        self.calls.append((list(messages), system))
        return self.reply

    async def health_check(self) -> bool:  # pragma: no cover
        return True


class FailingLLM(RecordingLLM):
    async def chat(self, messages: list[LLMMessage], *, system: str | None = None) -> str:
        from ht_lens.llm.errors import LLMTransientError

        raise LLMTransientError("boom")


async def _seed(db_path: Path) -> tuple[int, list[int]]:
    """One mineru doc: heading 28.4, body, heading 28.5. Returns (doc_id, chunk_ids)."""
    engine = make_engine(db_path)
    factory = make_session_factory(engine)
    try:
        async with factory() as s:
            doc = Document(
                filename="m.pdf",
                src_lang="en",
                tgt_lang="ko",
                status="translated",
                created_at=datetime.now(UTC),
                extractor="mineru",
            )
            s.add(doc)
            await s.flush()
            ids = []
            for i, (t, body) in enumerate(
                [("heading", "28.4 Sec"), ("text", "body"), ("heading", "28.5 Next")]
            ):
                ch = Chunk(
                    doc_id=doc.id,
                    page_idx=0,
                    order_idx=i,
                    type=t,
                    bbox_json="[]",
                    content=body,
                )
                s.add(ch)
                await s.flush()
                ids.append(ch.id)
            await s.commit()
            return doc.id, ids
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_create_chunk_and_section_threads(api_db_path: Path) -> None:
    doc_id, ids = await _seed(api_db_path)
    with make_test_client(api_db_path, chat_llm_override=RecordingLLM()) as client:
        r1 = client.post(
            "/v2/threads",
            json={"doc_id": doc_id, "anchor_type": "chunk", "chunk_id": ids[1]},
        )
        r2 = client.post(
            "/v2/threads",
            json={"doc_id": doc_id, "anchor_type": "section", "chunk_id": ids[0]},
        )
    assert r1.status_code == 201 and r1.json()["anchor_type"] == "chunk"
    assert r2.status_code == 201 and r2.json()["chunk_id"] == ids[0]


@pytest.mark.asyncio
async def test_create_rejects_chunk_doc_mismatch(api_db_path: Path) -> None:
    doc_id, ids = await _seed(api_db_path)
    with make_test_client(api_db_path, chat_llm_override=RecordingLLM()) as client:
        r = client.post(
            "/v2/threads",
            json={"doc_id": doc_id + 999, "anchor_type": "chunk", "chunk_id": ids[1]},
        )
    assert r.status_code == 422  # chunk does not belong to doc_id


@pytest.mark.asyncio
async def test_section_anchor_must_be_heading(api_db_path: Path) -> None:
    doc_id, ids = await _seed(api_db_path)
    with make_test_client(api_db_path, chat_llm_override=RecordingLLM()) as client:
        r = client.post(
            "/v2/threads",
            json={"doc_id": doc_id, "anchor_type": "section", "chunk_id": ids[1]},  # ids[1]=text
        )
    assert r.status_code == 422  # section anchor must reference a heading


@pytest.mark.asyncio
async def test_post_message_uses_section_context_and_persists(api_db_path: Path) -> None:
    doc_id, ids = await _seed(api_db_path)
    llm = RecordingLLM()
    with make_test_client(api_db_path, chat_llm_override=llm) as client:
        tid = client.post(
            "/v2/threads",
            json={"doc_id": doc_id, "anchor_type": "section", "chunk_id": ids[0]},
        ).json()["id"]
        r = client.post(f"/v2/threads/{tid}/messages", json={"content": "이 절 설명해줘"})
        msgs = client.get(f"/v2/threads/{tid}/messages").json()
    assert r.status_code == 202 and r.json()["role"] == "assistant"
    assert "28.4 Sec" in (llm.calls[-1][1] or "")  # section context reached the LLM
    assert [m["role"] for m in msgs] == ["user", "assistant"]  # both persisted


@pytest.mark.asyncio
async def test_message_llm_failure_writes_no_messages(api_db_path: Path) -> None:
    doc_id, ids = await _seed(api_db_path)
    with make_test_client(api_db_path, chat_llm_override=FailingLLM()) as client:
        tid = client.post(
            "/v2/threads", json={"doc_id": doc_id, "anchor_type": "chunk", "chunk_id": ids[1]}
        ).json()["id"]
        r = client.post(f"/v2/threads/{tid}/messages", json={"content": "q"})
        msgs = client.get(f"/v2/threads/{tid}/messages").json()
    assert r.status_code == 502  # LLM transient → 502
    assert msgs == []  # neither user nor assistant row persisted (challenge R8)


@pytest.mark.asyncio
async def test_post_to_deleted_thread_404(api_db_path: Path) -> None:
    doc_id, ids = await _seed(api_db_path)
    with make_test_client(api_db_path, chat_llm_override=RecordingLLM()) as client:
        tid = client.post(
            "/v2/threads", json={"doc_id": doc_id, "anchor_type": "chunk", "chunk_id": ids[1]}
        ).json()["id"]
        assert client.delete(f"/v2/threads/{tid}").status_code == 204
        r = client.post(f"/v2/threads/{tid}/messages", json={"content": "q"})
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_fk_prevents_orphan_messages(api_db_path: Path) -> None:
    """The hard no-orphan guarantee behind R8: a message FK to a missing
    thread is rejected (true concurrent-delete is impractical to simulate
    under SQLite locking; the FK is the backstop)."""
    await _seed(api_db_path)
    engine = make_engine(api_db_path)
    factory = make_session_factory(engine)
    try:
        async with factory() as s:
            s.add(
                ChunkMessage(
                    thread_id=999999,
                    role="user",
                    content="x",
                    model=None,
                    created_at=datetime.now(UTC),
                )
            )
            with pytest.raises(IntegrityError):
                await s.commit()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_list_threads_with_counts(api_db_path: Path) -> None:
    doc_id, ids = await _seed(api_db_path)
    with make_test_client(api_db_path, chat_llm_override=RecordingLLM()) as client:
        tid = client.post(
            "/v2/threads", json={"doc_id": doc_id, "anchor_type": "chunk", "chunk_id": ids[1]}
        ).json()["id"]
        client.post(f"/v2/threads/{tid}/messages", json={"content": "q"})
        listing = client.get(f"/v2/documents/{doc_id}/threads").json()
    assert len(listing) == 1 and listing[0]["message_count"] == 2


@pytest.mark.asyncio
async def test_pins_create_list_delete(api_db_path: Path) -> None:
    doc_id, ids = await _seed(api_db_path)
    with make_test_client(api_db_path, chat_llm_override=RecordingLLM()) as client:
        pid = client.post("/v2/pins", json={"doc_id": doc_id, "chunk_id": ids[1]}).json()["id"]
        assert len(client.get(f"/v2/documents/{doc_id}/pins").json()) == 1
        assert client.delete(f"/v2/pins/{pid}").status_code == 204
        assert client.get(f"/v2/documents/{doc_id}/pins").json() == []


@pytest.mark.asyncio
async def test_v2_chat_does_not_touch_1x_threads(api_db_path: Path) -> None:
    doc_id, ids = await _seed(api_db_path)
    with make_test_client(api_db_path, chat_llm_override=RecordingLLM()) as client:
        client.post(
            "/v2/threads", json={"doc_id": doc_id, "anchor_type": "chunk", "chunk_id": ids[1]}
        )
    engine = make_engine(api_db_path)
    factory = make_session_factory(engine)
    try:
        async with factory() as s:
            n_1x = (await s.execute(select(func.count(Thread.id)))).scalar_one()
            n_v2 = (await s.execute(select(func.count(ChunkThread.id)))).scalar_one()
    finally:
        await engine.dispose()
    assert n_1x == 0 and n_v2 == 1  # v2 thread created, 1.x threads untouched
