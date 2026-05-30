"""Phase 8d-1 — enrich_inline.js unit tests (jsdom).

Locks the citation/section-ref inline styler: digit-required citations
(so ``[KO]`` is never styled), membership-gated section refs (so equation
numbers stay plain), multiple adjacent matches in one text node, and the
KaTeX-safe skip (text under ``.katex`` is never touched).
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
MOD = REPO / "src" / "ht_lens" / "api" / "static" / "js" / "utils" / "enrich_inline.js"


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
    const w = new JSDOM("<!doctype html><html><body></body></html>").window;
    globalThis.window = w; globalThis.document = w.document;
    globalThis.HTMLElement = w.HTMLElement; globalThis.Element = w.Element;
    globalThis.Node = w.Node; globalThis.NodeFilter = w.NodeFilter;
    globalThis.DocumentFragment = w.DocumentFragment;
    const { enrichInline } = await import("%(mod)s");
    // Build a <p> holding `text`, enrich with `nums` (array), return the <p>.
    const run = (text, nums) => {
      const p = document.createElement('p');
      p.textContent = text;
      enrichInline(p, new Set(nums || []));
      return p;
    };
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


def test_citation_excludes_digitless_markers(jsdom_url: str) -> None:
    """[KO]/[EN]/[Note] must NOT style; [BJ05]/[Kha+10] must (debate R1)."""
    script = """
    const p = run('[KO] [EN] [Note] see [BJ05] and [Kha+10] also [CDS02]', []);
    const cites = [...p.querySelectorAll('.rf-cite')].map((e) => e.textContent);
    console.log(JSON.stringify({ cites }));
    """
    out = _run(script, jsdom_url)
    assert out["cites"] == ["[BJ05]", "[Kha+10]", "[CDS02]"]


def test_section_ref_membership_only(jsdom_url: str) -> None:
    """Dotted numbers link only when they name a real heading (debate R11)."""
    script = """
    const p = run('see 28.3.5 and equation 28.116 also fig 28.22', ['28.3.5']);
    const refs = [...p.querySelectorAll('.rf-ref')].map((e) => e.dataset.sec);
    console.log(JSON.stringify({ refs, text: p.textContent }));
    """
    out = _run(script, jsdom_url)
    assert out["refs"] == ["28.3.5"]  # 28.116 / 28.22 not in set → plain
    assert "28.116" in out["text"] and "28.22" in out["text"]  # preserved


def test_multiple_adjacent_matches_one_node(jsdom_url: str) -> None:
    """Adjacent citations + multiple refs in one text node, no text loss."""
    script = """
    const p = run('[BJ05][CDS02] see 28.3.5 and 28.4.2', ['28.3.5', '28.4.2']);
    console.log(JSON.stringify({
      cites: p.querySelectorAll('.rf-cite').length,
      refs: p.querySelectorAll('.rf-ref').length,
      text: p.textContent,
    }));
    """
    out = _run(script, jsdom_url)
    assert out["cites"] == 2 and out["refs"] == 2
    assert out["text"] == "[BJ05][CDS02] see 28.3.5 and 28.4.2"  # nothing dropped


def test_katex_zone_is_skipped(jsdom_url: str) -> None:
    """Text under .katex is never wrapped; sibling text still is (debate R5)."""
    script = """
    const p = document.createElement('p');
    const k = document.createElement('span');
    k.className = 'katex';
    k.textContent = '[BJ05] 28.3.5';   // would-be matches, but inside KaTeX
    p.appendChild(k);
    p.appendChild(document.createTextNode(' tail [CDS02] 28.4.2'));
    enrichInline(p, new Set(['28.3.5', '28.4.2']));
    console.log(JSON.stringify({
      insideKatex: k.querySelectorAll('.rf-cite, .rf-ref').length,
      outsideCite: [...p.querySelectorAll('.rf-cite')].map((e) => e.textContent),
      outsideRef: [...p.querySelectorAll('.rf-ref')].map((e) => e.dataset.sec),
    }));
    """
    out = _run(script, jsdom_url)
    assert out["insideKatex"] == 0  # KaTeX content untouched
    assert out["outsideCite"] == ["[CDS02]"] and out["outsideRef"] == ["28.4.2"]


def test_plain_integers_and_decimals_untouched(jsdom_url: str) -> None:
    """Bare integers (150, 16) and unknown decimals (0.5) are left alone."""
    script = """
    const p = run('We observe N = 150 vectors of length D = 16, ratio 0.5', []);
    console.log(JSON.stringify({
      refs: p.querySelectorAll('.rf-ref').length,
      cites: p.querySelectorAll('.rf-cite').length,
      same: p.textContent === 'We observe N = 150 vectors of length D = 16, ratio 0.5',
    }));
    """
    out = _run(script, jsdom_url)
    assert out["refs"] == 0 and out["cites"] == 0 and out["same"] is True
