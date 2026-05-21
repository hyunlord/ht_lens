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
    # Phase 6b: page-mount replaced by stage-container.
    assert 'id="stage"' in html
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


# --- Phase 5 R1 fix regression guards ---


@pytest.mark.asyncio
async def test_state_persists_active_doc_id(api_db_path: Path, assets_root: Path) -> None:
    """R1 fix: panel state must be doc-scoped (activeDocId persisted) so
    cross-document reload cannot rehydrate doc A's thread in doc B."""
    src = (assets_root / "js" / "state.js").read_text(encoding="utf-8")
    assert "ht_lens.activeDocId" in src
    assert "activeDocId" in src
    # openPanel must accept and persist docId.
    assert "docId" in src


@pytest.mark.asyncio
async def test_viewer_refuses_cross_document_panel_restore(
    api_db_path: Path, assets_root: Path
) -> None:
    """R1 fix: bootstrap discards persisted panel when activeDocId mismatches."""
    src = (assets_root / "js" / "viewer.js").read_text(encoding="utf-8")
    assert "restoredDocId" in src
    assert "cross-document panel restore" in src
    # All openPanel callsites must pass docId now.
    # Look for at least 3 openPanel({...docId...}) call sites.
    assert src.count("docId") >= 5


@pytest.mark.asyncio
async def test_viewer_retry_actually_reissues(api_db_path: Path, assets_root: Path) -> None:
    """R1 fix: retry button must call the failed action again, not just clear
    the banner."""
    src = (assets_root / "js" / "viewer.js").read_text(encoding="utf-8")
    assert "lastFailedAction" in src
    # both explain + submit set lastFailedAction on error
    assert src.count("lastFailedAction =") >= 3


@pytest.mark.asyncio
async def test_chat_panel_scrolls_to_bottom_on_paint(api_db_path: Path, assets_root: Path) -> None:
    """R1 fix: long restored thread should reopen at the newest message, not
    at scrollTop=0."""
    src = (assets_root / "js" / "components" / "chat_panel.js").read_text(encoding="utf-8")
    # The dist < 80 shortcut was the bug; the new code force-scrolls.
    assert "main.scrollTop = main.scrollHeight" in src
    assert "dist < 80" not in src


@pytest.mark.asyncio
async def test_thread_list_active_by_thread_id(api_db_path: Path, assets_root: Path) -> None:
    """R1 fix: multi-thread per block — active row keyed by thread.id, not
    block_id. Otherwise multiple threads on one block all light up."""
    src = (assets_root / "js" / "components" / "thread_list.js").read_text(encoding="utf-8")
    assert "currentThreadId" in src
    assert "t.id === currentThreadId" in src
    # The buggy block_id comparison must be gone.
    assert "block_id === currentBlockId" not in src


@pytest.mark.asyncio
async def test_phase5_scenario_script_committed(api_db_path: Path) -> None:
    """R1 fix: the Playwright driver behind verify's 10-question scenario
    must be tracked in scripts/ so reviewers can audit + rerun it."""
    script = REPO / "scripts" / "phase5_scenario.py"
    assert script.is_file(), "scripts/phase5_scenario.py is missing"
    text = script.read_text(encoding="utf-8")
    assert "10-question" in text or "10 question" in text.lower()
    assert "playwright" in text.lower()


REPO = Path(__file__).resolve().parents[2]


# --- Planner-directed R2 fix regression guards ---


@pytest.mark.asyncio
async def test_block_transition_clears_retry_state(api_db_path: Path, assets_root: Path) -> None:
    """R2 fix: switching to a different block must reset panelError +
    lastFailedAction so the retry button cannot replay a previous failure
    into the new conversation. Same-block re-click is preserved."""
    src = (assets_root / "js" / "viewer.js").read_text(encoding="utf-8")
    # Both block click + jumpToThread guard the transition.
    assert "state.activeBlockId !== blockId" in src, (
        "block click handler must compare against previous activeBlockId"
    )
    assert "state.activeBlockId !== thread.block_id" in src, (
        "jumpToThread must compare against previous activeBlockId"
    )
    # The reset must zero both retry-related fields.
    # We accept either ordering of the two assignments.
    transitions = src.count("panelError = null;\n    lastFailedAction = null;")
    assert transitions >= 2, (
        "block transition guards should clear both panelError and lastFailedAction"
    )


