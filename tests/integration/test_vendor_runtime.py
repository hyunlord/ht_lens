"""Phase 5 — vendor library ESM smoke test via node.

The viewer imports ``marked.esm.js`` and ``purify.es.mjs`` via ``<script
type="module">``. These tests load both with the same dynamic-import path the
browser uses and assert the exported shape. Skipped automatically when
``node`` is not on PATH.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
VENDOR = REPO / "src" / "ht_lens" / "api" / "static" / "vendor"


def _node_available() -> bool:
    return shutil.which("node") is not None


pytestmark = pytest.mark.skipif(not _node_available(), reason="node binary not on PATH")


def _run_node(script: str) -> dict:
    proc = subprocess.run(
        ["node", "--input-type=module", "-e", script],
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


def test_marked_esm_is_importable_and_parses_markdown() -> None:
    marked_url = (VENDOR / "marked.esm.js").as_uri()
    script = f"""
    const m = await import("{marked_url}");
    const out = {{
      hasMarked: typeof m.marked === "function",
      parseFn: typeof m.marked.parse,
      html: m.marked.parse("# hi\\n\\n**bold**"),
    }};
    console.log(JSON.stringify(out));
    """
    out = _run_node(script)
    assert out["hasMarked"] is True
    assert out["parseFn"] == "function"
    assert "<h1>hi</h1>" in out["html"]
    assert "<strong>bold</strong>" in out["html"]


def test_dompurify_esm_is_importable_factory() -> None:
    """The ES module ships an instance pre-bound to ``window`` in browsers and a
    factory function otherwise. We accept either — both are valid."""
    purify_url = (VENDOR / "purify.es.mjs").as_uri()
    script = f"""
    const m = await import("{purify_url}");
    const def = m.default;
    const out = {{
      hasDefault: def !== undefined,
      typeofDefault: typeof def,
      hasSanitize: typeof def.sanitize === "function",
      hasVersion: typeof def.version === "string",
    }};
    console.log(JSON.stringify(out));
    """
    out = _run_node(script)
    assert out["hasDefault"] is True
    # In node we get the factory (function); in browser an object with sanitize.
    assert out["typeofDefault"] in ("function", "object")
    assert out["hasVersion"] is True


def test_vendor_files_exist() -> None:
    assert (VENDOR / "marked.esm.js").is_file()
    assert (VENDOR / "purify.es.mjs").is_file()
    assert (VENDOR / "LICENSE").is_file()
