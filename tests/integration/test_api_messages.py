"""Phase 3 — /threads/{id}/explain and /messages endpoints (mock LLM)."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select

from ht_lens.db.models import Message
from ht_lens.db.session import make_engine, make_session_factory
from ht_lens.llm.client import Message as LLMMessage
from ht_lens.llm.errors import LLMPermanentError, LLMTransientError

from ._api_helpers import make_test_client, seed_minimal_document


class RecordingMockLLM:
    """Captures every (messages, system) tuple passed to ``chat``."""

    model_name = "recorder"

    def __init__(self, reply: str = "OK") -> None:
        self.calls: list[tuple[list[LLMMessage], str | None]] = []
        self.reply = reply

    async def translate(
        self, text: str, src: str, tgt: str, *, context: str | None = None
    ) -> str:  # pragma: no cover — not used here
        return text

    async def chat(self, messages: list[LLMMessage], *, system: str | None = None) -> str:
        self.calls.append((list(messages), system))
        return self.reply

    async def health_check(self) -> bool:
        return True


class FailingChatLLM(RecordingMockLLM):
    def __init__(self, error: Exception) -> None:
        super().__init__()
        self.error = error

    async def chat(self, messages: list[LLMMessage], *, system: str | None = None) -> str:
        self.calls.append((list(messages), system))
        raise self.error


async def _make_seed_and_thread(api_db_path: Path, tmp_path: Path) -> tuple[int, int]:
    engine = make_engine(api_db_path)
    factory = make_session_factory(engine)
    async with factory() as session:
        seeded = await seed_minimal_document(session, tmp_dir=tmp_path, blocks_per_page=3)
        block_id = seeded.block_ids[1]
    await engine.dispose()

    with make_test_client(api_db_path) as client:
        thread_resp = client.post("/threads", json={"block_id": block_id})
        thread = thread_resp.json()
    return thread["id"], block_id


@pytest.mark.asyncio
async def test_explain_appends_user_and_assistant(api_db_path: Path, tmp_path: Path) -> None:
    thread_id, _ = await _make_seed_and_thread(api_db_path, tmp_path)
    llm = RecordingMockLLM(reply="설명입니다")

    with make_test_client(api_db_path, llm_override=llm) as client:
        resp = client.post(f"/threads/{thread_id}/explain")
    assert resp.status_code == 202
    body = resp.json()
    assert body["role"] == "assistant"
    assert body["content"] == "설명입니다"
    assert body["model"] == "recorder"
    # one chat call, with system=block context
    assert len(llm.calls) == 1
    msgs, system = llm.calls[0]
    assert system is not None and "원문:" in system
    assert msgs[-1]["role"] == "user"
    assert "설명해주세요" in msgs[-1]["content"]


@pytest.mark.asyncio
async def test_explain_is_not_idempotent(api_db_path: Path, tmp_path: Path) -> None:
    thread_id, _ = await _make_seed_and_thread(api_db_path, tmp_path)
    llm = RecordingMockLLM(reply="OK")

    with make_test_client(api_db_path, llm_override=llm) as client:
        client.post(f"/threads/{thread_id}/explain")
        client.post(f"/threads/{thread_id}/explain")
        body = client.get(f"/threads/{thread_id}").json()
    assert len(body["messages"]) == 4  # 2 calls x (user+assistant)
    assert len(llm.calls) == 2


@pytest.mark.asyncio
async def test_messages_passes_history_to_llm(api_db_path: Path, tmp_path: Path) -> None:
    thread_id, _ = await _make_seed_and_thread(api_db_path, tmp_path)
    llm = RecordingMockLLM(reply="응답입니다")

    with make_test_client(api_db_path, llm_override=llm) as client:
        client.post(f"/threads/{thread_id}/explain")  # 2 msgs in DB
        resp = client.post(f"/threads/{thread_id}/messages", json={"content": "더 자세히 알려줘"})
    assert resp.status_code == 202
    # second chat call: history should have prior user+assistant + new user
    msgs, system = llm.calls[1]
    assert system is not None and "원문:" in system
    roles = [m["role"] for m in msgs]
    assert roles == ["user", "assistant", "user"]
    assert msgs[-1]["content"] == "더 자세히 알려줘"


@pytest.mark.asyncio
async def test_messages_first_call_no_prepend_in_user_content(
    api_db_path: Path, tmp_path: Path
) -> None:
    """User row stores raw content; block context only travels via system=."""
    thread_id, _ = await _make_seed_and_thread(api_db_path, tmp_path)
    llm = RecordingMockLLM()

    with make_test_client(api_db_path, llm_override=llm) as client:
        client.post(f"/threads/{thread_id}/messages", json={"content": "안녕"})
        body = client.get(f"/threads/{thread_id}").json()

    user_row = next(m for m in body["messages"] if m["role"] == "user")
    assert user_row["content"] == "안녕"
    # LLM received block context only via system=
    msgs, system = llm.calls[0]
    assert system is not None and "원문:" in system
    assert msgs[-1]["content"] == "안녕"


@pytest.mark.asyncio
async def test_messages_transient_error_returns_502(api_db_path: Path, tmp_path: Path) -> None:
    thread_id, _ = await _make_seed_and_thread(api_db_path, tmp_path)
    llm = FailingChatLLM(LLMTransientError("upstream timeout"))

    with make_test_client(api_db_path, llm_override=llm) as client:
        resp = client.post(f"/threads/{thread_id}/messages", json={"content": "hi"})
    assert resp.status_code == 502
    assert "transient" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_messages_permanent_error_returns_502(api_db_path: Path, tmp_path: Path) -> None:
    thread_id, _ = await _make_seed_and_thread(api_db_path, tmp_path)
    llm = FailingChatLLM(LLMPermanentError("auth failed"))

    with make_test_client(api_db_path, llm_override=llm) as client:
        resp = client.post(f"/threads/{thread_id}/explain")
    assert resp.status_code == 502


@pytest.mark.asyncio
async def test_messages_does_not_persist_partial_user_row_on_llm_failure(
    api_db_path: Path, tmp_path: Path
) -> None:
    """LLM call happens FIRST; on failure no row should be persisted."""
    thread_id, _ = await _make_seed_and_thread(api_db_path, tmp_path)
    llm = FailingChatLLM(LLMTransientError("boom"))

    with make_test_client(api_db_path, llm_override=llm) as client:
        client.post(f"/threads/{thread_id}/messages", json={"content": "hello"})

    engine = make_engine(api_db_path)
    factory = make_session_factory(engine)
    async with factory() as session:
        rows = (
            (await session.execute(select(Message).where(Message.thread_id == thread_id)))
            .scalars()
            .all()
        )
    await engine.dispose()
    assert rows == []


@pytest.mark.asyncio
async def test_explain_retry_still_includes_block_context_after_failed_first_attempt(
    api_db_path: Path, tmp_path: Path
) -> None:
    """A failed first call must not corrupt subsequent calls' system context."""
    thread_id, _ = await _make_seed_and_thread(api_db_path, tmp_path)

    failing = FailingChatLLM(LLMTransientError("first attempt fails"))
    with make_test_client(api_db_path, llm_override=failing) as client:
        client.post(f"/threads/{thread_id}/explain")  # 502

    # second client with succeeding mock
    succeeding = RecordingMockLLM(reply="복구")
    with make_test_client(api_db_path, llm_override=succeeding) as client:
        resp = client.post(f"/threads/{thread_id}/explain")
    assert resp.status_code == 202
    _msgs, system = succeeding.calls[0]
    assert system is not None and "원문:" in system


@pytest.mark.asyncio
async def test_messages_unknown_thread_returns_404(api_db_path: Path) -> None:
    with make_test_client(api_db_path) as client:
        resp = client.post("/threads/9999/messages", json={"content": "x"})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_messages_empty_content_returns_422(api_db_path: Path, tmp_path: Path) -> None:
    thread_id, _ = await _make_seed_and_thread(api_db_path, tmp_path)
    with make_test_client(api_db_path) as client:
        resp = client.post(f"/threads/{thread_id}/messages", json={"content": ""})
    assert resp.status_code == 422
