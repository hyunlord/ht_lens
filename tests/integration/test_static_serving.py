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
    assert (
        mime_prefix in resp.headers["content-type"]
    ), f"{path} content-type={resp.headers['content-type']}"


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
    assert (
        "no documents yet" in src
    ), "index.js should show a friendly empty state when /documents is []"


@pytest.mark.asyncio
async def test_viewer_js_clamps_query_and_handles_404(api_db_path: Path, assets_root: Path) -> None:
    src = (assets_root / "js" / "viewer.js").read_text(encoding="utf-8")
    # clamp logic: viewer should bound `page` into [1, num_pages]
    assert (
        "Math.max(1" in src and "Math.min(doc.num_pages" in src
    ), "viewer.js should clamp the URL page into [1, num_pages]"
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
    assert (
        "rotation" in src and "rotation-banner" in src
    ), "page_view should warn on rotated pages instead of mis-aligning blocks"
