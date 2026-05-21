"""Phase 5 — XSS sanitisation check for ``render_markdown.js``.

Runs the actual module via node + jsdom and verifies that DOMPurify strips
the standard XSS payloads before the panel ever sees them. Skipped when
either ``node`` or a usable ``jsdom`` install cannot be located.

Note: jsdom is intentionally NOT a project dependency — Phase 5 forbids
new Python or JS deps. This test opportunistically uses a system jsdom
when present (e.g. via npm); otherwise we fall back to the simpler
``test_static_serving::test_render_markdown_js_uses_dompurify_hook``
grep guard.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
RENDER_MD = REPO / "src" / "ht_lens" / "api" / "static" / "js" / "utils" / "render_markdown.js"


def _find_jsdom() -> str | None:
    """Locate a jsdom install on the host. Returns the JS module path or None."""
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
    const w = new JSDOM("").window;
    globalThis.window = w;
    globalThis.document = w.document;
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


def test_render_markdown_strips_script_tag(jsdom_url: str) -> None:
    md = "<script>alert(1)</script><p>safe</p>"
    script = f"""
    const {{ renderMarkdown }} = await import("{RENDER_MD.as_uri()}");
    const out = renderMarkdown({json.dumps(md)});
    console.log(JSON.stringify({{ out }}));
    """
    out = _run_with_jsdom(script, jsdom_url)
    assert "<script>" not in out["out"]
    assert "alert" not in out["out"]
    assert "<p>safe</p>" in out["out"]


def test_render_markdown_strips_javascript_href(jsdom_url: str) -> None:
    md = '<a href="javascript:bad()">x</a>'
    script = f"""
    const {{ renderMarkdown }} = await import("{RENDER_MD.as_uri()}");
    const out = renderMarkdown({json.dumps(md)});
    console.log(JSON.stringify({{ out }}));
    """
    out = _run_with_jsdom(script, jsdom_url)
    assert "javascript:" not in out["out"]


def test_render_markdown_strips_iframe(jsdom_url: str) -> None:
    md = '<iframe src="evil"></iframe><p>kept</p>'
    script = f"""
    const {{ renderMarkdown }} = await import("{RENDER_MD.as_uri()}");
    const out = renderMarkdown({json.dumps(md)});
    console.log(JSON.stringify({{ out }}));
    """
    out = _run_with_jsdom(script, jsdom_url)
    assert "<iframe" not in out["out"]
    assert "<p>kept</p>" in out["out"]


def test_render_markdown_strips_onerror(jsdom_url: str) -> None:
    md = '<img src="x" onerror="bad()">'
    script = f"""
    const {{ renderMarkdown }} = await import("{RENDER_MD.as_uri()}");
    const out = renderMarkdown({json.dumps(md)});
    console.log(JSON.stringify({{ out }}));
    """
    out = _run_with_jsdom(script, jsdom_url)
    assert "onerror" not in out["out"]


def test_render_markdown_external_link_opens_new_tab(jsdom_url: str) -> None:
    md = "[example](https://example.com)"
    script = f"""
    const {{ renderMarkdown }} = await import("{RENDER_MD.as_uri()}");
    const out = renderMarkdown({json.dumps(md)});
    console.log(JSON.stringify({{ out }}));
    """
    out = _run_with_jsdom(script, jsdom_url)
    assert 'target="_blank"' in out["out"]
    assert "noopener" in out["out"]
