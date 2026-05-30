"""Phase 8d-2a — chat.js unit tests (jsdom).

Locks the selection state (paragraph vs section, the latter via the 8d-1
``sectionselect`` event carrying ``headingChunkId``) and that assistant
markdown is sanitised through marked + DOMPurify (challenge R7 — no script /
event handlers / javascript: hrefs survive).
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
CHAT_JS = REPO / "src" / "ht_lens" / "api" / "static" / "js" / "chat.js"


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


_PRELUDE = """
    import { JSDOM } from "%(jsdom)s";
    const w = new JSDOM(`<!doctype html><html><body>
      <div id="chat-status"></div>
      <div id="content"></div>
      <div id="chat-messages"></div>
    </body></html>`).window;
    globalThis.window = w; globalThis.document = w.document;
    globalThis.HTMLElement = w.HTMLElement; globalThis.Element = w.Element;
    globalThis.Node = w.Node; globalThis.NodeFilter = w.NodeFilter;
    globalThis.DocumentFragment = w.DocumentFragment; globalThis.CustomEvent = w.CustomEvent;
    globalThis.MouseEvent = w.MouseEvent;
    globalThis.fetch = () => Promise.resolve({ ok: true, json: () => Promise.resolve([]) });
    const { setSelection, renderAssistant, initChat } = await import("%(chat)s");
"""


def _run(script: str, jsdom_url: str) -> dict:
    full = (_PRELUDE % {"jsdom": jsdom_url, "chat": CHAT_JS.as_uri()}) + script
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


def test_set_selection_paragraph_and_section(jsdom_url: str) -> None:
    script = """
    const s = document.getElementById('chat-status');
    setSelection({ type: 'chunk', chunkId: '5', label: '#5' });
    const para = s.textContent;
    setSelection({ type: 'section', chunkId: 13, label: '28.4' });
    const sec = s.textContent;
    setSelection(null);
    console.log(JSON.stringify({ para, sec, cleared: s.textContent }));
    """
    out = _run(script, jsdom_url)
    assert "문단 선택: #5" in out["para"]
    assert "섹션 선택: 28.4" in out["sec"]
    assert "선택된 항목 없음" in out["cleared"]


def test_section_select_event_drives_selection(jsdom_url: str) -> None:
    """initChat consumes the 8d-1 sectionselect event (heading chunk anchor)."""
    script = """
    const content = document.getElementById('content');
    initChat({ docId: 1, contentEl: content });
    content.dispatchEvent(new w.CustomEvent('sectionselect', {
      detail: { secNo: '28.4.2', headingChunkId: 42, chunkIds: [42, 43] }, bubbles: true,
    }));
    console.log(JSON.stringify({ status: document.getElementById('chat-status').textContent }));
    """
    out = _run(script, jsdom_url)
    assert "섹션 선택: 28.4.2" in out["status"]


def test_render_assistant_sanitizes_html(jsdom_url: str) -> None:
    """marked + DOMPurify must strip script / event handlers / js: hrefs
    while keeping markdown (challenge R7)."""
    script = r"""
    const c = document.createElement('div');
    renderAssistant(
      c,
      '**굵게** <script>bad()</script>' +
      '<a href="javascript:bad()">l</a> <img src=x onerror="bad()"> 끝',
    );
    console.log(JSON.stringify({
      hasScript: c.querySelector('script') !== null,
      hasOnerror: [...c.querySelectorAll('*')].some((el) => el.hasAttribute('onerror')),
      jsHref: [...c.querySelectorAll('a')].some(
        (a) => (a.getAttribute('href') || '').toLowerCase().startsWith('javascript:')),
      hasBold: c.querySelector('strong') !== null,
      endText: c.textContent.includes('끝'),
    }));
    """
    out = _run(script, jsdom_url)
    assert out["hasScript"] is False  # <script> stripped
    assert out["hasOnerror"] is False  # event handler stripped
    assert out["jsHref"] is False  # javascript: href neutralised
    assert out["hasBold"] is True and out["endText"] is True  # markdown preserved
