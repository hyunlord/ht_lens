"""Phase 6d — POST /documents/{id}/summarize."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from ht_lens.db.session import make_engine, make_session_factory

from ._api_helpers import make_test_client, seed_minimal_document


class _CapturingMockLLM:
    """Deterministic mock that records each chat call so tests can assert
    the summarize prompt was actually built."""

    model_name = "mock-summarize"

    def __init__(self, reply: str = "MOCK 한국어 요약 응답입니다.") -> None:
        self.reply = reply
        self.prompts: list[str] = []

    async def translate(self, text: str, src: str, tgt: str, *, context=None) -> str:
        return f"[KO] {text}"

    async def chat(self, messages, *, system=None) -> str:
        self.prompts.append(messages[-1]["content"])
        return self.reply

    async def health_check(self) -> bool:
        return True


@pytest.mark.asyncio
async def test_summarize_404_for_unknown_doc(api_db_path: Path) -> None:
    with make_test_client(api_db_path) as client:
        resp = client.post("/documents/9999/summarize")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_summarize_image_only_document_returns_422(api_db_path: Path, tmp_path: Path) -> None:
    """Debate §5 missing test: image-only / not-yet-translated docs must
    surface a clear 422 instead of an opaque 500."""
    engine = make_engine(api_db_path)
    factory = make_session_factory(engine)
    async with factory() as session:
        seeded = await seed_minimal_document(
            session,
            tmp_dir=tmp_path,
            blocks_per_page=2,
            block_types=("image", "image"),
            with_translations=False,
        )
    await engine.dispose()

    llm = _CapturingMockLLM()
    with make_test_client(api_db_path, llm_override=llm) as client:
        resp = client.post(f"/documents/{seeded.doc_id}/summarize")
    assert resp.status_code == 422
    assert "번역된 텍스트가 없" in resp.json()["detail"]
    assert llm.prompts == []  # never called


@pytest.mark.asyncio
async def test_summarize_writes_summary_and_summarized_at(
    api_db_path: Path, tmp_path: Path
) -> None:
    engine = make_engine(api_db_path)
    factory = make_session_factory(engine)
    async with factory() as session:
        seeded = await seed_minimal_document(session, tmp_dir=tmp_path, blocks_per_page=3)
    await engine.dispose()

    llm = _CapturingMockLLM(reply="이 문서는 테스트용 요약입니다." * 5)
    with make_test_client(api_db_path, llm_override=llm) as client:
        resp = client.post(f"/documents/{seeded.doc_id}/summarize")
    assert resp.status_code == 202
    body = resp.json()
    assert body["summary"] is not None
    assert "테스트용 요약" in body["summary"]
    assert body["summarized_at"] is not None
    # The mock saw exactly one chat call with the Korean prompt header.
    assert len(llm.prompts) == 1
    assert "한국어로 번역된 문서" in llm.prompts[0]


@pytest.mark.llm
@pytest.mark.asyncio
async def test_summarize_live_returns_korean(
    api_db_path: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Real sglang call. Skipped unless LLM_BASE_URL / LLM_MODEL are set."""
    if not os.environ.get("LLM_BASE_URL") or not os.environ.get("LLM_MODEL"):
        pytest.skip("LLM_BASE_URL / LLM_MODEL not set")

    engine = make_engine(api_db_path)
    factory = make_session_factory(engine)
    async with factory() as session:
        seeded = await seed_minimal_document(session, tmp_dir=tmp_path, blocks_per_page=3)
        # Seed translated text long enough for the LLM to summarise.
        from sqlalchemy import update

        from ht_lens.db.models import Block, Translation

        for i, block_id in enumerate(seeded.block_ids):
            await session.execute(
                update(Block)
                .where(Block.id == block_id)
                .values(
                    original_text=(
                        "Open-Sora 2.0 is an open-source video diffusion "
                        "model trained on 8 GPUs for $200K. " * 3
                    )
                )
            )
            await session.execute(
                update(Translation)
                .where(Translation.block_id == block_id)
                .values(
                    translated_text=(
                        f"단락 {i + 1}: 오픈소스 비디오 생성 모델 Open-Sora 2.0"
                        f"은 8 GPU로 20만 달러에 학습된 확산 모델입니다. " * 3
                    )
                )
            )
        await session.commit()
    await engine.dispose()

    monkeypatch.setenv("LLM_PROVIDER", "openai_compat")
    monkeypatch.setenv("HT_LENS_SKIP_LLM_CHECK", "1")

    with make_test_client(api_db_path) as client:
        resp = client.post(f"/documents/{seeded.doc_id}/summarize")
    assert resp.status_code == 202, resp.text
    body = resp.json()
    summary = body["summary"]
    assert summary
    # At least one Hangul character.
    assert any("가" <= ch <= "힣" for ch in summary), summary
