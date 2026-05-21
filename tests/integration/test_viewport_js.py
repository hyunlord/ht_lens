"""Phase 6c — viewport.js + stage_container.pickActivePage jsdom tests."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
VIEWPORT = REPO / "src" / "ht_lens" / "api" / "static" / "js" / "utils" / "viewport.js"
STAGE = REPO / "src" / "ht_lens" / "api" / "static" / "js" / "components" / "stage_container.js"


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
        pytest.fail(f"node failed rc={proc.returncode}\nstdout={proc.stdout}\nstderr={proc.stderr}")
    return json.loads(proc.stdout.strip().splitlines()[-1])


def test_compute_fit_zoom_snaps_down_to_largest_step() -> None:
    """Phase 6c debate §2: result must be the largest ZOOM_STEPS value
    <= target so the page never overflows the stage width."""
    script = f"""
    const {{ computeFitZoom }} = await import("{VIEWPORT.as_uri()}");
    const wideStage = computeFitZoom({{
        pageWidthPt: 612, scale: 2.78, stageWidthPx: 1200, viewMode: "translation"
    }});
    const tinyStage = computeFitZoom({{
        pageWidthPt: 612, scale: 2.78, stageWidthPx: 400, viewMode: "translation"
    }});
    const bothMode = computeFitZoom({{
        pageWidthPt: 612, scale: 2.78, stageWidthPx: 2000, viewMode: "both"
    }});
    console.log(JSON.stringify({{ wideStage, tinyStage, bothMode }}));
    """
    out = _run_node(script)
    # 1200px stage / 1701px natural ≈ 0.69 → snap down to 0.5 (largest step ≤ target).
    assert out["wideStage"] == 0.5
    # Tiny stage clamps to smallest step (0.5).
    assert out["tinyStage"] == 0.5
    # Both mode: 2000px / (1701 * 2 + 16 + 32) ≈ 0.57 → 0.5.
    assert out["bothMode"] == 0.5


def test_compute_fit_zoom_uses_view_mode_for_pane_count() -> None:
    """Debate §3 fix: the caller passes viewModeActual so paneCount tracks
    the *actual* layout (chat panel open collapses both → translation)."""
    script = f"""
    const {{ computeFitZoom }} = await import("{VIEWPORT.as_uri()}");
    // Same stage width; translation should fit a larger zoom than both.
    const single = computeFitZoom({{
        pageWidthPt: 612, scale: 2.78, stageWidthPx: 1700, viewMode: "translation"
    }});
    const dual = computeFitZoom({{
        pageWidthPt: 612, scale: 2.78, stageWidthPx: 1700, viewMode: "both"
    }});
    console.log(JSON.stringify({{ single, dual }}));
    """
    out = _run_node(script)
    assert out["single"] >= out["dual"], (
        f"single pane should fit a larger or equal zoom than both: "
        f"single={out['single']} dual={out['dual']}"
    )


def test_pick_active_page_prefers_viewport_midpoint() -> None:
    """Phase 6c scroll fix: when several rows are intersecting, pick the
    one that contains the viewport midpoint — NOT the one with the largest
    intersectionRatio. On tall pages the second page can dominate the
    visible area while the first page still has a smaller-but-higher
    ratio."""
    script = f"""
    const sc = await import("{STAGE.as_uri()}");

    // Fake stage element + per-page rows that we control geometrically.
    function row(top, bottom) {{
        return {{
            getBoundingClientRect: () => ({{ top, bottom, height: bottom - top }}),
        }};
    }}
    const rows = {{
        1: row(0, 800),    // mostly above viewport
        2: row(800, 1800), // contains midpoint (viewport 500-1500)
        3: row(1800, 2800), // below viewport
    }};
    const stageEl = {{
        getBoundingClientRect: () => ({{ top: 500, height: 1000 }}),
        querySelector: (sel) => {{
            const m = sel.match(/data-page="(\\d+)"/);
            return m ? rows[m[1]] : null;
        }},
    }};
    const visibility = new Map();
    // Page 1 has the highest ratio but doesn't contain the midpoint.
    visibility.set(1, 0.9);
    visibility.set(2, 0.5);
    visibility.set(3, 0.2);
    const picked = sc.pickActivePage(stageEl, visibility);
    console.log(JSON.stringify({{ picked }}));
    """
    out = _run_node(script)
    assert out["picked"] == 2, f"midpoint-based pick should select page 2; got {out['picked']}"


def test_pick_active_page_falls_back_to_ratio_when_no_midpoint_hit() -> None:
    script = f"""
    const sc = await import("{STAGE.as_uri()}");
    const rows = {{
        4: {{ getBoundingClientRect: () => ({{ top: -100, bottom: -50 }}) }},
        5: {{ getBoundingClientRect: () => ({{ top: 2000, bottom: 3000 }}) }},
    }};
    const stageEl = {{
        getBoundingClientRect: () => ({{ top: 500, height: 1000 }}),
        querySelector: (sel) => {{
            const m = sel.match(/data-page="(\\d+)"/);
            return m ? rows[m[1]] : null;
        }},
    }};
    const visibility = new Map([[4, 0.1], [5, 0.4]]);
    const picked = sc.pickActivePage(stageEl, visibility);
    console.log(JSON.stringify({{ picked }}));
    """
    out = _run_node(script)
    assert out["picked"] == 5  # largest ratio fallback


def test_pick_active_page_returns_minus_one_when_empty() -> None:
    script = f"""
    const sc = await import("{STAGE.as_uri()}");
    const stageEl = {{ getBoundingClientRect: () => ({{ top: 0, height: 0 }}) }};
    const picked = sc.pickActivePage(stageEl, new Map());
    console.log(JSON.stringify({{ picked }}));
    """
    out = _run_node(script)
    assert out["picked"] == -1


def test_compute_fit_zoom_handles_heterogeneous_pages() -> None:
    """R1 fix (cross-verify §4): a page with non-standard width must get
    its own fit computation. Demonstrates viewMode + per-page width
    independence."""
    script = f"""
    const {{ computeFitZoom }} = await import("{VIEWPORT.as_uri()}");
    // Page 1: letter (612pt @ scale 2.78)
    const small = computeFitZoom({{
        pageWidthPt: 612, scale: 2.78, stageWidthPx: 1400, viewMode: "translation"
    }});
    // Page 2: A3 (1191pt @ scale 2.78) — fit should be much smaller.
    const large = computeFitZoom({{
        pageWidthPt: 1191, scale: 2.78, stageWidthPx: 1400, viewMode: "translation"
    }});
    console.log(JSON.stringify({{ small, large }}));
    """
    out = _run_node(script)
    # Larger page fits a smaller zoom — proves per-page metadata matters.
    assert out["small"] >= out["large"], (
        f"small page should fit larger zoom than A3-sized page: "
        f"small={out['small']} large={out['large']}"
    )
