"""Phase 8d-2c — resize.js unit tests (jsdom).

Locks the drawer resize + body-coupling contract the challenge (R9) requires:
- width clamps to [280, 60vw] and persists to sessionStorage (NOT localStorage);
- the body margin follows the drawer ONLY in single reading mode while open;
- compare mode is overlay (no margin → the 1fr|1fr grid is never squeezed);
- closing the drawer or switching to compare clears the margin;
- a persisted width is restored on init; dragging the handle updates the width.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
RESIZE_JS = REPO / "src" / "ht_lens" / "api" / "static" / "js" / "resize.js"


def _find_jsdom() -> str | None:
    for p in (
        Path(__file__).resolve().parents[2] / "node_modules" / "jsdom",  # repo-local (CI npm ci)
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
    const w = new JSDOM(`<!doctype html><html><body>
      <div class="layout" id="layout" data-mode="single">
        <aside class="pane--pdf"></aside>
        <main class="pane--reflow"></main>
      </div>
      <aside class="chat" id="chat" hidden>
        <div class="chat-resizer"></div>
      </aside>
    </body></html>`, { url: "http://localhost/" }).window;
    globalThis.window = w; globalThis.document = w.document;
    globalThis.MouseEvent = w.MouseEvent;
    const doc = w.document;
    const R = await import("%(resize)s");
"""


def _run(body: str, jsdom_url: str) -> dict:
    full = (_PRELUDE % {"jsdom": jsdom_url, "resize": RESIZE_JS.as_uri()}) + body
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


def test_clamp_width_bounds(jsdom_url: str) -> None:
    out = _run(
        """
        console.log(JSON.stringify({
          min: R.clampWidth(100, 1024),       // below MIN → 280
          max: R.clampWidth(99999, 1024),     // above 60vw → 614
          mid: R.clampWidth(400, 1024),       // in range → 400
          tinyViewport: R.clampWidth(400, 300) // 60vw=180 < MIN → MIN wins
        }));
        """,
        jsdom_url,
    )
    assert out == {"min": 280, "max": 614, "mid": 400, "tinyViewport": 280}


def test_apply_width_sets_var_and_session(jsdom_url: str) -> None:
    out = _run(
        """
        R.applyChatWidth(450, { doc, win: w });
        console.log(JSON.stringify({
          cssVar: doc.documentElement.style.getPropertyValue("--chat-w"),
          stored: w.sessionStorage.getItem(R.STORAGE_KEY),
        }));
        """,
        jsdom_url,
    )
    assert out == {"cssVar": "450px", "stored": "450"}


def test_sync_margin_single_open_sets_body_margin(jsdom_url: str) -> None:
    out = _run(
        """
        doc.getElementById("chat").removeAttribute("hidden");
        R.applyChatWidth(450, { doc, win: w });
        const ret = R.syncPaneMargin({ doc });
        console.log(JSON.stringify({
          margin: doc.querySelector(".pane--reflow").style.marginRight,
          ret,
        }));
        """,
        jsdom_url,
    )
    assert out == {"margin": "450px", "ret": "450px"}


def test_compare_mode_does_not_squeeze_pane(jsdom_url: str) -> None:
    # R9: compare is overlay — open drawer, compare mode → NO body margin.
    out = _run(
        """
        doc.getElementById("chat").removeAttribute("hidden");
        R.applyChatWidth(450, { doc, win: w });
        doc.getElementById("layout").dataset.mode = "compare";
        const ret = R.syncPaneMargin({ doc });
        console.log(JSON.stringify({
          margin: doc.querySelector(".pane--reflow").style.marginRight,
          ret,
        }));
        """,
        jsdom_url,
    )
    assert out == {"margin": "", "ret": ""}


def test_close_then_reopen_round_trips_margin(jsdom_url: str) -> None:
    # open (single) sets margin; close clears it; reopen restores it at the same
    # width (R9 / debate §5 #5: close, reopen, restore together).
    out = _run(
        """
        const chat = doc.getElementById("chat");
        chat.removeAttribute("hidden");
        R.applyChatWidth(450, { doc, win: w });
        const opened = R.syncPaneMargin({ doc });
        chat.setAttribute("hidden", "");
        const closed = R.syncPaneMargin({ doc });
        chat.removeAttribute("hidden");
        const reopened = R.syncPaneMargin({ doc });
        console.log(JSON.stringify({ opened, closed, reopened }));
        """,
        jsdom_url,
    )
    assert out["opened"] == "450px"
    assert out["closed"] == ""
    assert out["reopened"] == "450px"  # width preserved across the close/reopen cycle


def test_init_restores_persisted_width(jsdom_url: str) -> None:
    out = _run(
        """
        w.sessionStorage.setItem(R.STORAGE_KEY, "500");
        R.initResize({ doc, win: w });
        console.log(JSON.stringify({
          cssVar: doc.documentElement.style.getPropertyValue("--chat-w"),
        }));
        """,
        jsdom_url,
    )
    assert out == {"cssVar": "500px"}


def test_init_default_width_when_no_session(jsdom_url: str) -> None:
    out = _run(
        """
        R.initResize({ doc, win: w });
        console.log(JSON.stringify({
          cssVar: doc.documentElement.style.getPropertyValue("--chat-w"),
        }));
        """,
        jsdom_url,
    )
    assert out == {"cssVar": "380px"}


def test_drag_handle_updates_width(jsdom_url: str) -> None:
    # Drawer on the right: dragging the handle LEFT (clientX 900→800) widens it
    # from the 380 default by 100 → 480.
    out = _run(
        """
        doc.getElementById("chat").removeAttribute("hidden");
        R.initResize({ doc, win: w });
        const handle = doc.querySelector(".chat-resizer");
        handle.dispatchEvent(new MouseEvent("pointerdown", { clientX: 900, bubbles: true }));
        doc.dispatchEvent(new MouseEvent("pointermove", { clientX: 800, bubbles: true }));
        doc.dispatchEvent(new MouseEvent("pointerup", { bubbles: true }));
        console.log(JSON.stringify({
          cssVar: doc.documentElement.style.getPropertyValue("--chat-w"),
          margin: doc.querySelector(".pane--reflow").style.marginRight,
          stored: w.sessionStorage.getItem(R.STORAGE_KEY),
        }));
        """,
        jsdom_url,
    )
    assert out == {"cssVar": "480px", "margin": "480px", "stored": "480"}