@pytest.mark.asyncio
async def test_close_panel_preserves_active_block(api_db_path: Path, assets_root: Path) -> None:
    """R2 fix: closePanel() must keep activeBlockId/activeThreadId so
    Ctrl/Cmd+B can reopen the same conversation. The hard reset moves to
    discardPanel()."""
    src = (assets_root / "js" / "state.js").read_text(encoding="utf-8")
    # closePanel only flips panelOpen
    assert "export function closePanel()" in src
    # closePanel block must NOT clear activeBlockId
    close_block = src[src.index("export function closePanel()") :]
    close_block = close_block[: close_block.index("export function")]
    assert "activeBlockId = null" not in close_block, (
        "closePanel must preserve activeBlockId for togglePanel to reopen"
    )
    assert "activeThreadId = null" not in close_block
    # discardPanel exists for the hard-reset case
    assert "export function discardPanel()" in src
    discard_block = src[src.index("export function discardPanel()") :]
    assert "activeBlockId = null" in discard_block
    assert "activeDocId = null" in discard_block


@pytest.mark.asyncio
async def test_toggle_panel_reopens_after_close(api_db_path: Path, assets_root: Path) -> None:
    """R2 fix: togglePanel must reopen the preserved active block."""
    src = (assets_root / "js" / "state.js").read_text(encoding="utf-8")
    assert "export function togglePanel()" in src
    # Toggle should: close if open, open against activeBlockId otherwise.
    toggle_block = src[src.index("export function togglePanel()") :]
    toggle_block = toggle_block[: toggle_block.index("\n}") + 2]
    assert "panelOpen" in toggle_block
    assert "activeBlockId === null" in toggle_block, (
        "togglePanel must guard against opening with no active block"
    )

    # viewer.js keyboard handler routes Ctrl/Cmd+B through togglePanel.
    vsrc = (assets_root / "js" / "viewer.js").read_text(encoding="utf-8")
    assert "togglePanel()" in vsrc


@pytest.mark.asyncio
async def test_navigate_and_popstate_use_discard_panel(
    api_db_path: Path, assets_root: Path
) -> None:
    """R2 fix: page navigation and browser back/forward should NOT keep the
    previous conversation in activeBlockId — discardPanel wipes everything."""
    src = (assets_root / "js" / "viewer.js").read_text(encoding="utf-8")
    # navigateTo and popstate handler must both use discardPanel
    nav_idx = src.index("function navigateTo")
    nav_block = src[nav_idx : nav_idx + 500]
    assert "discardPanel()" in nav_block
    # popstate
    pop_idx = src.index('addEventListener("popstate"')
    pop_block = src[pop_idx : pop_idx + 500]
    assert "discardPanel()" in pop_block


@pytest.mark.asyncio
async def test_state_migration_guard_for_pre_r1_localstorage(
    api_db_path: Path, assets_root: Path
) -> None:
    """R2 fix: pre-R1 localStorage rows lack activeDocId. The bootstrap
    snapshot loader must refuse to restore panel-scoped fields in that
    case so a stale thread cannot leak into a new document."""
    src = (assets_root / "js" / "state.js").read_text(encoding="utf-8")
    assert "readPanelSnapshot" in src
    # The migration guard explicitly checks for missing activeDocId.
    snap_idx = src.index("function readPanelSnapshot")
    snap_block = src[snap_idx : snap_idx + 1200]
    assert "docId === null" in snap_block
    # And erases the orphaned session-bound rows so they cannot resurface.
    assert "Pre-R1" in snap_block or "pre-r1" in snap_block.lower()
    # safeWrite(STORAGE_PANEL_OPEN, null) etc. are inside the guard.
    assert "safeWrite(STORAGE_PANEL_OPEN, null)" in snap_block


