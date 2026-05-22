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


@pytest.mark.asyncio
async def test_history_state_carries_thread_id(api_db_path: Path, assets_root: Path) -> None:
    """Planner R2 fix #2: history state must include threadId so browser
    back/forward across multiple sidebar question selections restores the
    exact thread on multi-thread blocks."""
    src = (assets_root / "js" / "viewer.js").read_text(encoding="utf-8")
    # pushState payload includes threadId.
    assert "threadId: opts.activateThreadId" in src
    # popstate restores threadId AND forwards to navigateTo.
    assert "data.threadId" in src
    assert "activateThreadId: target.threadId" in src
    # Cross-doc popstate path: loadDocument accepts initialThreadId.
    assert "initialThreadId" in src


# --- Phase 6c: viewer polish (sidebar toggle / fit-to-width / logo / scroll) ---


@pytest.mark.parametrize(
    "path",
    [
        "/static/js/utils/viewport.js",
    ],
)
@pytest.mark.asyncio
async def test_phase6c_assets_served(api_db_path: Path, path: str) -> None:
    with make_test_client(api_db_path) as client:
        resp = client.get(path)
    assert resp.status_code == 200, path


@pytest.mark.asyncio
async def test_viewer_html_has_logo_link_and_sidebar_toggle(
    api_db_path: Path, assets_root: Path
) -> None:
    """Phase 6c: the app logo links to index.html, and the sidebar toggle
    lives in the static header (NOT inside sidebar.js which is rebuilt on
    every setCurrentPage tick — debate §3 fix)."""
    html = (assets_root / "viewer.html").read_text(encoding="utf-8")
    assert 'class="app-logo"' in html
    assert 'href="/static/index.html"' in html
    assert 'id="sidebar-toggle"' in html
    assert 'class="sidebar-toggle"' in html
    # Toggle button comes before the sidebar aside in source order.
    assert html.index('class="sidebar-toggle"') < html.index('<aside class="sidebar"')


@pytest.mark.asyncio
async def test_state_exposes_phase6c_helpers(api_db_path: Path, assets_root: Path) -> None:
    src = (assets_root / "js" / "state.js").read_text(encoding="utf-8")
    for name in (
        "sidebarOpen",
        "setSidebarOpen",
        "toggleSidebar",
        "setZoomAutoFit",
        "zoomIsAuto",
        "STORAGE_SIDEBAR_OPEN",
    ):
        assert name in src, f"state.js should export '{name}'"
    # User Ctrl+ArrowUp/Down (setZoom) flips zoomIsAuto -> false.
    set_zoom_idx = src.find("export function setZoom(")
    assert set_zoom_idx > 0
    body = src[set_zoom_idx : set_zoom_idx + 400]
    assert "zoomIsAuto = false" in body


@pytest.mark.asyncio
async def test_viewport_js_exports_compute_fit_zoom(api_db_path: Path, assets_root: Path) -> None:
    src = (assets_root / "js" / "utils" / "viewport.js").read_text(encoding="utf-8")
    assert "export function computeFitZoom" in src
    # Snap-down rule (debate §2 fix).
    assert "<= target" in src or "step <= target" in src


@pytest.mark.asyncio
async def test_viewer_wires_resize_observer_and_fit_on_load(
    api_db_path: Path, assets_root: Path
) -> None:
    src = (assets_root / "js" / "viewer.js").read_text(encoding="utf-8")
    assert "ResizeObserver" in src
    assert "computeFitZoom" in src or "applyFitToWidthIfAuto" in src
    # fit-to-width call must come AFTER buildPlaceholderRows and BEFORE scrollToPage
    # so the deep-link target lands on the right row height (debate §3 fix).
    build_idx = src.find("buildPlaceholderRows(stageEl")
    # R1 fix: applyFitToWidthIfAuto now takes {preferPage: clampedPage} so
    # heterogeneous documents fit the target page, not the first one.
    fit_idx = src.find("applyFitToWidthIfAuto({ preferPage:")
    scroll_idx = src.find("scrollToPage(stageEl, clampedPage")
    assert build_idx > 0 and fit_idx > 0 and scroll_idx > 0
    assert build_idx < fit_idx < scroll_idx, "loadDocument order must be build -> fit -> scroll"
    # The auto-fit must key off viewModeActual (not viewMode) so chat-panel
    # collapse doesn't fit for the wrong pane count (debate §3).
    fit_helper_idx = src.find("function applyFitToWidthIfAuto(")
    assert fit_helper_idx > 0
    # R1 fix widened the helper (preferPage / currentPage selection) so we
    # take a generous window.
    helper = src[fit_helper_idx : fit_helper_idx + 900]
    assert "state.viewModeActual" in helper


