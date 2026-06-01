"""Phase 8d-1 — sections.js unit tests (jsdom).

Locks section identity from heading ORIGINALS, the no-synthetic-node tree,
parent-includes-children selection, the ``sectionselect`` event carrying a
stable secNo, ref-jump that does NOT bubble into the chunk-sync handler,
the TOC render, and that the fixed TOC drawer stays outside the compare
grid (loads the real reflow.html).
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
STATIC = REPO / "src" / "ht_lens" / "api" / "static"
MOD = STATIC / "js" / "sections.js"
REFLOW_HTML = STATIC / "reflow.html"


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
    const w = new JSDOM(`<!doctype html><html><body><div id="content"></div></body></html>`).window;
    w.HTMLElement.prototype.scrollIntoView = function () {};  // jsdom stub
    globalThis.window = w; globalThis.document = w.document;
    globalThis.HTMLElement = w.HTMLElement; globalThis.Element = w.Element;
    globalThis.Node = w.Node; globalThis.CustomEvent = w.CustomEvent;
    globalThis.MouseEvent = w.MouseEvent; globalThis.DocumentFragment = w.DocumentFragment;
    const {
      parseSectionNo, buildSectionTree, computeSectionChunks,
      selectSection, selectSectionByHeading, jumpToSection, wireRefJump, renderToc,
    } = await import("%(mod)s");
    // Heading / text chunk factories. NB: chunks carry NO order_idx (matches
    // ReflowChunk in reflow.py); document order == array order (verify-cross
    // R1). The 2nd arg is a positional doc-order hint only, intentionally
    // unused by the section code.
    const H = (id, _order, orig, tr) =>
      ({ id, type: 'heading', original: orig, translated: tr || null });
    const T = (id, _order) => ({ id, type: 'text', original: 'body', translated: '본문' });
"""


def _run(script: str, jsdom_url: str) -> dict:
    full = (_PRELUDE % {"jsdom": jsdom_url, "mod": MOD.as_uri()}) + script
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


def test_parse_section_no_variants(jsdom_url: str) -> None:
    script = """
    console.log(JSON.stringify({
      plain: parseSectionNo('28.4.2 Multinomial PCA'),
      sign: parseSectionNo('§28.4'),
      trailingDot: parseSectionNo('28.4.2. Title'),
      appendix: parseSectionNo('Appendix A.1'),
      empty: parseSectionNo(''),
      bare: parseSectionNo('28 Latent Variable Models'),
    }));
    """
    out = _run(script, jsdom_url)
    assert out["plain"] == "28.4.2" and out["sign"] == "28.4"
    assert out["trailingDot"] == "28.4.2" and out["bare"] == "28"
    assert out["appendix"] is None and out["empty"] is None


def test_build_tree_nests_without_synthetic_nodes(jsdom_url: str) -> None:
    """28.4 nests 28.4.1/28.4.2(>28.4.2.1); no fake 28.3/28 nodes (debate R9)."""
    script = """
    const chunks = [
      H(1,0,'28.3.5 A'), H(2,2,'28.3.5.1 B'), H(3,4,'28.4 C'),
      H(4,6,'28.4.1 D'), H(5,8,'28.4.2 E'), H(6,10,'28.4.2.1 F'), H(7,12,'28.5 G'),
    ];
    const tree = buildSectionTree(chunks);
    const roots = tree.map((n) => n.secNo);
    const c284 = tree.find((n) => n.secNo === '28.4');
    const c2842 = c284.children.find((n) => n.secNo === '28.4.2');
    console.log(JSON.stringify({
      roots,
      kids284: c284.children.map((n) => n.secNo),
      kids2842: c2842.children.map((n) => n.secNo),
    }));
    """
    out = _run(script, jsdom_url)
    # 28.3.5 / 28.5 are roots (no synthetic 28.3 / 28); 28.4 nests its kids.
    assert out["roots"] == ["28.3.5", "28.4", "28.5"]
    assert out["kids284"] == ["28.4.1", "28.4.2"]
    assert out["kids2842"] == ["28.4.2.1"]


def test_section_id_from_original_when_translation_changes_prefix(jsdom_url: str) -> None:
    """Translated heading text must not break section identity (debate R2)."""
    script = """
    const chunks = [H(1, 0, '28.4.2 Multinomial PCA', '[KO] 다항 PCA')];
    const tree = buildSectionTree(chunks);
    console.log(JSON.stringify({ secNo: tree[0].secNo, title: tree[0].title }));
    """
    out = _run(script, jsdom_url)
    assert out["secNo"] == "28.4.2"  # parsed from original, not "[KO] 다항 PCA"
    assert out["title"] == "[KO] 다항 PCA"


