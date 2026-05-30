"""Phase 8c — reflow.js renderChunk unit tests (jsdom).

Mirrors the Phase 6i jsdom harness: drives the real ``renderChunk`` export
(which calls the vendored KaTeX via applyMath) so the chunk→DOM mapping is
locked in-suite. The full viewer (layout/scroll/compare) is validated by
the Playwright E2E recorded in verify.md (the project has no Playwright
pytest fixture; jsdom covers the pure render logic).
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
REFLOW_JS = REPO / "src" / "ht_lens" / "api" / "static" / "js" / "reflow.js"


def _find_jsdom() -> str | None:
    for p in (
        Path.home() / "github" / "WorldFork" / "frontend" / "node_modules" / "jsdom",
        Path.home() / "node_modules" / "jsdom",
        Path("/usr/lib/node_modules/jsdom"),
        Path("/usr/local/lib/node_modules/jsdom"),
    ):
        if (p / "lib" / "api.js").is_file():
            return (p / "lib" / "api.js").as_uri()
    return None


pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node not on PATH")


@pytest.fixture
def jsdom_url() -> str:
    url = _find_jsdom()
    if url is None:
        pytest.skip("no jsdom install located")
    return url


# A ``mk(over)`` helper in JS spreads a base chunk so each test stays short.
_PRELUDE = """
    import { JSDOM } from "%(jsdom)s";
    const w = new JSDOM("<!doctype html><html><body></body></html>").window;
    globalThis.window = w; globalThis.document = w.document;
    globalThis.HTMLElement = w.HTMLElement; globalThis.Element = w.Element;
    globalThis.Node = w.Node; globalThis.DocumentFragment = w.DocumentFragment;
    const { renderChunk } = await import("%(reflow)s");
    const BASE = {
      id: 1, type: 'text', text_level: null, page_idx: 0,
      original: 'x', translated: null, caption: null,
      caption_translated: null, img_url: null, bbox: null,
    };
    const mk = (over) => renderChunk({ ...BASE, ...over });
"""


def _run(script: str, jsdom_url: str) -> dict:
    full = (_PRELUDE % {"jsdom": jsdom_url, "reflow": REFLOW_JS.as_uri()}) + script
    proc = subprocess.run(
        ["node", "--input-type=module", "-e", full],
        capture_output=True,
        text=True,
        cwd=str(REPO),
        check=False,
    )
    if proc.returncode != 0:
        pytest.fail(f"node rc={proc.returncode}\n{proc.stdout}\n{proc.stderr}")
    return json.loads(proc.stdout.strip().splitlines()[-1])


def test_heading_level_maps_to_h2_h3(jsdom_url: str) -> None:
    script = """
    const h2 = mk({type:'heading', text_level:2, translated:'[KO] A'});
    const h3 = mk({type:'heading', text_level:3, translated:'[KO] B'});
    console.log(JSON.stringify(
      {h2:h2.tagName, h3:h3.tagName, cls:h2.className, txt:h2.textContent}));
    """
    out = _run(script, jsdom_url)
    assert out["h2"] == "H2" and out["h3"] == "H3"
    assert "rf-heading" in out["cls"] and "[KO] A" in out["txt"]


def test_equation_renders_katex(jsdom_url: str) -> None:
    script = r"""
    const el = mk({type:'equation', original:'$$E=mc^2$$', translated:'$$E=mc^2$$'});
    console.log(JSON.stringify({katex: el.querySelector('.katex') !== null}));
    """
    out = _run(script, jsdom_url)
    assert out["katex"] is True, out


def test_text_with_math_renders_and_keeps_korean(jsdom_url: str) -> None:
    script = r"""
    const el = mk({type:'text', translated:'[KO] 잠재 $p(z)$ 변수'});
    console.log(JSON.stringify({
      tag: el.tagName, katex: el.querySelector('.katex')!==null,
      ko: el.textContent.includes('잠재'),
    }));
    """
    out = _run(script, jsdom_url)
    assert out["tag"] == "P" and out["katex"] is True and out["ko"] is True


def test_image_figure_box_caption(jsdom_url: str) -> None:
    script = """
    const el = mk({
      id:5, type:'image', original:'', caption:'Figure 1: cat',
      caption_translated:'[KO] 그림 1: 고양이', img_url:'/v2/chunks/5/image',
    });
    console.log(JSON.stringify({
      tag: el.tagName, hasImg: el.querySelector('img')!==null,
      capKo: (el.querySelector('.fb-cap')||{}).textContent || '',
      capEn: (el.querySelector('.fb-en')||{}).textContent || '',
    }));
    """
    out = _run(script, jsdom_url)
    assert out["tag"] == "FIGURE" and out["hasImg"] is True
    assert out["capKo"] == "[KO] 그림 1: 고양이" and "Figure 1" in out["capEn"]


def test_table_chunk_fallback_no_crash(jsdom_url: str) -> None:
    script = """
    const el = mk({type:'table', original:'| a | b |', translated:'[KO] | a | b |'});
    console.log(JSON.stringify({cls: el.className, hasPre: el.querySelector('pre')!==null}));
    """
    out = _run(script, jsdom_url)
    assert "rf-table" in out["cls"] and out["hasPre"] is True


def test_chunk_carries_page_idx_for_sync(jsdom_url: str) -> None:
    script = """
    const el = mk({id:9, type:'text', page_idx:4, translated:'[KO] x'});
    console.log(JSON.stringify({
      page: el.dataset.pageIdx, chunk: el.dataset.chunkId,
      isChunk: el.classList.contains('chunk'),
    }));
    """
    out = _run(script, jsdom_url)
    assert out["page"] == "4" and out["chunk"] == "9" and out["isChunk"] is True
