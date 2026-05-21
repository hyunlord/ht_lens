"""Phase 4 — static viewer asset serving + integrity checks."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from ._api_helpers import make_test_client


@pytest.fixture
def assets_root() -> Path:
    from ht_lens.api import app as app_module

    return Path(app_module.__file__).resolve().parent / "static"


# --- core mount: each Phase 4 asset is reachable + right content-type ---


@pytest.mark.parametrize(
    ("path", "mime_prefix"),
    [
        ("/static/index.html", "text/html"),
        ("/static/viewer.html", "text/html"),
        ("/static/css/base.css", "text/css"),
        ("/static/css/viewer.css", "text/css"),
        ("/static/js/api.js", "javascript"),
        ("/static/js/state.js", "javascript"),
        ("/static/js/index.js", "javascript"),
        ("/static/js/viewer.js", "javascript"),
        ("/static/js/components/page_view.js", "javascript"),
        ("/static/js/components/block.js", "javascript"),
        ("/static/js/components/sidebar.js", "javascript"),
        ("/static/js/utils/font_fit.js", "javascript"),
        ("/static/js/utils/keyboard.js", "javascript"),
    ],
)
@pytest.mark.asyncio
async def test_static_asset_served(api_db_path: Path, path: str, mime_prefix: str) -> None:
    with make_test_client(api_db_path) as client:
        resp = client.get(path)
    assert resp.status_code == 200, path
    assert mime_prefix in resp.headers["content-type"], (
        f"{path} content-type={resp.headers['content-type']}"
    )


@pytest.mark.asyncio
async def test_static_gitkeep_still_served(api_db_path: Path) -> None:
    """Phase 3 regression guard — adding files shouldn't break the marker."""
    with make_test_client(api_db_path) as client:
        resp = client.get("/static/.gitkeep")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_static_unknown_path_returns_404(api_db_path: Path) -> None:
    with make_test_client(api_db_path) as client:
        resp = client.get("/static/does-not-exist.html")
    assert resp.status_code == 404


# --- referenced-asset integrity: <script src> + <link href> must resolve ---

_HREF_RE = re.compile(r'<(?:link|script)[^>]+(?:href|src)\s*=\s*"([^"]+)"', re.IGNORECASE)


def _extract_refs(html: str) -> list[str]:
    return _HREF_RE.findall(html)


@pytest.mark.asyncio
async def test_index_html_references_resolvable_assets(
    api_db_path: Path, assets_root: Path
) -> None:
    html = (assets_root / "index.html").read_text(encoding="utf-8")
    refs = _extract_refs(html)
    assert refs, "index.html should reference at least one CSS/JS asset"
    with make_test_client(api_db_path) as client:
        for ref in refs:
            url = ref if ref.startswith("/") else f"/static/{ref}"
            resp = client.get(url)
            assert resp.status_code == 200, f"missing referenced asset {ref}"


@pytest.mark.asyncio
async def test_viewer_html_references_resolvable_assets(
    api_db_path: Path, assets_root: Path
) -> None:
    html = (assets_root / "viewer.html").read_text(encoding="utf-8")
    refs = _extract_refs(html)
    assert refs, "viewer.html should reference at least one CSS/JS asset"
    with make_test_client(api_db_path) as client:
        for ref in refs:
            url = ref if ref.startswith("/") else f"/static/{ref}"
            resp = client.get(url)
            assert resp.status_code == 200, f"missing referenced asset {ref}"


# --- HTML hooks: each entry-point page wires up the right script + structure ---


@pytest.mark.asyncio
async def test_index_html_has_doc_card_grid(api_db_path: Path) -> None:
    with make_test_client(api_db_path) as client:
        html = client.get("/static/index.html").text
    assert 'class="doc-card-grid"' in html
    assert 'src="js/index.js"' in html


@pytest.mark.asyncio
async def test_viewer_html_has_required_mount_points(api_db_path: Path) -> None:
    with make_test_client(api_db_path) as client:
        html = client.get("/static/viewer.html").text
    assert 'class="sidebar"' in html
    assert 'id="page-mount"' in html
    assert 'src="js/viewer.js"' in html


# --- static JS contract markers (we can't run JS in pytest; grep instead) ---


@pytest.mark.asyncio
async def test_index_js_has_empty_state_marker(api_db_path: Path, assets_root: Path) -> None:
    src = (assets_root / "js" / "index.js").read_text(encoding="utf-8")
    assert "no documents yet" in src, (
        "index.js should show a friendly empty state when /documents is []"
    )