def test_compute_section_includes_children_until_next_sibling(jsdom_url: str) -> None:
    """Selecting 28.4 includes 28.4.1/28.4.2 chunks but stops before 28.5."""
    script = """
    const chunks = [
      H(1,0,'28.4 C'), T(2,1), H(3,2,'28.4.1 D'), T(4,3),
      H(5,4,'28.4.2 E'), T(6,5), H(7,6,'28.4.2.1 F'), T(8,7), H(9,8,'28.5 G'), T(10,9),
    ];
    console.log(JSON.stringify(computeSectionChunks('28.4', chunks)));
    """
    out = _run(script, jsdom_url)
    assert out["secNo"] == "28.4"
    assert out["chunkIds"] == [1, 2, 3, 4, 5, 6, 7, 8]  # 28.4 .. 28.4.2.1 body; not 28.5(9,10)


def test_select_section_highlights_and_emits_secno(jsdom_url: str) -> None:
    script = """
    const chunks = [H(1,0,'28.4 C'), T(2,1), H(3,2,'28.4.1 D'), T(4,3), H(5,4,'28.5 G')];
    const content = document.getElementById('content');
    for (const c of chunks) {
      const d = document.createElement('div');
      d.className = 'chunk';
      d.dataset.chunkId = String(c.id);
      content.appendChild(d);
    }
    let evt = null;
    content.addEventListener('sectionselect', (e) => { evt = e.detail; });
    selectSection('28.4', chunks, content);
    const selected = [...content.querySelectorAll('.chunk.section-selected')]
      .map((e) => e.dataset.chunkId);
    console.log(JSON.stringify({
      selected, evtSec: evt && evt.secNo, evtIds: evt && evt.chunkIds }));
    """
    out = _run(script, jsdom_url)
    assert out["selected"] == ["1", "2", "3", "4"]  # 28.4 + 28.4.1 range, not 28.5
    assert out["evtSec"] == "28.4" and out["evtIds"] == [1, 2, 3, 4]


def test_jump_to_section_scrolls_and_flashes(jsdom_url: str) -> None:
    script = """
    const content = document.getElementById('content');
    const h = document.createElement('div');
    h.className = 'chunk'; h.dataset.sec = '28.4'; h.dataset.chunkId = '1';
    content.appendChild(h);
    const ok = jumpToSection('28.4', content);
    const miss = jumpToSection('99.9', content);
    console.log(JSON.stringify({ ok, miss, flashed: h.classList.contains('rf-flash') }));
    """
    out = _run(script, jsdom_url)
    assert out["ok"] is True and out["miss"] is False and out["flashed"] is True


def test_ref_click_does_not_trigger_chunk_sync(jsdom_url: str) -> None:
    """`.rf-ref` click jumps but must NOT bubble into the chunk handler (R4)."""
    script = """
    const content = document.getElementById('content');
    const head = document.createElement('div');
    head.className = 'chunk'; head.dataset.sec = '28.4'; head.dataset.chunkId = '1';
    const body = document.createElement('div');
    body.className = 'chunk'; body.dataset.chunkId = '2';
    const ref = document.createElement('a');
    ref.className = 'rf-ref'; ref.dataset.sec = '28.4'; ref.textContent = '28.4';
    body.appendChild(ref);
    content.append(head, body);
    let synced = false;
    body.addEventListener('click', () => { synced = true; });  // simulates syncToChunk
    wireRefJump(content);
    ref.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
    console.log(JSON.stringify({ synced, flashed: head.classList.contains('rf-flash') }));
    """
    out = _run(script, jsdom_url)
    assert out["synced"] is False  # stopPropagation prevented the chunk handler
    assert out["flashed"] is True  # but the jump still happened


