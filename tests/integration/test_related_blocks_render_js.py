"""Phase 7a R2 Planner-directed fix — jsdom behavioral tests for the
cross-doc references UI surface.

R2 verify-cross §2 flagged that the RE-CODE state.js cache (
``relatedBlocksByMessageId`` + ``setRelatedBlocksForMessage`` /
``getRelatedBlocksForMessage``) and the message.js rendering branch had
no automated coverage despite the existing Node-based test harness.
This module locks both:

- the pure-JS cache contract (back-and-forth between
  ``setRelatedBlocksForMessage`` and ``getRelatedBlocksForMessage``,
  including the no-op when ``messageId`` is falsy);
- the renderer fall-back contract under jsdom — assistant messages
  without an inline ``related_blocks`` field still surface the
  "다른 책의 관련 부분" section by reading the runtime cache, and
  the resulting DOM exposes the expected anchor/score/preview shape.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
STATE_JS = REPO / "src" / "ht_lens" / "api" / "static" / "js" / "state.js"
MESSAGE_JS = REPO / "src" / "ht_lens" / "api" / "static" / "js" / "components" / "message.js"


def _find_jsdom() -> str | None:
    candidates = [
        Path.home() / "github" / "WorldFork" / "frontend" / "node_modules" / "jsdom",
        Path.home() / "node_modules" / "jsdom",
        Path("/usr/lib/node_modules/jsdom"),
        Path("/usr/local/lib/node_modules/jsdom"),
    ]
    for p in candidates:
        api = p / "lib" / "api.js"
        if api.is_file():
            return api.as_uri()
    return None


def _node_available() -> bool:
    return shutil.which("node") is not None


pytestmark = pytest.mark.skipif(not _node_available(), reason="node binary not on PATH")


@pytest.fixture
def jsdom_url() -> str:
    url = _find_jsdom()
    if url is None:
        pytest.skip("no jsdom install located on host")
    return url


def _run_with_jsdom(script: str, jsdom_url: str) -> dict:
    # ``jsdom`` provides ``window``, ``document``, ``localStorage`` etc.
    # state.js touches localStorage at import time so we need a real one.
    full = f"""
    import {{ JSDOM }} from "{jsdom_url}";
    const w = new JSDOM("", {{ url: "http://localhost/" }}).window;
    globalThis.window = w;
    globalThis.document = w.document;
    globalThis.localStorage = w.localStorage;
    globalThis.Node = w.Node;
    globalThis.HTMLElement = w.HTMLElement;
    {script}
    """
    proc = subprocess.run(
        ["node", "--input-type=module", "-e", full],
        capture_output=True,
        text=True,
        cwd=str(REPO),
        check=False,
    )
    if proc.returncode != 0:
        pytest.fail(
            f"node failed: rc={proc.returncode}\nstdout={proc.stdout}\nstderr={proc.stderr}"
        )
    return json.loads(proc.stdout.strip().splitlines()[-1])


def test_set_and_get_related_blocks_round_trip(jsdom_url: str) -> None:
    """``setRelatedBlocksForMessage`` writes; ``getRelatedBlocksForMessage``
    reads. This locks the state.js cache that the renderer falls back to
    when ``GET /threads/{id}`` rebuilds the message list from ORM rows
    (which drop the response-only ``related_blocks`` field)."""
    refs = [
        {
            "block_id": 42,
            "doc_id": 7,
            "doc_filename": "other.pdf",
            "page_num": 3,
            "block_local_id": "b007",
            "score": 0.91,
            "original_preview": "preview text",
            "translated_preview": "한국어 미리보기",
        },
        {
            "block_id": 51,
            "doc_id": 9,
            "doc_filename": "third.pdf",
            "page_num": 1,
            "block_local_id": "b001",
            "score": 0.83,
            "original_preview": "second preview",
            "translated_preview": "두 번째 미리보기",
        },
    ]
    refs_json = json.dumps(refs)
    script = f"""
    const mod = await import("{STATE_JS.as_uri()}");
    const {{ setRelatedBlocksForMessage, getRelatedBlocksForMessage }} = mod;
    const refs = {refs_json};
    setRelatedBlocksForMessage(123, refs);
    const read = getRelatedBlocksForMessage(123);
    // Reading a different message id must yield an empty list, not the
    // first message's refs (no cross-contamination across messages).
    const other = getRelatedBlocksForMessage(999);
    console.log(JSON.stringify({{
        readLen: read.length,
        readIds: read.map(r => r.block_id),
        otherLen: other.length,
    }}));
    """
    out = _run_with_jsdom(script, jsdom_url)
    assert out["readLen"] == 2
    assert out["readIds"] == [42, 51]
    assert out["otherLen"] == 0, "cache must be scoped per messageId"


def test_set_related_blocks_ignores_falsy_message_id(jsdom_url: str) -> None:
    """``setRelatedBlocksForMessage(undefined, ...)`` must be a no-op so a
    failed POST response with no ``id`` does not pollute the cache under
    a falsy key. R2: this branch was untested in the RE-CODE."""
    script = f"""
    const mod = await import("{STATE_JS.as_uri()}");
    const {{ setRelatedBlocksForMessage, getRelatedBlocksForMessage, state }} = mod;
    // No messageId -> nothing stored.
    setRelatedBlocksForMessage(undefined, [{{block_id: 1}}]);
    setRelatedBlocksForMessage(null, [{{block_id: 2}}]);
    setRelatedBlocksForMessage(0, [{{block_id: 3}}]);
    const keys = Object.keys(state.relatedBlocksByMessageId);
    console.log(JSON.stringify({{
        keys,
        underZero: getRelatedBlocksForMessage(0).length,
    }}));
    """
    out = _run_with_jsdom(script, jsdom_url)
    assert out["keys"] == [], f"falsy messageId must not create a cache entry; got {out['keys']!r}"
    assert out["underZero"] == 0


def test_render_message_falls_back_to_cache_for_related_blocks(jsdom_url: str) -> None:
    """When ``msg.related_blocks`` is absent (the rehydrated-from-ORM
    case), ``renderMessage`` must read from the runtime cache and still
    emit the cross-doc references section into the DOM.

    This is the R2 missed-coverage path. Locking it here means a future
    refactor that breaks the fall-back will fail this test before users
    notice an empty "다른 책의 관련 부분" section after panel reload.
    """
    refs = [
        {
            "block_id": 42,
            "doc_id": 7,
            "doc_filename": "other.pdf",
            "page_num": 3,
            "block_local_id": "b007",
            "score": 0.91,
            "original_preview": "Cross-doc preview text that exercises the renderer.",
            "translated_preview": "교차 문서 미리보기 텍스트",
        }
    ]
    refs_json = json.dumps(refs)
    script = f"""
    const stateMod = await import("{STATE_JS.as_uri()}");
    const msgMod = await import("{MESSAGE_JS.as_uri()}");
    stateMod.setRelatedBlocksForMessage(7, {refs_json});

    const container = document.createElement("div");
    // ORM-rehydrated message has no related_blocks field.
    const msg = {{ id: 7, role: "assistant", content: "AI 응답 본문", model: "mock" }};
    msgMod.renderMessage(container, msg);

    const section = container.querySelector(".related-blocks");
    const items = container.querySelectorAll(".related-block");
    const title = section ? section.querySelector(".related-blocks-title") : null;
    const score = section ? section.querySelector(".related-score") : null;
    const link = section ? section.querySelector("a.related-open") : null;

    console.log(JSON.stringify({{
        sectionPresent: section !== null,
        itemCount: items.length,
        titleText: title ? title.textContent : null,
        scoreText: score ? score.textContent : null,
        linkHref: link ? link.getAttribute("href") : null,
        linkText: link ? link.textContent : null,
    }}));
    """
    out = _run_with_jsdom(script, jsdom_url)
    assert out["sectionPresent"] is True, "fall-back rendering must emit .related-blocks"
    assert out["itemCount"] == 1
    assert out["titleText"] == "다른 책의 관련 부분 (1)"
    assert out["scoreText"] == "score 0.91"
    # R1 deep-link fix: ``?doc=&page=&block=`` query params, not the
    # earlier broken ``#block-N`` fragment.
    assert out["linkHref"] == "/static/viewer.html?doc=7&page=3&block=42"
    assert out["linkText"] == "→ 열기"


def test_render_message_prefers_inline_related_blocks_over_cache(jsdom_url: str) -> None:
    """When the response carries ``related_blocks`` inline, the renderer
    uses it directly and ignores the cache. This locks the priority
    order so a stale cache cannot overwrite fresh server data."""
    cached = [
        {
            "block_id": 100,
            "doc_id": 1,
            "doc_filename": "stale.pdf",
            "page_num": 1,
            "block_local_id": "b001",
            "score": 0.10,
        }
    ]
    inline = [
        {
            "block_id": 200,
            "doc_id": 2,
            "doc_filename": "fresh.pdf",
            "page_num": 5,
            "block_local_id": "b010",
            "score": 0.99,
        }
    ]
    cached_json = json.dumps(cached)
    inline_json = json.dumps(inline)
    script = f"""
    const stateMod = await import("{STATE_JS.as_uri()}");
    const msgMod = await import("{MESSAGE_JS.as_uri()}");
    stateMod.setRelatedBlocksForMessage(9, {cached_json});
    const container = document.createElement("div");
    const msg = {{
        id: 9,
        role: "assistant",
        content: "X",
        related_blocks: {inline_json},
    }};
    msgMod.renderMessage(container, msg);

    const link = container.querySelector("a.related-open");
    const docName = container.querySelector(".related-doc");
    console.log(JSON.stringify({{
        href: link ? link.getAttribute("href") : null,
        docText: docName ? docName.textContent : null,
    }}));
    """
    out = _run_with_jsdom(script, jsdom_url)
    # Inline (fresh) data wins over cached (stale) data.
    assert out["href"] == "/static/viewer.html?doc=2&page=5&block=200"
    assert out["docText"] == "fresh.pdf"
