"""Phase 4 — algorithm-level checks on ``js/utils/font_fit.js`` via Node.

Skipped automatically when ``node`` is not on PATH. The JS module is loaded as
ES module and exercised through a small harness; we assert that:
  * the returned size lies inside ``[MIN_SIZE, MAX_SIZE]``
  * monotonicity holds: a wider bbox never returns a smaller size
  * mixed CJK + long-ASCII content respects the bbox (under the Node-side
    estimator, which is conservative)

Coupling: this exercises the *estimator* fallback (no canvas in Node). The
browser-side measurement is verified manually in 5-B.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
JS_PATH = REPO / "src" / "ht_lens" / "api" / "static" / "js" / "utils" / "font_fit.js"


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


def test_fits_within_bounds() -> None:
    script = f"""
    import {{ fitFontSize, MIN_SIZE, MAX_SIZE }} from "{JS_PATH.as_uri()}";
    const cases = [
      ["Hello world", 200, 50, "normal"],
      ["한국어 텍스트 fitting 테스트", 200, 50, "normal"],
      ["A", 10, 10, "normal"],
      ["A very long English line that almost certainly needs to wrap several times to fit",
       150, 60, "normal"],
      ["한국어와 English가 섞인 mixed-script 텍스트로 fitting 검증", 200, 80, "600"],
    ];
    const out = cases.map(([t, w, h, weight]) => ({{
      size: fitFontSize(t, w, h, weight), MIN_SIZE, MAX_SIZE,
    }}));
    console.log(JSON.stringify(out));
    """
    out = _run_node(script)
    for entry in out:
        assert entry["MIN_SIZE"] <= entry["size"] <= entry["MAX_SIZE"]


def test_wider_bbox_returns_size_at_least_as_large() -> None:
    """Monotonicity: doubling the bbox width should never shrink the chosen size."""
    script = f"""
    import {{ fitFontSize }} from "{JS_PATH.as_uri()}";
    const text = "한글과 영문이 함께 들어간 medium-length text for fitting.";
    const small = fitFontSize(text, 120, 80, "normal");
    const wider = fitFontSize(text, 240, 80, "normal");
    const taller = fitFontSize(text, 120, 160, "normal");
    console.log(JSON.stringify({{ small, wider, taller }}));
    """
    out = _run_node(script)
    assert out["wider"] >= out["small"]
    assert out["taller"] >= out["small"]


def test_mixed_cjk_long_ascii_respects_bbox() -> None:
    """``fits(size, ...)`` is true for the returned size — i.e. the algorithm
    keeps its own promise that the chosen size will not overflow."""
    script = f"""
    import {{ fitFontSize, fits }} from "{JS_PATH.as_uri()}";
    const text = "한국어와 함께 a fairly long English clause that the fitter should " +
                 "wrap or shrink so the entire block stays inside the bbox.";
    const w = 220;
    const h = 90;
    const size = fitFontSize(text, w, h, "normal");
    const ok = fits(size, text, w, h, "normal");
    console.log(JSON.stringify({{ size, ok }}));
    """
    out = _run_node(script)
    assert out["ok"] is True, f"size={out['size']} did not actually fit"


def test_degenerate_inputs() -> None:
    """Empty text and zero-area bbox should return MIN_SIZE without crashing."""
    script = f"""
    import {{ fitFontSize, MIN_SIZE }} from "{JS_PATH.as_uri()}";
    const a = fitFontSize("", 100, 100, "normal");
    const b = fitFontSize("text", 0, 100, "normal");
    const c = fitFontSize("text", 100, 0, "normal");
    console.log(JSON.stringify({{ a, b, c, MIN_SIZE }}));
    """
    out = _run_node(script)
    assert out["a"] == out["MIN_SIZE"]
    assert out["b"] == out["MIN_SIZE"]
    assert out["c"] == out["MIN_SIZE"]