def test_render_toc_nested_with_callbacks(jsdom_url: str) -> None:
    script = """
    const chunks = [H(1,0,'28.4 C'), H(2,2,'28.4.1 D'), H(3,4,'28.5 G')];
    const tree = buildSectionTree(chunks);
    const nav = document.createElement('nav');
    let jumped = null;
    renderToc(tree, nav, { onJump: (s) => { jumped = s; }, onSelect: () => {} });
    const links = [...nav.querySelectorAll('.toc-link')].map((a) => a.textContent);
    const nested = nav.querySelector('li ul .toc-link') !== null;  // 28.4.1 under 28.4
    nav.querySelector('.toc-link[data-sec="28.4"]').dispatchEvent(
      new MouseEvent('click', { bubbles: true, cancelable: true }));
    console.log(JSON.stringify({ links, nested, jumped,
      selects: nav.querySelectorAll('.toc-select').length }));
    """
    out = _run(script, jsdom_url)
    assert out["links"] == ["28.4 C", "28.4.1 D", "28.5 G"]
    assert out["nested"] is True and out["jumped"] == "28.4" and out["selects"] == 3


def test_select_section_by_heading_resolves_duplicates(jsdom_url: str) -> None:
    """verify-cross R1: the product path must anchor a section by its concrete
    heading chunk id, so a SECOND '28.4' resolves to its own range — not the
    first. Emits headingChunkId for the 8d-2 chat anchor."""
    script = """
    const content = document.getElementById('content');
    // Two '28.4' headings (e.g. body + appendix excerpt) with distinct ids.
    const chunks = [
      H(1, 0, '28.4 First'), T(2, 1), H(3, 2, '28.5 Mid'),
      H(4, 4, '28.4 Second'), T(5, 5), H(6, 6, '28.6 End'),
    ];
    for (const c of chunks) {
      const d = document.createElement('div');
      d.className = 'chunk'; d.dataset.chunkId = String(c.id);
      content.appendChild(d);
    }
    let evt = null;
    content.addEventListener('sectionselect', (e) => { evt = e.detail; });
    selectSectionByHeading(4, chunks, content);  // pick the SECOND 28.4 (id 4)
    console.log(JSON.stringify({
      headingChunkId: evt && evt.headingChunkId,
      secNo: evt && evt.secNo,
      chunkIds: evt && evt.chunkIds,
    }));
    """
    out = _run(script, jsdom_url)
    assert out["headingChunkId"] == 4  # the SECOND 28.4, not the first (id 1)
    assert out["secNo"] == "28.4"
    assert out["chunkIds"] == [4, 5]  # second 28.4's range, stops before 28.6


def test_toc_select_button_passes_heading_chunk_id(jsdom_url: str) -> None:
    """verify-cross R2: clicking a rendered .toc-select button must call
    onSelect with the heading's chunk id — the real product path (TOC →
    section select → chat anchor), not the bypassed direct call."""
    script = """
    const chunks = [H(7, 0, '28.4 C'), H(9, 2, '28.4.1 D'), H(11, 4, '28.5 G')];
    const nav = document.createElement('nav');
    let received = null;
    renderToc(buildSectionTree(chunks), nav, {
      onJump: () => {}, onSelect: (cid) => { received = cid; },
    });
    const btn = nav.querySelector('.toc-select[data-chunk-id="7"]');
    btn.dispatchEvent(new w.MouseEvent('click', { bubbles: true, cancelable: true }));
    console.log(JSON.stringify({
      received, btnCount: nav.querySelectorAll('.toc-select').length }));
    """
    out = _run(script, jsdom_url)
    assert out["received"] == 7  # heading chunk id (not secNo) → duplicate-safe anchor
    assert out["btnCount"] == 3


_LAYOUT_SCRIPT = """
    import { JSDOM } from "%(jsdom)s";
    import { readFileSync } from "node:fs";
    const html = readFileSync("%(html)s", "utf-8");
    const w = new JSDOM(html).window;
    const d = w.document;
    const layout = d.getElementById('layout');
    layout.dataset.mode = 'compare';
    const toc = d.getElementById('toc');
    const childIds = [...layout.children].map((c) => c.id || c.className);
    console.log(JSON.stringify({
      tocInsideLayout: layout.contains(toc),
      layoutChildren: layout.children.length,
      childIds,
      hasPdf: !!d.getElementById('pane-pdf'),
      hasContent: !!d.getElementById('content'),
    }));
"""


def test_toc_drawer_outside_compare_grid(jsdom_url: str) -> None:
    """Load the real reflow.html: #toc must be OUTSIDE .layout so the
    compare 1fr-1fr grid keeps both panes (debate R6)."""
    script = _LAYOUT_SCRIPT % {"jsdom": jsdom_url, "html": REFLOW_HTML.as_posix()}
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
    assert out["tocInsideLayout"] is False  # drawer outside grid → grid intact
    assert out["layoutChildren"] == 2  # only pane-pdf + main
    assert out["hasPdf"] is True and out["hasContent"] is True
