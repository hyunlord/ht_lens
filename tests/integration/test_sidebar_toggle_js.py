"""v0.7 hotfix — sidebar toggle behavioural test (jsdom-light pattern).

Loads ``state.js`` as a real ES module under Node, attaches the exact
wiring viewer.js uses (sidebar-toggle click → ``toggleSidebar()`` +
``applySidebarOpen()``), and asserts that click + class-toggle round
trips correctly across two clicks. This is the live-behaviour guard
that grep-only Phase 6c verify could not provide.

CSS-cascade guard (the actual root cause of the v0.7 regression) lives
in ``test_static_serving.py`` — this file locks the JS path.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


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
            f"node failed:\n  rc={proc.returncode}\n  stdout={proc.stdout}\n  stderr={proc.stderr}"
        )
    return json.loads(proc.stdout.strip().splitlines()[-1])


_SCRIPT = r"""
// Minimal shims for state.js's localStorage usage.
const store = new Map();
globalThis.localStorage = {
  getItem: (k) => (store.has(k) ? store.get(k) : null),
  setItem: (k, v) => store.set(k, String(v)),
  removeItem: (k) => store.delete(k),
  clear: () => store.clear(),
};

// FakeEl: just enough DOMTokenList.toggle + addEventListener semantics.
class FakeEl {
  constructor() {
    this._classes = new Set();
    this._attrs = new Map();
    this._listeners = new Map();
    this.text = "";
  }
  setAttribute(k, v) { this._attrs.set(k, v); }
  addEventListener(ev, fn) {
    if (!this._listeners.has(ev)) this._listeners.set(ev, []);
    this._listeners.get(ev).push(fn);
  }
  dispatch(ev) {
    (this._listeners.get(ev) || []).forEach((fn) => fn());
  }
}
const shell = new FakeEl();
const btn = new FakeEl();
// DOMTokenList.toggle-compatible shape on the shell.
shell.classList = {
  _set: new Set(),
  toggle(klass, force) {
    if (force === true) this._set.add(klass);
    else if (force === false) this._set.delete(klass);
    else if (this._set.has(klass)) this._set.delete(klass);
    else this._set.add(klass);
    return this._set.has(klass);
  },
  has(klass) { return this._set.has(klass); },
};

const stateMod = await import("./src/ht_lens/api/static/js/state.js");
const { state, toggleSidebar, subscribe } = stateMod;

// Exactly the wiring at viewer.js lines 813-828.
function applySidebarOpen() {
  shell.classList.toggle("viewer-shell--sidebar-closed", !state.sidebarOpen);
  btn.text = state.sidebarOpen ? "left-arrow" : "right-arrow";
  btn.setAttribute("aria-expanded", state.sidebarOpen ? "true" : "false");
}
applySidebarOpen();
btn.addEventListener("click", () => {
  toggleSidebar();
  applySidebarOpen();
});
subscribe(() => applySidebarOpen());

const initial = {
  sidebarOpen: state.sidebarOpen,
  closed: shell.classList.has("viewer-shell--sidebar-closed"),
};
btn.dispatch("click");
const afterClick1 = {
  sidebarOpen: state.sidebarOpen,
  closed: shell.classList.has("viewer-shell--sidebar-closed"),
  aria: btn._attrs.get("aria-expanded"),
};
btn.dispatch("click");
const afterClick2 = {
  sidebarOpen: state.sidebarOpen,
  closed: shell.classList.has("viewer-shell--sidebar-closed"),
  aria: btn._attrs.get("aria-expanded"),
};

console.log(JSON.stringify({ initial, afterClick1, afterClick2 }));
"""


def test_sidebar_toggle_click_flips_state_and_class() -> None:
    out = _run_node(_SCRIPT)
    # Defaults to open per state.js safeReadBool(STORAGE_SIDEBAR_OPEN, true).
    assert out["initial"]["sidebarOpen"] is True
    assert out["initial"]["closed"] is False
    # First click → closed.
    assert out["afterClick1"]["sidebarOpen"] is False
    assert out["afterClick1"]["closed"] is True
    assert out["afterClick1"]["aria"] == "false"
    # Second click → open again (round-trip).
    assert out["afterClick2"]["sidebarOpen"] is True
    assert out["afterClick2"]["closed"] is False
    assert out["afterClick2"]["aria"] == "true"