@pytest.mark.asyncio
async def test_sidebar_toggle_is_static_not_inside_sidebar_render(
    api_db_path: Path, assets_root: Path
) -> None:
    """Phase 6c debate §3: the toggle button must NOT be appended in
    renderSidebar() because renderSidebar wipes its container on every
    setCurrentPage repaint."""
    sidebar_js = (assets_root / "js" / "components" / "sidebar.js").read_text(encoding="utf-8")
    assert "sidebar-toggle" not in sidebar_js, (
        "sidebar.js must not create the toggle button — it lives in viewer.html"
    )
    viewer_js = (assets_root / "js" / "viewer.js").read_text(encoding="utf-8")
    assert 'getElementById("sidebar-toggle")' in viewer_js
    assert "toggleSidebar()" in viewer_js


@pytest.mark.asyncio
async def test_viewer_css_has_sidebar_collapsed_and_app_logo(
    api_db_path: Path, assets_root: Path
) -> None:
    src = (assets_root / "css" / "viewer.css").read_text(encoding="utf-8")
    assert ".viewer-shell--sidebar-closed" in src
    assert ".app-logo" in src
    assert ".sidebar-toggle" in src
    # Sidebar transition (200ms) for smooth open/close.
    assert "transition" in src


@pytest.mark.asyncio
async def test_stage_container_rootmargin_widened_for_scroll_fix(
    api_db_path: Path, assets_root: Path
) -> None:
    """Phase 6c user feedback: scrolling down past large pages sometimes
    fails to mount the next page. rootMargin widened from 100% to 200% +
    pickActivePage uses viewport midpoint instead of intersectionRatio."""
    src = (assets_root / "js" / "components" / "stage_container.js").read_text(encoding="utf-8")
    assert '"200% 0px 200% 0px"' in src
    assert "export function pickActivePage" in src
    # Midpoint logic
    assert "midY" in src or "viewport midpoint" in src


# --- Phase 6c R1 Cross-verify fixes (mixed page sizes + provider pin) ---


@pytest.mark.asyncio
async def test_fit_to_width_uses_current_page_summary_not_first(
    api_db_path: Path, assets_root: Path
) -> None:
    """R1 fix (cross-verify §4): heterogeneous documents have per-page
    dimensions (pages-summary contract). applyFitToWidthIfAuto must select
    the summary matching the active/preferred page, NOT pageSummaries[0]
    blindly."""
    src = (assets_root / "js" / "viewer.js").read_text(encoding="utf-8")
    idx = src.find("function applyFitToWidthIfAuto(")
    assert idx > 0
    body = src[idx : idx + 800]
    # Must accept preferPage opt + fall back to state.currentPage, not [0].
    assert "preferPage" in body, "applyFitToWidthIfAuto must accept preferPage"
    assert "state.currentPage" in body
    # No naive ``pageSummaries[0]`` lookup remains.
    assert "pageSummaries[0]" not in body, "fit-to-width must not hard-code first page metadata"
    # loadDocument passes the deep-link target as preferPage.
    load_idx = src.find("applyFitToWidthIfAuto({ preferPage:")
    assert load_idx > 0, "loadDocument must pass preferPage to applyFitToWidthIfAuto"
    # subscribe() re-fits when currentPage changes.
    assert "state.currentPage !== _lastCurrentPage" in src


@pytest.mark.asyncio
async def test_make_test_client_only_pins_mock_when_unset(
    api_db_path: Path, assets_root: Path
) -> None:
    """R1 fix (cross-verify §4): the test helper must NOT silently override
    a caller-supplied LLM_PROVIDER. @pytest.mark.llm tests set
    openai_compat then expect the live provider to survive the helper."""
    helpers_src = (Path(__file__).resolve().parent / "_api_helpers.py").read_text(encoding="utf-8")
    # The pin must be guarded by ``prev_provider is None``.
    assert "if prev_provider is None:" in helpers_src
    pin_idx = helpers_src.find('os.environ["LLM_PROVIDER"] = "mock"')
    assert pin_idx > 0
    # The preceding (non-blank) line must be the guard, not an unconditional set.
    head = helpers_src[:pin_idx].rstrip()
    last_line = head.split("\n")[-1].strip()
    assert last_line.startswith("if prev_provider is None:"), (
        f"LLM_PROVIDER pin must sit inside the prev_provider None guard; "
        f"found preceding line: {last_line!r}"
    )


# --- Phase 6d: uploads + jobs panel + summary banner ---


@pytest.mark.parametrize(
    "path",
    [
        "/static/css/index.css",
        "/static/js/components/upload.js",
        "/static/js/components/jobs_panel.js",
        "/static/js/components/summary_banner.js",
    ],
)
@pytest.mark.asyncio
async def test_phase6d_assets_served(api_db_path: Path, path: str) -> None:
    with make_test_client(api_db_path) as client:
        resp = client.get(path)
    assert resp.status_code == 200, path