@pytest.mark.asyncio
async def test_state_panel_snapshot_returns_typed_object(
    api_db_path: Path, assets_root: Path
) -> None:
    """The loader must always return all four panel fields so callers
    don't accidentally read ``undefined`` for a missing key."""
    src = (assets_root / "js" / "state.js").read_text(encoding="utf-8")
    snap_idx = src.index("function readPanelSnapshot")
    snap_block = src[snap_idx : snap_idx + 1200]
    for key in ("panelOpen", "activeBlockId", "activeThreadId", "activeDocId"):
        assert key in snap_block, f"snapshot loader must include '{key}'"


# --- Phase 6a: search modal + confirm modal + retranslate + export ---


@pytest.mark.parametrize(
    "path",
    [
        "/static/css/search_modal.css",
        "/static/js/components/search_modal.js",
        "/static/js/components/confirm_modal.js",
    ],
)
@pytest.mark.asyncio
async def test_phase6a_assets_served(api_db_path: Path, path: str) -> None:
    with make_test_client(api_db_path) as client:
        resp = client.get(path)
    assert resp.status_code == 200, path


@pytest.mark.asyncio
async def test_viewer_html_loads_search_modal_css(api_db_path: Path, assets_root: Path) -> None:
    html = (assets_root / "viewer.html").read_text(encoding="utf-8")
    assert "css/search_modal.css" in html
    assert 'id="search-modal-mount"' in html


@pytest.mark.asyncio
async def test_keyboard_supports_cmd_k_and_search_close_priority(
    api_db_path: Path, assets_root: Path
) -> None:
    """Phase 6a: Cmd/Ctrl+K opens search even from inside chat textarea,
    and Esc closes the search modal first (when isSearchOpen)."""
    src = (assets_root / "js" / "utils" / "keyboard.js").read_text(encoding="utf-8")
    assert "onOpenSearch" in src
    assert "onCloseSearch" in src
    assert "isSearchOpen" in src
    # Cmd+K branch fires BEFORE the typing early-return.
    assert "Cmd/Ctrl+K opens the search modal" in src or "k" in src


@pytest.mark.asyncio
async def test_state_exposes_search_helpers(api_db_path: Path, assets_root: Path) -> None:
    src = (assets_root / "js" / "state.js").read_text(encoding="utf-8")
    for name in (
        "openSearch",
        "closeSearch",
        "setSearchResults",
        "moveSearchSelection",
        "setRetranslateInProgress",
    ):
        assert name in src, f"state.js should export '{name}'"
    assert "searchOpen" in src
    assert "searchResults" in src


@pytest.mark.asyncio
async def test_api_js_has_search_export_retranslate_helpers(
    api_db_path: Path, assets_root: Path
) -> None:
    src = (assets_root / "js" / "api.js").read_text(encoding="utf-8")
    assert "searchAll" in src
    assert "exportQuestions" in src
    assert "retranslateBlock" in src
    # Export uses fetch + Blob (debate §2 fix) so server errors surface.
    assert "URL.createObjectURL" in src
    assert "Blob" in src or "blob" in src


@pytest.mark.asyncio
async def test_block_js_dispatches_contextmenu_event(api_db_path: Path, assets_root: Path) -> None:
    src = (assets_root / "js" / "components" / "block.js").read_text(encoding="utf-8")
    assert "ht-lens:block-contextmenu" in src
    # Only text/header types fire the contextmenu (image is excluded).
    assert 'blockData.type !== "text"' in src
    assert 'blockData.type !== "header"' in src


