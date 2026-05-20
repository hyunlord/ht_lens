"""Phase 3 — live LLM end-to-end test.

Hits the real LLM endpoint defined by ``LLM_BASE_URL`` / ``LLM_MODEL`` env
vars. Skipped (and not collected) unless ``-m llm`` is passed.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from ht_lens.db.session import make_engine, make_session_factory

from ._api_helpers import make_test_client, seed_minimal_document


@pytest.mark.llm
@pytest.mark.asyncio
async def test_explain_and_followup_returns_korean_text(
    api_db_path: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    if not os.environ.get("LLM_BASE_URL") or not os.environ.get("LLM_MODEL"):
        pytest.skip("LLM_BASE_URL / LLM_MODEL not set")

    engine = make_engine(api_db_path)
    factory = make_session_factory(engine)
    async with factory() as session:
        seeded = await seed_minimal_document(session, tmp_dir=tmp_path)
    await engine.dispose()

    monkeypatch.setenv("LLM_PROVIDER", "openai_compat")
    # Real LLM client; skip startup health_check because we exercise chat directly.
    monkeypatch.setenv("HT_LENS_SKIP_LLM_CHECK", "1")

    with make_test_client(api_db_path) as client:
        thread = client.post("/threads", json={"block_id": seeded.block_ids[0]}).json()
        explain_resp = client.post(f"/threads/{thread['id']}/explain")
        assert explain_resp.status_code == 202
        assistant1 = explain_resp.json()
        assert assistant1["role"] == "assistant"
        assert len(assistant1["content"].strip()) > 0
        # We requested a Korean explanation in /explain; assert at least one
        # Hangul syllable is present so we know the model honored the language.
        assert any("가" <= ch <= "힣" for ch in assistant1["content"]), (
            "no Hangul characters in /explain response: " + assistant1["content"][:200]
        )

        followup = client.post(
            f"/threads/{thread['id']}/messages",
            json={"content": "한 문장으로 더 짧게 다시 설명해줘."},
        )
        assert followup.status_code == 202
        assistant2 = followup.json()
        assert len(assistant2["content"].strip()) > 0
        # Follow-up should also be in Korean since prior context is Korean
        # and the user asked again in Korean.
        assert any("가" <= ch <= "힣" for ch in assistant2["content"]), (
            "no Hangul characters in /messages response: " + assistant2["content"][:200]
        )

        detail = client.get(f"/threads/{thread['id']}").json()
        assert len(detail["messages"]) == 4
        assert [m["role"] for m in detail["messages"]] == [
            "user",
            "assistant",
            "user",
            "assistant",
        ]
