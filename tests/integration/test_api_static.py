"""Phase 3 — /static mount."""

from __future__ import annotations

from pathlib import Path

import pytest

from ._api_helpers import make_test_client


@pytest.mark.asyncio
async def test_static_gitkeep_is_served(api_db_path: Path) -> None:
    with make_test_client(api_db_path) as client:
        resp = client.get("/static/.gitkeep")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_static_missing_file_returns_404(api_db_path: Path) -> None:
    with make_test_client(api_db_path) as client:
        resp = client.get("/static/nonexistent.html")
    assert resp.status_code == 404