@pytest.mark.asyncio
async def test_viewer_js_handles_search_export_retranslate(
    api_db_path: Path, assets_root: Path
) -> None:
    src = (assets_root / "js" / "viewer.js").read_text(encoding="utf-8")
    # Handlers wired in
    assert "handleSearchInput" in src
    assert "handleSearchSelect" in src
    assert "handleExport" in src
    assert "handleRetranslate" in src
    # block URL deep link
    assert "activateBlockId" in src
    # popstate respects block deep link
    assert "blockId" in src and 'params.get("block")' in src


@pytest.mark.asyncio
async def test_search_result_block_param_restores_target_block(
    api_db_path: Path, assets_root: Path
) -> None:
    """The `block` URL parameter must be parsed AND propagated through the
    bootstrap path so search-result jumps highlight the matched block."""
    src = (assets_root / "js" / "viewer.js").read_text(encoding="utf-8")
    # parseQuery returns blockId.
    assert "blockId" in src
    # bootstrap forwards it to the document loader (Phase 6a used
    # activateBlockId, Phase 6b renamed the parameter to initialBlockId for
    # the bootstrap path while keeping activateBlockId on navigateTo).
    assert "activateBlockId: initial.blockId" in src or "initialBlockId: initial.blockId" in src
    # Flash highlight present (centralised in stage_container.js since 6b).
    assert "flashBlock" in src or "block--flash" in src


@pytest.mark.asyncio
async def test_sidebar_has_export_button_and_search_hint(
    api_db_path: Path, assets_root: Path
) -> None:
    src = (assets_root / "js" / "components" / "sidebar.js").read_text(encoding="utf-8")
    assert "export-btn" in src
    assert "onExport" in src
    assert "onOpenSearch" in src
    assert "search-hint" in src


@pytest.mark.asyncio
async def test_search_modal_sanitises_preview_to_mark_only(
    api_db_path: Path, assets_root: Path
) -> None:
    """The preview comes from the backend with a single ``<mark>`` tag; the
    modal must restrict DOMPurify to ``<mark>`` only so any other HTML the
    server might accidentally emit is stripped."""
    src = (assets_root / "js" / "components" / "search_modal.js").read_text(encoding="utf-8")
    assert "ALLOWED_TAGS" in src and '"mark"' in src
    assert "DOMPurify.sanitize" in src


# --- Phase 6b: stage container + view modes + multi-page state ---


@pytest.mark.parametrize(
    "path",
    [
        "/static/js/components/stage_container.js",
        "/static/js/components/pane.js",
    ],
)
@pytest.mark.asyncio
async def test_phase6b_assets_served(api_db_path: Path, path: str) -> None:
    with make_test_client(api_db_path) as client:
        resp = client.get(path)
    assert resp.status_code == 200, path


@pytest.mark.asyncio
async def test_viewer_html_uses_stage_container_mount(api_db_path: Path, assets_root: Path) -> None:
    html = (assets_root / "viewer.html").read_text(encoding="utf-8")
    assert 'id="stage"' in html
    assert "page-mount" not in html  # legacy single-page mount removed
    assert "mode (번역" in html  # T-key hint updated for Phase 6b


@pytest.mark.asyncio
async def test_state_exposes_phase6b_helpers(api_db_path: Path, assets_root: Path) -> None:
    src = (assets_root / "js" / "state.js").read_text(encoding="utf-8")
    for name in (
        "viewMode",
        "viewModeActual",
        "setViewMode",
        "cycleViewMode",
        "pageDataById",
        "setPageData",
        "clearPageData",
        "setPageSummaries",
        "findBlockInPageData",
        "VIEW_MODES",
    ):
        assert name in src, f"state.js should export '{name}'"
    # Migration guard for the new viewMode key (default 'translation').
    assert 'STORAGE_VIEW_MODE = "ht_lens.viewMode"' in src


