"""Phase 8e-4 — compare-mode scroll-sync (jsdom).

Locks the deterministic core that replaced IntersectionObserver (jsdom can't
validate IO): ``pickCurrentPage`` (binary search over page boundaries) and
``initCompareSync.syncNow`` (scrolls the left PDF pane to the current page ONLY
in compare mode). Mocks getBoundingClientRect/scrollIntoView since jsdom has no
layout (verify-cross §2.7/§3.8).
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


_PRELUDE = """
    import { JSDOM } from "%(jsdom)s";
    // Import with an EMPTY body so reflow.js's module-level auto-init
    // (``if (paneReflow && layout)``) stays inert — otherwise load() runs on
    // import and wipes #content's children before the test builds its DOM.
    const w = new JSDOM(`<!doctype html><html><body></body></html>`).window;
    globalThis.window = w; globalThis.document = w.document;
    globalThis.HTMLElement = w.HTMLElement; globalThis.Element = w.Element;
    globalThis.Node = w.Node; globalThis.DocumentFragment = w.DocumentFragment;
    globalThis.location = w.location;
    w.Element.prototype.scrollIntoView = function () { this.dataset.scrolled = "1"; };
    if (!w.requestAnimationFrame) w.requestAnimationFrame = (fn) => setTimeout(fn, 0);
    const doc = w.document;
    const { pickCurrentPage, initCompareSync } = await import("%(reflow)s");
    // Now build the compare-mode DOM (auto-init already skipped above).
    doc.body.innerHTML = `
      <div id="layout" data-mode="single">
        <main class="pane--reflow" id="pane">
          <article id="content">
            <div class="chunk" data-page-idx="0"></div>
            <div class="chunk" data-page-idx="0"></div>
            <div class="chunk" data-page-idx="1"></div>
            <div class="chunk" data-page-idx="2"></div>
          </article>
        </main>
      </div>
      <aside id="pane-pdf">
        <div class="pdf-page" data-page-idx="0"></div>
        <div class="pdf-page" data-page-idx="1"></div>
        <div class="pdf-page" data-page-idx="2"></div>
      </aside>`;
    // Absolute page offsets 0/100/300; real browsers shift rect.top by scrollTop,
    // so the mock subtracts pane.scrollTop (the code's offset formula relies on it).
    const tops = { 0: 0, 1: 100, 2: 300 };
    const _paneMock = doc.querySelector("#pane");
    _paneMock.getBoundingClientRect = () => ({ top: 0 });
    for (const el of doc.querySelectorAll(".chunk")) {
      const p = Number(el.dataset.pageIdx);
      el.getBoundingClientRect = () => ({ top: tops[p] - _paneMock.scrollTop });
    }
"""


def _run(body: str, jsdom_url: str) -> dict:
    full = (_PRELUDE % {"jsdom": jsdom_url, "reflow": REFLOW_JS.as_uri()}) + body
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


def test_pick_current_page_binary_search(jsdom_url: str) -> None:
    out = _run(
        """
        const b = [{pageIdx:0,offset:0},{pageIdx:1,offset:100},{pageIdx:2,offset:300}];
        console.log(JSON.stringify({
          top: pickCurrentPage(b, 0),
          mid: pickCurrentPage(b, 150),   // between 100 and 300 → page 1
          last: pickCurrentPage(b, 350),  // past 300 → page 2
          empty: pickCurrentPage([], 50),
        }));
        """,
        jsdom_url,
    )
    assert out == {"top": 0, "mid": 1, "last": 2, "empty": None}


def test_sync_scrolls_left_pane_only_in_compare_mode(jsdom_url: str) -> None:
    out = _run(
        """
        const layout = doc.getElementById("layout");
        const pane = doc.getElementById("pane");
        const panePdf = doc.getElementById("pane-pdf");
        const sync = initCompareSync({ contentEl: doc.getElementById("content"), panePdf, layout });
        const hl = () => panePdf.querySelector(".pdf-page.hl")?.dataset.pageIdx ?? null;

        // single mode → no left scroll
        pane.scrollTop = 150; sync.syncNow();
        const single = hl();

        // compare mode, scrollTop in page 1 band → left highlights page 1
        layout.dataset.mode = "compare"; sync.recompute(); pane.scrollTop = 150; sync.syncNow();
        const p1 = hl();
        const p1Scrolled = panePdf.querySelector('.pdf-page[data-page-idx="1"]').dataset.scrolled;

        // scroll into page 2 band → page 2
        pane.scrollTop = 350; sync.syncNow();
        const p2 = hl();

        console.log(JSON.stringify({ single, p1, p1Scrolled, p2 }));
        """,
        jsdom_url,
    )
    assert out == {"single": None, "p1": "1", "p1Scrolled": "1", "p2": "2"}


def test_teardown_detaches_scroll_handler(jsdom_url: str) -> None:
    out = _run(
        """
        const layout = doc.getElementById("layout");
        const pane = doc.getElementById("pane");
        const panePdf = doc.getElementById("pane-pdf");
        layout.dataset.mode = "compare";
        const sync = initCompareSync({ contentEl: doc.getElementById("content"), panePdf, layout });
        sync.teardown();
        // after teardown, a scroll event must NOT sync the left pane
        pane.scrollTop = 350;
        pane.dispatchEvent(new w.Event("scroll"));
        const after = panePdf.querySelector(".pdf-page.hl")?.dataset.pageIdx ?? null;
        console.log(JSON.stringify({ after }));
        """,
        jsdom_url,
    )
    assert out == {"after": None}