@pytest.mark.asyncio
async def test_viewer_js_clamps_query_and_handles_404(api_db_path: Path, assets_root: Path) -> None:
    src = (assets_root / "js" / "viewer.js").read_text(encoding="utf-8")
    # clamp logic: viewer should bound `page` into [1, num_pages]
    assert "Math.max(1" in src and "Math.min(doc.num_pages" in src, (
        "viewer.js should clamp the URL page into [1, num_pages]"
    )
    # 404 path
    assert "err.status === 404" in src
    # history pushState (Phase 4 challenge revision §1)
    assert "history.pushState" in src
    assert "popstate" in src


@pytest.mark.asyncio
async def test_block_js_rejects_invalid_bbox(api_db_path: Path, assets_root: Path) -> None:
    src = (assets_root / "js" / "components" / "block.js").read_text(encoding="utf-8")
    # bbox sanitization markers (Phase 4 challenge revision §3)
    for marker in [
        "not a 4-tuple",
        "not finite",
        "not positive",
        "outside page",
    ]:
        assert marker in src, f"block.js should warn on '{marker}'"


@pytest.mark.asyncio
async def test_page_view_handles_rotation(api_db_path: Path, assets_root: Path) -> None:
    src = (assets_root / "js" / "components" / "page_view.js").read_text(encoding="utf-8")
    assert "rotation" in src and "rotation-banner" in src, (
        "page_view should warn on rotated pages instead of mis-aligning blocks"
    )


# --- RE-CODE round 1 regression guards ---


@pytest.mark.asyncio
async def test_viewer_clears_dom_on_error(api_db_path: Path, assets_root: Path) -> None:
    """R1 fix: 404/error path must wipe stale page-mount + sidebar content."""
    src = (assets_root / "js" / "viewer.js").read_text(encoding="utf-8")
    assert "clearViewerDom" in src, "viewer.js should define clearViewerDom()"
    # Error handler must call clearViewerDom before showing the banner.
    catch_idx = src.find("} catch (err)")
    assert catch_idx > 0
    assert "clearViewerDom()" in src[catch_idx:], "viewer.js catch block must wipe stale viewer DOM"


@pytest.mark.asyncio
async def test_viewer_navigation_token_cancels_stale_responses(
    api_db_path: Path, assets_root: Path
) -> None:
    """R1 fix: rapid prev/next must not let an older response paint on top."""
    src = (assets_root / "js" / "viewer.js").read_text(encoding="utf-8")
    assert "navToken" in src, "viewer.js should track a navigation token"
    # Token must be checked at least twice (after each await).
    assert src.count("token !== navToken") >= 2, (
        "viewer.js should re-check navToken after every async boundary"
    )


@pytest.mark.asyncio
async def test_overlay_data_mode_set_by_page_view(api_db_path: Path, assets_root: Path) -> None:
    """R1 fix: CSS targets ``.overlay[data-mode='...']`` to keep the original
    mode visually clean. page_view.js must actually set that attribute."""
    pv = (assets_root / "js" / "components" / "page_view.js").read_text(encoding="utf-8")
    assert "dataset.mode" in pv, "page_view.js should set overlay.dataset.mode"
    css = (assets_root / "css" / "viewer.css").read_text(encoding="utf-8")
    assert "overlay[data-mode='translation']" in css
    assert "overlay[data-mode='original']" in css


@pytest.mark.asyncio
async def test_state_snaps_zoom_on_init(api_db_path: Path, assets_root: Path) -> None:
    """R1 fix: a stale localStorage zoom value must be snapped to a step
    before first render, not used as-is."""
    src = (assets_root / "js" / "state.js").read_text(encoding="utf-8")
    assert "snapToStep" in src
    # The initial state.zoom must go through snapToStep.
    assert "zoom: snapToStep(" in src, "state.zoom on init must be snapped to ZOOM_STEPS"


# --- Planner-directed R2 follow-up: status labels in index.js, opacity ---


@pytest.mark.asyncio
async def test_index_js_has_status_labels(api_db_path: Path, assets_root: Path) -> None:
    """index.js must label Document.status (R2 fix) instead of rendering raw."""
    src = (assets_root / "js" / "index.js").read_text(encoding="utf-8")
    assert "STATUS_LABELS" in src, "index.js should map raw status values to labels"
    for raw_key in (
        "ready_for_translation",
        "translating",
        "translated",
        "partial_translated",
        "failed",
    ):
        assert raw_key in src, f"status key '{raw_key}' missing from labels"


@pytest.mark.asyncio
async def test_viewer_css_has_status_tag_styles(api_db_path: Path, assets_root: Path) -> None:
    src = (assets_root / "css" / "viewer.css").read_text(encoding="utf-8")
    for cls in (
        "status--pending",
        "status--running",
        "status--ok",
        "status--partial",
        "status--failed",
    ):
        assert cls in src, f"status class '{cls}' missing from viewer.css"