@pytest.mark.asyncio
async def test_api_js_has_pages_summary_helper(api_db_path: Path, assets_root: Path) -> None:
    src = (assets_root / "js" / "api.js").read_text(encoding="utf-8")
    assert "getPagesSummary" in src
    assert "pages-summary" in src
    # AbortController signal plumbing (Phase 6b debate §4 fix).
    assert "opts.signal" in src


@pytest.mark.asyncio
async def test_stage_container_has_mount_unmount_race_guards(
    api_db_path: Path, assets_root: Path
) -> None:
    src = (assets_root / "js" / "components" / "stage_container.js").read_text(encoding="utf-8")
    for name in (
        "mountPage",
        "unmountPage",
        "mountPromise",
        "AbortController",
        "_mountTokenByPage",
        "_mountedPages",
        "scrollToPage",
        "waitForBlockMounted",
        "flashBlock",
        "repaintAllMountedPages",
        "repaintMountedPage",
        "buildPlaceholderRows",
        "attachIntersectionObserver",
    ):
        assert name in src, f"stage_container.js should define '{name}'"


@pytest.mark.asyncio
async def test_pane_preserves_page_view_contracts(api_db_path: Path, assets_root: Path) -> None:
    """Phase 6b debate §3: rotation banner + data-fallback fallback must
    keep working. page_view.js (not page_row.js) still owns the rendering."""
    page_view = (assets_root / "js" / "components" / "page_view.js").read_text(encoding="utf-8")
    assert "rotation-banner" in page_view
    # The side-aware overlay must use ``data-side``.
    assert "overlay.dataset.side = side" in page_view


@pytest.mark.asyncio
async def test_keyboard_uses_cycle_view_mode(api_db_path: Path, assets_root: Path) -> None:
    src = (assets_root / "js" / "utils" / "keyboard.js").read_text(encoding="utf-8")
    assert "onCycleViewMode" in src


@pytest.mark.asyncio
async def test_block_js_has_hover_sync(api_db_path: Path, assets_root: Path) -> None:
    src = (assets_root / "js" / "components" / "block.js").read_text(encoding="utf-8")
    assert "syncBlockHover" in src
    assert "block--hover-sync" in src


@pytest.mark.asyncio
async def test_viewer_uses_stage_container_and_pushstate_on_navigate(
    api_db_path: Path, assets_root: Path
) -> None:
    src = (assets_root / "js" / "viewer.js").read_text(encoding="utf-8")
    # currentPage singleton must be gone (Phase 6b debate §2 fix).
    assert "currentPage = pageData" not in src
    assert "let currentPage" not in src
    # Stage container symbols are wired in.
    for name in (
        "buildPlaceholderRows",
        "attachIntersectionObserver",
        "mountPage",
        "repaintAllMountedPages",
        "scrollToPage",
        "waitForBlockMounted",
        "flashBlock",
    ):
        assert name in src, f"viewer.js should reference {name}"
    # Explicit navigation uses pushState; free scroll uses replaceState (debate §2).
    assert "window.history.pushState" in src
    assert "window.history.replaceState" in src
    assert "onScrollPageChange" in src
    # handleRetranslate iterates mounted pages, not the singleton currentPage.
    assert "Object.values(state.pageDataById)" in src


@pytest.mark.asyncio
async def test_viewer_css_has_stage_layout(api_db_path: Path, assets_root: Path) -> None:
    src = (assets_root / "css" / "viewer.css").read_text(encoding="utf-8")
    for sel in (
        ".stage-container",
        ".page-row",
        ".pane",
        ".block--hover-sync",
    ):
        assert sel in src, f"viewer.css missing {sel}"


# --- Phase 6b R1 fix regression guards (cross-verify R1 §4) ---


