"""Phase 6a — /blocks/{id}/retranslate endpoint tests."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from sqlalchemy import select

from ht_lens.db.models import Block, Translation
from ht_lens.db.session import make_engine, make_session_factory
from ht_lens.llm.errors import LLMPermanentError, LLMTransientError

from ._api_helpers import make_test_client, seed_minimal_document


class _RecordingMockLLM:
    model_name = "mock-retranslate"

    def __init__(self, reply: str = "[KO-NEW] %s") -> None:
        self.calls: list[str] = []
        self.reply = reply

    async def translate(self, text: str, src: str, tgt: str, *, context: str | None = None) -> str:
        self.calls.append(text)
        return self.reply % text if "%s" in self.reply else self.reply

    async def chat(self, messages: list, *, system: str | None = None) -> str:  # pragma: no cover
        return "n/a"

    async def health_check(self) -> bool:
        return True


class _FailingLLM(_RecordingMockLLM):
    def __init__(self, exc: Exception) -> None:
        super().__init__()
        self.exc = exc

    async def translate(self, text: str, src: str, tgt: str, *, context: str | None = None) -> str:
        self.calls.append(text)
        raise self.exc


@pytest.mark.asyncio
async def test_retranslate_404_for_unknown_block(api_db_path: Path) -> None:
    with make_test_client(api_db_path) as client:
        resp = client.post("/blocks/9999/retranslate")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_retranslate_400_for_image_block(api_db_path: Path, tmp_path: Path) -> None:
    engine = make_engine(api_db_path)
    factory = make_session_factory(engine)
    async with factory() as session:
        seeded = await seed_minimal_document(
            session,
            tmp_dir=tmp_path,
            blocks_per_page=2,
            block_types=("text", "image"),
        )
    await engine.dispose()
    # The image block is at index 1.
    image_bid = seeded.block_ids[1]
    with make_test_client(api_db_path) as client:
        resp = client.post(f"/blocks/{image_bid}/retranslate")
    assert resp.status_code == 400
    assert "image" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_retranslate_updates_existing_translation(api_db_path: Path, tmp_path: Path) -> None:
    engine = make_engine(api_db_path)
    factory = make_session_factory(engine)
    async with factory() as session:
        seeded = await seed_minimal_document(session, tmp_dir=tmp_path, blocks_per_page=1)
    await engine.dispose()

    bid = seeded.block_ids[0]
    llm = _RecordingMockLLM(reply="[KO-NEW] manual")

    with make_test_client(api_db_path, llm_override=llm) as client:
        resp = client.post(f"/blocks/{bid}/retranslate")
    assert resp.status_code == 202
    body = resp.json()
    assert body["block_id"] == bid
    assert body["translation"]["translated_text"] == "[KO-NEW] manual"
    assert body["translation"]["model"] == "mock-retranslate"
    assert body["translation"]["status"] == "translated"

    # Confirm the row was updated, not duplicated.
    engine = make_engine(api_db_path)
    factory = make_session_factory(engine)
    async with factory() as session:
        rows = (
            (await session.execute(select(Translation).where(Translation.block_id == bid)))
            .scalars()
            .all()
        )
    await engine.dispose()
    assert len(rows) == 1
    assert rows[0].translated_text == "[KO-NEW] manual"


@pytest.mark.asyncio
async def test_retranslate_inserts_new_row_when_no_existing_translation(
    api_db_path: Path, tmp_path: Path
) -> None:
    engine = make_engine(api_db_path)
    factory = make_session_factory(engine)
    async with factory() as session:
        seeded = await seed_minimal_document(
            session, tmp_dir=tmp_path, blocks_per_page=1, with_translations=False
        )
    await engine.dispose()
    bid = seeded.block_ids[0]

    llm = _RecordingMockLLM(reply="[KO-FRESH]")
    with make_test_client(api_db_path, llm_override=llm) as client:
        resp = client.post(f"/blocks/{bid}/retranslate")
    assert resp.status_code == 202
    assert resp.json()["translation"]["translated_text"] == "[KO-FRESH]"


@pytest.mark.asyncio
async def test_retranslate_transient_error_returns_502_and_preserves_existing(
    api_db_path: Path, tmp_path: Path
) -> None:
    """R-CODE atomicity: a transient LLM failure must leave the existing
    translation row unchanged (no partial write)."""
    engine = make_engine(api_db_path)
    factory = make_session_factory(engine)
    async with factory() as session:
        seeded = await seed_minimal_document(session, tmp_dir=tmp_path, blocks_per_page=1)
    await engine.dispose()
    bid = seeded.block_ids[0]

    # Capture the row contents before the failed call.
    engine = make_engine(api_db_path)
    factory = make_session_factory(engine)
    async with factory() as session:
        before = (
            await session.execute(select(Translation).where(Translation.block_id == bid))
        ).scalar_one()
        before_text = before.translated_text
        before_model = before.model
        before_updated = before.updated_at
    await engine.dispose()

    llm = _FailingLLM(LLMTransientError("upstream timeout"))
    with make_test_client(api_db_path, llm_override=llm) as client:
        resp = client.post(f"/blocks/{bid}/retranslate")
    assert resp.status_code == 502

    engine = make_engine(api_db_path)
    factory = make_session_factory(engine)
    async with factory() as session:
        after = (
            await session.execute(select(Translation).where(Translation.block_id == bid))
        ).scalar_one()
    await engine.dispose()
    assert after.translated_text == before_text
    assert after.model == before_model
    assert after.updated_at == before_updated


@pytest.mark.asyncio
async def test_retranslate_failed_llm_writes_no_partial_row(
    api_db_path: Path, tmp_path: Path
) -> None:
    """Block with NO existing translation + permanent LLM error must not
    create a half-written ``translations`` row (Phase 3 atomicity)."""
    engine = make_engine(api_db_path)
    factory = make_session_factory(engine)
    async with factory() as session:
        seeded = await seed_minimal_document(
            session, tmp_dir=tmp_path, blocks_per_page=1, with_translations=False
        )
    await engine.dispose()
    bid = seeded.block_ids[0]

    llm = _FailingLLM(LLMPermanentError("auth failed"))
    with make_test_client(api_db_path, llm_override=llm) as client:
        resp = client.post(f"/blocks/{bid}/retranslate")
    assert resp.status_code == 502

    engine = make_engine(api_db_path)
    factory = make_session_factory(engine)
    async with factory() as session:
        rows = (await session.execute(select(Translation).where(Translation.block_id == bid))).all()
    await engine.dispose()
    assert rows == []


@pytest.mark.llm
@pytest.mark.asyncio
async def test_retranslate_live_replaces_translation(
    api_db_path: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End-to-end live LLM retranslate. Skipped unless ``-m llm``."""
    if not os.environ.get("LLM_BASE_URL") or not os.environ.get("LLM_MODEL"):
        pytest.skip("LLM_BASE_URL / LLM_MODEL not set")

    engine = make_engine(api_db_path)
    factory = make_session_factory(engine)
    async with factory() as session:
        seeded = await seed_minimal_document(session, tmp_dir=tmp_path, blocks_per_page=1)
        # Use a short English sentence we know qwen3.6 can handle quickly.
        await session.execute(
            Block.__table__.update()
            .where(Block.id == seeded.block_ids[0])
            .values(original_text="Hello world.")
        )
        await session.commit()
    await engine.dispose()
    bid = seeded.block_ids[0]

    monkeypatch.setenv("LLM_PROVIDER", "openai_compat")
    monkeypatch.setenv("HT_LENS_SKIP_LLM_CHECK", "1")

    with make_test_client(api_db_path) as client:
        resp = client.post(f"/blocks/{bid}/retranslate")
    assert resp.status_code == 202
    out = resp.json()["translation"]["translated_text"]
    # We at least expect a non-empty answer with Hangul.
    assert out
    assert any("가" <= ch <= "힣" for ch in out), out
