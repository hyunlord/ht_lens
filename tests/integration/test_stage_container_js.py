"""Phase 6b — jsdom behavioral tests for stage_container.js.

Drives ``mountPage`` and ``unmountPage`` through real DOM + AbortController
semantics so the race guards (debate §4 fix) are locked beyond grep. Skipped
when ``node`` or a local ``jsdom`` install is unavailable.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
STAGE = REPO / "src" / "ht_lens" / "api" / "static" / "js" / "components" / "stage_container.js"


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


def _run_with_jsdom(script: str, jsdom_url: str) -> dict:
    full = f"""
    import {{ JSDOM }} from "{jsdom_url}";
    const w = new JSDOM("<!doctype html><html><body><div id='stage'></div></body></html>", {{
      runScripts: "outside-only",
      pretendToBeVisual: true,
    }}).window;
    globalThis.window = w;
    globalThis.document = w.document;
    globalThis.performance = w.performance;
    globalThis.IntersectionObserver = class {{
      observe() {{}}
      disconnect() {{}}
      unobserve() {{}}
    }};
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


@pytest.fixture
def jsdom_url() -> str:
    url = _find_jsdom()
    if url is None:
        pytest.skip("no jsdom install located on host")
    return url


def test_mount_page_ignores_stale_fetch_after_unmount(jsdom_url: str) -> None:
    """Phase 6b debate §3/§4: a late page fetch resolving AFTER unmountPage
    must not write into pageDataById or render into the row. The mountToken
    bump + AbortController.abort must both invalidate the in-flight mount."""
    script = f"""
    // Stub ``fetch`` so we control resolution timing.
    let resolveFn;
    const pending = new Promise((res) => {{ resolveFn = res; }});
    globalThis.fetch = (url, init) => {{
        // Honour AbortSignal so AbortError surfaces if abort() is called.
        if (init?.signal) {{
            init.signal.addEventListener("abort", () => {{
                resolveFn?.(new Response(null, {{ status: 499 }}));
            }});
        }}
        return pending;
    }};

    const sc = await import("{STAGE.as_uri()}");
    const stage = document.getElementById("stage");
    // Build a single placeholder row so renderRowContent can find it.
    sc.buildPlaceholderRows(stage, [
        {{ page_num: 1, width: 612, height: 792, rotation: 0,
           render: {{ dpi: 72, pixel_w: 612, pixel_h: 792, scale: 1 }} }}
    ], 1, "translation");

    const ctx = {{
        doc: {{ id: 1 }},
        docId: 1,
        stageEl: stage,
        getThreadsByBlock: () => null,
    }};
    // Kick off mount (fetch still pending).
    const mountPromise = sc.mountPage(1, ctx);
    // Now unmount — must abort + bump token.
    sc.unmountPage(1, ctx);
    // Late resolution arrives.
    resolveFn(new Response(JSON.stringify({{
        page_num: 1, width: 612, height: 792, rotation: 0,
        render: {{ dpi: 72, pixel_w: 612, pixel_h: 792, scale: 1 }},
        blocks: [{{ id: 99, block_local_id: "p1_b001", type: "text",
                    bbox: [10, 10, 50, 50], order: 0,
                    original_text: "x", translated_text: "y", has_thread: false }}]
    }}), {{ status: 200, headers: {{ "Content-Type": "application/json" }} }}));
    await mountPromise;
    const row = stage.querySelector('.page-row[data-page="1"]');
    const internals = sc._internals();
    console.log(JSON.stringify({{
        mountedAfter: internals.mountedPages.has(1),
        rowMounted: row?.dataset.mounted,
        // The block that would only exist if the late fetch had been honoured.
        blockMounted: !!document.querySelector('[data-block-id="99"]'),
    }}));
    """
    out = _run_with_jsdom(script, jsdom_url)
    # The race guards must keep both flags false: late fetch ignored.
    assert out["mountedAfter"] is False
    assert out["blockMounted"] is False
    # The row's mounted attribute should reflect the unmount.
    assert out["rowMounted"] in (None, "0")


def test_mount_page_renders_blocks_when_fetch_resolves_in_order(
    jsdom_url: str,
) -> None:
    """Sanity: when the fetch resolves before any unmount, blocks render."""
    script = f"""
    globalThis.fetch = (_url) => Promise.resolve(new Response(JSON.stringify({{
        page_num: 1, width: 612, height: 792, rotation: 0,
        render: {{ dpi: 72, pixel_w: 612, pixel_h: 792, scale: 1 }},
        blocks: [{{ id: 42, block_local_id: "p1_b001", type: "text",
                    bbox: [10, 10, 100, 40], order: 0,
                    original_text: "hello", translated_text: "안녕",
                    has_thread: false }}]
    }}), {{ status: 200, headers: {{ "Content-Type": "application/json" }} }}));
    const sc = await import("{STAGE.as_uri()}");
    const stage = document.getElementById("stage");
    sc.buildPlaceholderRows(stage, [
        {{ page_num: 1, width: 612, height: 792, rotation: 0,
           render: {{ dpi: 72, pixel_w: 612, pixel_h: 792, scale: 1 }} }}
    ], 1, "translation");
    const ctx = {{ doc: {{ id: 1 }}, docId: 1, stageEl: stage,
                  getThreadsByBlock: () => null }};
    await sc.mountPage(1, ctx);
    console.log(JSON.stringify({{
        blockMounted: !!document.querySelector('[data-block-id="42"]'),
        mountedFlag: sc._internals().mountedPages.has(1),
    }}));
    """
    out = _run_with_jsdom(script, jsdom_url)
    assert out["blockMounted"] is True
    assert out["mountedFlag"] is True