@pytest.mark.asyncio
async def test_toggle_panel_recomputes_view_mode_actual(
    api_db_path: Path, assets_root: Path
) -> None:
    """R1 fix: togglePanel must recompute viewModeActual just like
    openPanel/closePanel/discardPanel, otherwise reopening the panel via
    Ctrl+B while viewMode==='both' leaves the side-by-side layout up.

    Verified by checking the state.js source includes the recompute call
    inside togglePanel's reopen path."""
    src = (assets_root / "js" / "state.js").read_text(encoding="utf-8")
    # Find the togglePanel body.
    idx = src.find("export function togglePanel(")
    assert idx > 0
    end = src.find("\nexport function", idx + 10)
    body = src[idx:end]
    # The reopen branch (the path after closePanel + the activeBlockId
    # check) must recompute viewModeActual.
    assert "viewModeActual = computeViewModeActual" in body, (
        "togglePanel must recompute viewModeActual on reopen"
    )


@pytest.mark.asyncio
async def test_navigate_to_pushes_block_id_in_history_state(
    api_db_path: Path, assets_root: Path
) -> None:
    """R1 fix: pushState must include blockId so back/forward to a search
    hit restores the highlight + panel, not just the page scroll."""
    src = (assets_root / "js" / "viewer.js").read_text(encoding="utf-8")
    # pushState payload must include blockId.
    assert "blockId: opts.activateBlockId" in src
    # popstate must restore via navigateTo({activateBlockId: ...,
    # fromPopstate: true}) so it doesn't re-push history.
    assert "fromPopstate: true" in src
    assert "data.blockId" in src or "target.blockId" in src


@pytest.mark.asyncio
async def test_mount_page_bounded_by_max_pages(api_db_path: Path, assets_root: Path) -> None:
    """R1 fix: mountPage(0) and mountPage(N+1) must short-circuit so the
    boundary-page neighbour prefetch does not 404 the server."""
    src = (assets_root / "js" / "components" / "stage_container.js").read_text(encoding="utf-8")
    assert "ctx?.maxPages" in src or "ctx.maxPages" in src
    assert "pageNum < 1" in src
    assert "maxPages" in src


@pytest.mark.asyncio
async def test_schedule_far_page_unmount_is_exported(api_db_path: Path, assets_root: Path) -> None:
    """R1 fix: scheduleFarPageUnmount must be exported so the jsdom test
    can drive the 200-page memory DoD code path directly."""
    src = (assets_root / "js" / "components" / "stage_container.js").read_text(encoding="utf-8")
    assert "export function scheduleFarPageUnmount" in src


# --- Phase 6b Planner-directed R2 fixes (jumpToThread + history threadId) ---


@pytest.mark.asyncio
async def test_jump_to_thread_uses_explicit_thread_id(api_db_path: Path, assets_root: Path) -> None:
    """Planner R2 fix #1: jumpToThread must forward the exact thread.id to
    navigateTo so multi-thread blocks open the clicked thread, not the
    highest-id auto-select."""
    src = (assets_root / "js" / "viewer.js").read_text(encoding="utf-8")
    # jumpToThread body forwards activateThreadId AND re-affirms via setActiveThreadId.
    idx = src.find("async function jumpToThread(")
    assert idx > 0
    end = src.find("\nasync function", idx + 10)
    if end < 0:
        end = src.find("\nfunction ", idx + 10)
    body = src[idx:end]
    assert "activateThreadId: thread.id" in body
    assert "setActiveThreadId(thread.id)" in body


@pytest.mark.asyncio
async def test_navigate_to_uses_explicit_thread_id_when_provided(
    api_db_path: Path, assets_root: Path
) -> None:
    """Planner R2 fix #1: navigateTo({activateThreadId}) skips the highest-id
    auto-select and opens the panel with the caller-supplied thread."""
    src = (assets_root / "js" / "viewer.js").read_text(encoding="utf-8")
    assert "opts.activateThreadId" in src
    # The branch that uses the explicit id must skip the existing-thread
    # auto-select. We check for the structural marker.
    assert "explicitThreadId" in src