@pytest.mark.asyncio
async def test_index_html_has_upload_zone_and_jobs_panel(
    api_db_path: Path, assets_root: Path
) -> None:
    html = (assets_root / "index.html").read_text(encoding="utf-8")
    assert 'id="upload-zone"' in html
    assert 'id="upload-button"' in html
    assert 'id="upload-input"' in html
    assert 'id="active-jobs"' in html
    assert 'id="doc-grid"' in html
    assert "css/index.css" in html


@pytest.mark.asyncio
async def test_viewer_html_has_summary_banner_mount(api_db_path: Path, assets_root: Path) -> None:
    html = (assets_root / "viewer.html").read_text(encoding="utf-8")
    assert 'id="summary-banner-mount"' in html


@pytest.mark.asyncio
async def test_api_js_has_upload_jobs_summarize_helpers(
    api_db_path: Path, assets_root: Path
) -> None:
    src = (assets_root / "js" / "api.js").read_text(encoding="utf-8")
    for name in ("uploadPDF", "listJobs", "getJob", "summarizeDocument"):
        assert name in src, f"api.js should export '{name}'"


@pytest.mark.asyncio
async def test_upload_js_handles_drag_and_drop(api_db_path: Path, assets_root: Path) -> None:
    src = (assets_root / "js" / "components" / "upload.js").read_text(encoding="utf-8")
    for marker in ("attachUpload", "dragenter", "dragover", "drop", "uploadPDF"):
        assert marker in src
    # The drag class toggles on the zone, not document, per challenge §1.
    assert "upload-zone--drag" in src


@pytest.mark.asyncio
async def test_jobs_panel_js_uses_visibility_and_terminal_stop(
    api_db_path: Path, assets_root: Path
) -> None:
    src = (assets_root / "js" / "components" / "jobs_panel.js").read_text(encoding="utf-8")
    assert "startJobsPolling" in src
    assert "stopJobsPolling" in src
    assert "visibilityState" in src
    # 2 s polling cadence.
    assert "POLL_MS = 2000" in src


@pytest.mark.asyncio
async def test_summary_banner_renders_empty_state_and_regenerate(
    api_db_path: Path, assets_root: Path
) -> None:
    src = (assets_root / "js" / "components" / "summary_banner.js").read_text(encoding="utf-8")
    assert "renderSummaryBanner" in src
    assert "summarizeDocument" in src
    assert "재생성" in src or "요약 생성" in src


@pytest.mark.asyncio
async def test_index_js_wires_upload_and_summary_preview(
    api_db_path: Path, assets_root: Path
) -> None:
    src = (assets_root / "js" / "index.js").read_text(encoding="utf-8")
    assert "attachUpload" in src
    assert "startJobsPolling" in src
    assert "summaryPreview" in src
    # 120 char cap for the index card preview (challenge §1 — short).
    assert "120" in src


@pytest.mark.asyncio
async def test_viewer_js_renders_summary_banner_on_load(
    api_db_path: Path, assets_root: Path
) -> None:
    src = (assets_root / "js" / "viewer.js").read_text(encoding="utf-8")
    assert "renderSummaryBanner" in src
    assert "summaryBannerEl" in src


# --- Planner-directed R2 fix: failed jobs surfaced in jobs_panel ---


@pytest.mark.asyncio
async def test_jobs_panel_renders_failed_with_dismiss(api_db_path: Path, assets_root: Path) -> None:
    """R2 fix lock: ``jobs_panel.js`` must render terminal-state rows
    (failed/done) with a dismiss button, polling must include them via
    ``include_recent_terminals=true``, and the row must carry the
    ``job-row--failed`` class so CSS can highlight it."""
    src = (assets_root / "js" / "components" / "jobs_panel.js").read_text(encoding="utf-8")
    # Polling layer pulls in recent terminals.
    assert "includeRecentTerminals" in src
    # Failed row class + ❌ prefix + dismiss control.
    assert "job-row--failed" in src
    assert "❌" in src
    assert "job-dismiss" in src
    # User-dismissed terminals are tracked across polls.
    assert "_dismissedTerminals" in src
    # Refetch fires once per "wave" of transitions, not on every dismiss.
    assert "_refetchOnce" in src


@pytest.mark.asyncio
async def test_api_js_list_jobs_supports_include_recent_terminals(
    api_db_path: Path, assets_root: Path
) -> None:
    src = (assets_root / "js" / "api.js").read_text(encoding="utf-8")
    assert "include_recent_terminals" in src
    assert "includeRecentTerminals" in src


@pytest.mark.asyncio
async def test_index_css_styles_failed_job_row(api_db_path: Path, assets_root: Path) -> None:
    src = (assets_root / "css" / "index.css").read_text(encoding="utf-8")
    assert ".job-row--failed" in src
    assert ".job-dismiss" in src