@pytest.mark.asyncio
async def test_viewer_css_translation_opacity_raised(api_db_path: Path, assets_root: Path) -> None:
    """R2 fix: translation panel opacity should be raised to reduce source
    text bleed-through. We require ``alpha >= 0.9``."""
    src = (assets_root / "css" / "viewer.css").read_text(encoding="utf-8")
    match = re.search(
        r"overlay\[data-mode='translation'\][^{]*\{[^}]*?background:\s*rgba\(\s*\d+\s*,\s*\d+\s*,\s*\d+\s*,\s*([0-9.]+)\s*\)",
        src,
        re.DOTALL,
    )
    assert match is not None, "translation panel rgba not found"
    alpha = float(match.group(1))
    assert alpha >= 0.9, f"translation panel opacity {alpha} should be >= 0.9"


# --- Phase 5: vendor + chat panel + pins + sidebar tabs ---


@pytest.mark.parametrize(
    "path",
    [
        "/static/vendor/marked.esm.js",
        "/static/vendor/purify.es.mjs",
        "/static/vendor/LICENSE",
        "/static/css/chat_panel.css",
        "/static/js/utils/render_markdown.js",
        "/static/js/components/chat_panel.js",
        "/static/js/components/message.js",
        "/static/js/components/message_input.js",
        "/static/js/components/thread_list.js",
    ],
)
@pytest.mark.asyncio
async def test_phase5_assets_served(api_db_path: Path, path: str) -> None:
    with make_test_client(api_db_path) as client:
        resp = client.get(path)
    assert resp.status_code == 200, path


@pytest.mark.asyncio
async def test_render_markdown_uses_dompurify_hook(api_db_path: Path, assets_root: Path) -> None:
    src = (assets_root / "js" / "utils" / "render_markdown.js").read_text(encoding="utf-8")
    assert "DOMPurify" in src
    assert "addHook" in src
    assert "target" in src and "noopener" in src
    # marked is imported from vendor ESM bundle
    assert "marked.esm.js" in src
    assert "purify.es.mjs" in src


@pytest.mark.asyncio
async def test_block_js_dispatches_custom_event_and_supports_multi_thread(
    api_db_path: Path, assets_root: Path
) -> None:
    src = (assets_root / "js" / "components" / "block.js").read_text(encoding="utf-8")
    # Phase 5 click is now a CustomEvent so the panel owner can listen
    assert "ht-lens:block-click" in src
    assert "CustomEvent" in src
    # Multi-thread per block: pin uses array + count attribute
    assert "threadsForBlock" in src
    assert "data-thread-count" in src or "threadCount" in src
    # Has-thread attribute drives the pin CSS
    assert "hasThread" in src or "data-has-thread" in src


@pytest.mark.asyncio
async def test_viewer_js_uses_refetch_pattern_for_threads(
    api_db_path: Path, assets_root: Path
) -> None:
    src = (assets_root / "js" / "viewer.js").read_text(encoding="utf-8")
    # Refetch pattern: write -> getThreadDetail
    assert "getThreadDetail" in src
    assert "ensureThreadDetail" in src
    # Doc-wide thread list refresh after creates/writes
    assert "listThreadsForDoc" in src
    # panelToken async cancellation (R1 fix extension into chat ops)
    assert "panelToken" in src
    # Esc handler hook is wired
    assert "onClosePanel" in src


@pytest.mark.asyncio
async def test_state_persists_active_thread_and_panel(api_db_path: Path, assets_root: Path) -> None:
    """Phase 5 R1 fix: panel open state + activeThreadId must be persisted to
    localStorage so reload restores the chat."""
    src = (assets_root / "js" / "state.js").read_text(encoding="utf-8")
    assert "ht_lens.panelOpen" in src
    assert "ht_lens.activeThreadId" in src
    assert "ht_lens.activeBlockId" in src
    assert "ht_lens.sidebarTab" in src


@pytest.mark.asyncio
async def test_viewer_html_loads_chat_panel_css(api_db_path: Path, assets_root: Path) -> None:
    html = (assets_root / "viewer.html").read_text(encoding="utf-8")
    assert "css/chat_panel.css" in html
    assert "right-slot" in html


@pytest.mark.asyncio
async def test_keyboard_handles_esc_and_ctrl_b(api_db_path: Path, assets_root: Path) -> None:
    src = (assets_root / "js" / "utils" / "keyboard.js").read_text(encoding="utf-8")
    assert "Escape" in src
    assert "onClosePanel" in src
    assert "onTogglePanel" in src
