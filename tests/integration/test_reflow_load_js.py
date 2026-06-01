"""Phase 8d-1 — reflow.js load() integration test (jsdom, fetch-stubbed).

verify-cross R1 asked for an end-to-end test of the real load() flow against
the LIVE API contract. This loads the actual reflow.html, stubs ``fetch`` with
a ``/v2/reflow``-shaped response that (like ReflowChunk) has **no order_idx**,
imports reflow.js so auto-init runs, and asserts the whole pipeline:
build sectionNums → render+enrich chunks → heading NOT self-linked → TOC
built → toggle works.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
REFLOW_HTML = REPO / "src" / "ht_lens" / "api" / "static" / "reflow.html"


def _find_jsdom() -> str | None:
    for p in (
        Path(__file__).resolve().parents[2] / "node_modules" / "jsdom",  # repo-local (CI npm ci)
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


# A realistic /v2/reflow response: NO order_idx (matches ReflowChunk). Chunk 1
# is a heading whose own number (28.4) must NOT become a self-ref; chunk 2 is
# prose citing 28.4 + [BJ05] + equation 28.116 (only 28.4 is a real heading).
_LOAD_SCRIPT = """
    import { JSDOM } from "%(jsdom)s";
    import { readFileSync } from "node:fs";
    const html = readFileSync("%(html)s", "utf-8");
    const dom = new JSDOM(html, { url: "http://localhost/static/reflow.html?doc=1" });
    const w = dom.window;
    w.HTMLElement.prototype.scrollIntoView = function () {};
    globalThis.window = w; globalThis.document = w.document;
    globalThis.HTMLElement = w.HTMLElement; globalThis.Element = w.Element;
    globalThis.Node = w.Node; globalThis.NodeFilter = w.NodeFilter;
    globalThis.DocumentFragment = w.DocumentFragment;
    globalThis.CustomEvent = w.CustomEvent; globalThis.MouseEvent = w.MouseEvent;
    globalThis.location = w.location;
    const RESPONSE = {
      filename: 'book2_ch28.pdf', extractor: 'mineru',
      chunks: [
        { id: 1, type: 'heading', text_level: 2, page_idx: 0,
          original: '28.4 LFMs with non-Gaussian priors',
          translated: '28.4 비가우시안 사전 분포를 가진 잠재 함수 모델',
          caption: null, caption_translated: null, img_url: null, bbox: null },
        { id: 2, type: 'text', text_level: null, page_idx: 0,
          original: 'See 28.4 and [BJ05]; equation 28.116 holds.',
          translated: '[KO] 28.4 절과 [BJ05] 참고; 식 28.116 성립.',
          caption: null, caption_translated: null, img_url: null, bbox: null },
        { id: 3, type: 'heading', text_level: 2, page_idx: 1,
          original: '28.4.2 Multinomial PCA', translated: '28.4.2 다항 PCA',
          caption: null, caption_translated: null, img_url: null, bbox: null },
      ],
    };
    globalThis.fetch = () => Promise.resolve({
      ok: true, status: 200,
      json: () => Promise.resolve(RESPONSE), text: () => Promise.resolve(''),
    });
    await import("%(reflow)s");  // auto-init fires load()
    // load() is async + not awaited by auto-init — poll until chunks render.
    for (let i = 0; i < 200 && document.querySelectorAll('#content .chunk').length === 0; i++) {
      await new Promise((r) => setTimeout(r, 5));
    }
    const heading = document.querySelector('.chunk[data-sec="28.4"]');
    const toc = document.getElementById('toc');
    const toggle = document.getElementById('toc-toggle');
    const hiddenBefore = toc.hasAttribute('hidden');
    toggle.dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
    console.log(JSON.stringify({
      chunkCount: document.querySelectorAll('#content .chunk').length,
      headingDataSec: heading ? heading.dataset.sec : null,
      headingSelfRef: heading ? heading.querySelectorAll('.rf-ref').length : -1,
      cites: [...document.querySelectorAll('#content .rf-cite')].map((e) => e.textContent),
      refs: [...document.querySelectorAll('#content .rf-ref')].map((e) => e.dataset.sec),
      tocLinks: document.querySelectorAll('#toc .toc-link').length,
      hiddenBefore, hiddenAfter: toc.hasAttribute('hidden'),
      aria: toggle.getAttribute('aria-expanded'),
    }));
"""


def test_load_builds_enriches_toc_without_order_idx(jsdom_url: str) -> None:
    reflow_js = (REPO / "src" / "ht_lens" / "api" / "static" / "js" / "reflow.js").as_uri()
    script = _LOAD_SCRIPT % {
        "jsdom": jsdom_url,
        "html": REFLOW_HTML.as_posix(),
        "reflow": reflow_js,
    }
    proc = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        capture_output=True,
        text=True,
        cwd=str(REPO),
        check=False,
    )
    if proc.returncode != 0:
        pytest.fail(f"node rc={proc.returncode}\n{proc.stdout}\n{proc.stderr}")
    out = json.loads(proc.stdout.strip().splitlines()[-1])
    # Whole pipeline ran against an order_idx-free response (R1 contract fix).
    assert out["chunkCount"] == 3
    # Heading carries its identity but is NOT enriched into a self-ref (R1 fix).
    assert out["headingDataSec"] == "28.4" and out["headingSelfRef"] == 0
    # Prose enrichment: [BJ05] cited, 28.4 linked, equation 28.116 left plain.
    assert out["cites"] == ["[BJ05]"] and out["refs"] == ["28.4"]
    # Section tree built from headings (28.4, 28.4.2).
    assert out["tocLinks"] >= 2
    # TOC toggle: starts hidden → opens (aria-expanded reflects state).
    assert out["hiddenBefore"] is True and out["hiddenAfter"] is False and out["aria"] == "true"
