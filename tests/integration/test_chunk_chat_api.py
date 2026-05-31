"""Phase 8d-2a/8d-2b — /v2/threads + /v2/pins API tests (mock chat LLM)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from ht_lens.db.models import Chunk, ChunkEmbedding, ChunkMessage, ChunkThread, Document, Thread
from ht_lens.db.session import make_engine, make_session_factory
from ht_lens.embedding.service import text_source_hash
from ht_lens.embedding.store import vector_to_bytes
from ht_lens.llm.client import Message as LLMMessage

from ._api_helpers import make_test_client


class FakeEmbed:
    """Phase 8d-2b — deterministic embedding client for cross-doc RAG tests."""

    dim = 2

    def __init__(self, vec: tuple[float, float] = (1.0, 0.0), fail: bool = False) -> None:
        self._vec = np.asarray(vec, dtype=np.float32)
        self.fail = fail

    def encode(self, texts: list[str]) -> np.ndarray:
        if self.fail:
            raise RuntimeError("embedding backend down")
        return np.tile(self._vec, (len(texts), 1))

    async def health_check(self) -> bool:  # pragma: no cover
        return True


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


@pytest.mark.asyncio
async def test_anchor_type_check_rejects_invalid(api_db_path: Path) -> None:
    """verify-cross R2: ck_chunk_threads_anchor_type rejects an unknown
    anchor_type on a DIRECT insert — defense beyond the API Literal."""
    doc_id, ids = await _seed(api_db_path)
    engine = make_engine(api_db_path)
    factory = make_session_factory(engine)
    try:
        async with factory() as s:
            s.add(
                ChunkThread(
                    doc_id=doc_id,
                    anchor_type="bogus",  # not in ('chunk','section')
                    chunk_id=ids[0],
                    title="x",
                    created_at=datetime.now(UTC),
                )
            )
            with pytest.raises(IntegrityError):
                await s.commit()
    finally:
        await engine.dispose()


async def _seed_two_docs_with_emb(db_path: Path) -> tuple[int, int, int]:
    """doc A (heading + anchor text chunk, emb [1,0]) + doc B (related text
    chunk, emb [1,0]). Returns (docA_id, anchor_chunk_id, docB_chunk_id)."""
    anchor_text = "exponential family factor analysis derivation and variational inference"
    related_text = "another book's section on exponential family latent variable models"
    engine = make_engine(db_path)
    factory = make_session_factory(engine)
    try:
        async with factory() as s:
            docs = [
                Document(
                    filename=f"{name}.pdf",
                    src_lang="en",
                    tgt_lang="ko",
                    status="translated",
                    created_at=datetime.now(UTC),
                    extractor="mineru",
                )
                for name in ("A", "B")
            ]
            s.add_all(docs)
            await s.flush()
            head = Chunk(
                doc_id=docs[0].id,
                page_idx=0,
                order_idx=0,
                type="heading",
                bbox_json="[]",
                content="1 Sec",
            )
            anchor = Chunk(
                doc_id=docs[0].id,
                page_idx=0,
                order_idx=1,
                type="text",
                bbox_json="[]",
                content=anchor_text,
            )
            b_chunk = Chunk(
                doc_id=docs[1].id,
                page_idx=2,
                order_idx=0,
                type="text",
                bbox_json="[]",
                content=related_text,
            )
            s.add_all([head, anchor, b_chunk])
            await s.flush()
            for ch, content in ((anchor, anchor_text), (b_chunk, related_text)):
                s.add(
                    ChunkEmbedding(
                        chunk_id=ch.id,
                        model="fake",
                        dim=2,
                        vector=vector_to_bytes(np.asarray([1.0, 0.0], dtype=np.float32)),
                        source_hash=text_source_hash(content),
                        updated_at=datetime.now(UTC),
                    )
                )
            await s.commit()
            return docs[0].id, anchor.id, b_chunk.id
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_post_message_returns_related_chunks(api_db_path: Path) -> None:
    """challenge R3: cross-doc refs surface in the API RESPONSE (not only the
    system prompt). doc A anchor → related chunk from doc B."""
    doc_a, anchor_id, b_chunk = await _seed_two_docs_with_emb(api_db_path)
    with make_test_client(
        api_db_path, chat_llm_override=RecordingLLM(), embedding_override=FakeEmbed()
    ) as client:
        tid = client.post(
            "/v2/threads", json={"doc_id": doc_a, "anchor_type": "chunk", "chunk_id": anchor_id}
        ).json()["id"]
        r = client.post(f"/v2/threads/{tid}/messages", json={"content": "이게 뭐야"})
    assert r.status_code == 202
    refs = r.json()["related_chunks"]
    assert [ref["chunk_id"] for ref in refs] == [b_chunk]  # only the OTHER doc's chunk
    assert refs[0]["doc_filename"] == "B.pdf" and refs[0]["page_idx"] == 2


@pytest.mark.asyncio
async def test_chat_graceful_on_embedding_failure(api_db_path: Path) -> None:
    """challenge R5: an embedding/encode failure must NOT 500 or block chat —
    refs are best-effort (empty), the message still persists. Anchor has no
    stored embedding → get_or_encode encodes → FakeEmbed(fail) raises → skip."""
    doc_id, ids = await _seed(api_db_path)  # no embeddings seeded
    with make_test_client(
        api_db_path, chat_llm_override=RecordingLLM(), embedding_override=FakeEmbed(fail=True)
    ) as client:
        tid = client.post(
            "/v2/threads", json={"doc_id": doc_id, "anchor_type": "chunk", "chunk_id": ids[1]}
        ).json()["id"]
        r = client.post(f"/v2/threads/{tid}/messages", json={"content": "q"})
        msgs = client.get(f"/v2/threads/{tid}/messages").json()
    assert r.status_code == 202  # chat succeeded despite embedding failure
    assert r.json()["related_chunks"] == []  # best-effort skip
    assert [m["role"] for m in msgs] == ["user", "assistant"]  # message persisted


@pytest.mark.asyncio
async def test_section_chat_graceful_on_embedding_failure(api_db_path: Path) -> None:
    """cross-verify R1 regression fix: SECTION chat must NOT 500 when the
    embedding backend fails — it falls back to deterministic context. (8d-2a
    section chat worked without embeddings; this must too.)"""
    doc_id, ids = await _seed(api_db_path)  # heading/text/heading, no embeddings
    with make_test_client(
        api_db_path, chat_llm_override=RecordingLLM(), embedding_override=FakeEmbed(fail=True)
    ) as client:
        tid = client.post(
            "/v2/threads", json={"doc_id": doc_id, "anchor_type": "section", "chunk_id": ids[0]}
        ).json()["id"]
        r = client.post(f"/v2/threads/{tid}/messages", json={"content": "이 절 설명"})
        msgs = client.get(f"/v2/threads/{tid}/messages").json()
    assert r.status_code == 202  # graceful degraded fallback, not a 500
    assert [m["role"] for m in msgs] == ["user", "assistant"]


@pytest.mark.asyncio
async def test_figure_anchor_post_uses_figure_context(api_db_path: Path) -> None:
    """cross-verify R1: an image-anchored thread routes through
    build_figure_context in the API (not just the builder unit) — the
    caption + neighbours reach the LLM system prompt (challenge R4)."""
    engine = make_engine(api_db_path)
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
            rows = [
                Chunk(
                    doc_id=doc.id,
                    page_idx=0,
                    order_idx=0,
                    type="text",
                    bbox_json="[]",
                    content="before the figure",
                ),
                Chunk(
                    doc_id=doc.id,
                    page_idx=0,
                    order_idx=1,
                    type="image",
                    bbox_json="[]",
                    content="",
                    caption="Figure 1: a histogram",
                ),
                Chunk(
                    doc_id=doc.id,
                    page_idx=0,
                    order_idx=2,
                    type="text",
                    bbox_json="[]",
                    content="after the figure",
                ),
            ]
            s.add_all(rows)
            await s.flush()
            doc_id, img_id = doc.id, rows[1].id
            await s.commit()
    finally:
        await engine.dispose()
    llm = RecordingLLM()
    with make_test_client(api_db_path, chat_llm_override=llm) as client:
        tid = client.post(
            "/v2/threads", json={"doc_id": doc_id, "anchor_type": "chunk", "chunk_id": img_id}
        ).json()["id"]
        r = client.post(f"/v2/threads/{tid}/messages", json={"content": "이 그림 설명"})
    assert r.status_code == 202
    system = llm.calls[-1][1] or ""
    assert "Figure 1: a histogram" in system  # caption reached the LLM
    assert "before the figure" in system and "after the figure" in system  # ±neighbours (R4)
    assert "[그림]" in system  # figure context marker
