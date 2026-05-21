"""Phase 6a R1 fix — behavioral test for ``renderConfirmModal``.

Drives the actual module under jsdom so confirm / cancel / backdrop /
DOM-cleanup behavior is locked beyond "the file is reachable". Skipped
when ``node`` or a local ``jsdom`` install is unavailable.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
CONFIRM = REPO / "src" / "ht_lens" / "api" / "static" / "js" / "components" / "confirm_modal.js"


def _find_jsdom() -> str | None:
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
    # Note: do NOT alias jsdom's queueMicrotask onto globalThis — jsdom's
    # implementation re-enters via the global which causes infinite recursion
    # under node. Node 22 already provides a native queueMicrotask which
    # the module picks up automatically.
    full = f"""
    import {{ JSDOM }} from "{jsdom_url}";
    const w = new JSDOM("<!doctype html><html><body></body></html>").window;
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


def test_confirm_button_fires_callback_and_removes_dom(jsdom_url: str) -> None:
    script = f"""
    const {{ renderConfirmModal }} = await import("{CONFIRM.as_uri()}");
    let confirmed = false;
    let canceled = false;
    renderConfirmModal({{
        title: "T", message: "M",
        onConfirm: () => {{ confirmed = true; }},
        onCancel:  () => {{ canceled  = true; }},
    }});
    const before = document.querySelectorAll(".confirm-modal").length;
    document.querySelector(".btn-confirm").click();
    const after = document.querySelectorAll(".confirm-modal").length;
    console.log(JSON.stringify({{ confirmed, canceled, before, after }}));
    """
    out = _run_with_jsdom(script, jsdom_url)
    assert out["confirmed"] is True
    assert out["canceled"] is False
    assert out["before"] == 1 and out["after"] == 0


def test_cancel_button_fires_callback_and_removes_dom(jsdom_url: str) -> None:
    script = f"""
    const {{ renderConfirmModal }} = await import("{CONFIRM.as_uri()}");
    let confirmed = false;
    let canceled = false;
    renderConfirmModal({{
        title: "T", message: "M",
        onConfirm: () => {{ confirmed = true; }},
        onCancel:  () => {{ canceled  = true; }},
    }});
    document.querySelector(".btn-cancel").click();
    const after = document.querySelectorAll(".confirm-modal").length;
    console.log(JSON.stringify({{ confirmed, canceled, after }}));
    """
    out = _run_with_jsdom(script, jsdom_url)
    assert out["canceled"] is True
    assert out["confirmed"] is False
    assert out["after"] == 0


def test_backdrop_click_cancels_and_removes_dom(jsdom_url: str) -> None:
    script = f"""
    const {{ renderConfirmModal }} = await import("{CONFIRM.as_uri()}");
    let canceled = false;
    renderConfirmModal({{
        title: "T", message: "M",
        onConfirm: () => {{}},
        onCancel:  () => {{ canceled = true; }},
    }});
    document.querySelector(".confirm-modal-backdrop").click();
    const after = document.querySelectorAll(".confirm-modal").length;
    console.log(JSON.stringify({{ canceled, after }}));
    """
    out = _run_with_jsdom(script, jsdom_url)
    assert out["canceled"] is True
    assert out["after"] == 0


def test_detail_text_is_rendered(jsdom_url: str) -> None:
    script = f"""
    const {{ renderConfirmModal }} = await import("{CONFIRM.as_uri()}");
    renderConfirmModal({{
        title: "T", message: "M", detail: "DETAIL_LINE_X",
        onConfirm: () => {{}},
    }});
    const small = document.querySelector(".confirm-modal-card small");
    console.log(JSON.stringify({{ text: small ? small.textContent : null }}));
    """
    out = _run_with_jsdom(script, jsdom_url)
    assert out["text"] == "DETAIL_LINE_X"
