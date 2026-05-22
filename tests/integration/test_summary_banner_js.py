"""v0.7 hotfix — summary banner jsdom-light test.

Loads ``summary_banner.js`` and exercises the three states (collapsed /
expanded / dismissed) + the localStorage dismiss persistence + the
empty-summary regenerate path. Built on the same DOM shim pattern as
``test_sidebar_toggle_js.py`` so we don't need a jsdom dep.
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


# Minimal DOM shim large enough for renderSummaryBanner. Keeps a parent →
# children list so test code can introspect the rendered tree.
_SHIM = r"""
const store = new Map();
globalThis.localStorage = {
  getItem: (k) => (store.has(k) ? store.get(k) : null),
  setItem: (k, v) => store.set(k, String(v)),
  removeItem: (k) => store.delete(k),
  clear: () => store.clear(),
};

let _idCounter = 0;
class FakeEl {
  constructor(tag) {
    this.tagName = tag.toUpperCase();
    this.children = [];
    this.parent = null;
    this._classes = new Set();
    this._attrs = new Map();
    this._listeners = new Map();
    this.dataset = {};
    this.textContent = "";
    this.hidden = false;
    this._innerHTML = "";
    this.disabled = false;
    this.title = "";
    this.type = "";
    this._id = ++_idCounter;
    const self = this;
    this.classList = {
      add: (k) => self._classes.add(k),
      remove: (k) => self._classes.delete(k),
      contains: (k) => self._classes.has(k),
      toggle: (k, force) => {
        if (force === true) self._classes.add(k);
        else if (force === false) self._classes.delete(k);
        else if (self._classes.has(k)) self._classes.delete(k);
        else self._classes.add(k);
        return self._classes.has(k);
      },
    };
  }
  get className() { return [...this._classes].join(" "); }
  set className(v) {
    this._classes.clear();
    for (const c of String(v).split(/\s+/)) if (c) this._classes.add(c);
  }
  set innerHTML(v) {
    this._innerHTML = v;
    if (v === "") { for (const c of this.children) c.parent = null; this.children = []; }
  }
  get innerHTML() { return this._innerHTML; }
  appendChild(child) {
    child.parent = this;
    this.children.push(child);
    return child;
  }
  setAttribute(k, v) { this._attrs.set(k, String(v)); }
  getAttribute(k) { return this._attrs.get(k); }
  addEventListener(ev, fn) {
    if (!this._listeners.has(ev)) this._listeners.set(ev, []);
    this._listeners.get(ev).push(fn);
  }
  dispatch(ev) {
    (this._listeners.get(ev) || []).forEach((fn) => fn());
  }
  // Helpers for tests.
  findByClass(cls) {
    if (this._classes.has(cls)) return this;
    for (const c of this.children) {
      const hit = c.findByClass(cls);
      if (hit) return hit;
    }
    return null;
  }
}

globalThis.document = {
  createElement: (tag) => new FakeEl(tag),
};

// fetch shim for summarizeDocument (api.js apiPost -> fetch). Default:
// reject so we can swap per-test if needed.
globalThis.fetch = async () => {
  return new Response(JSON.stringify({}), { status: 200 });
};
class Response {
  constructor(body, init = {}) {
    this._body = body;
    this.status = init.status || 200;
    this.ok = this.status >= 200 && this.status < 300;
  }
  async text() { return this._body; }
  async json() { return JSON.parse(this._body); }
}
globalThis.Response = Response;
"""


def _run_node(script: str) -> dict:
    full = _SHIM + script
    proc = subprocess.run(
        ["node", "--input-type=module", "-e", full],
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


def test_renders_collapsed_by_default_with_preview() -> None:
    """Default state is collapsed: preview line visible, body hidden,
    actions hidden. v0.7 hotfix: this was permanently expanded before."""
    out = _run_node(
        r"""
        const mod = await import("./src/ht_lens/api/static/js/components/summary_banner.js");
        const mount = new FakeEl("div");
        const doc = { id: 42, summary: "A".repeat(500) };
        mod.renderSummaryBanner(mount, doc);
        const card = mount.findByClass("summary-banner");
        const preview = mount.findByClass("summary-banner-preview");
        const body = mount.findByClass("summary-banner-body");
        const actions = mount.findByClass("summary-banner-actions");
        console.log(JSON.stringify({
          mountHidden: mount.hidden,
          state: card?.dataset.state,
          previewLen: preview?.textContent?.length,
          previewEllipsis: preview?.textContent?.endsWith("…"),
          bodyHidden: body?.hidden,
          actionsHidden: actions?.hidden,
        }));
        """
    )
    assert out["mountHidden"] is False
    assert out["state"] == "collapsed"
    # 200 char preview + "…" suffix.
    assert out["previewEllipsis"] is True
    assert out["previewLen"] == 201
    assert out["bodyHidden"] is True
    assert out["actionsHidden"] is True


def test_toggle_click_expands_then_collapses() -> None:
    """▼ 더보기 click → expanded (body visible, actions visible).
    ▲ 접기 click → collapsed again. Round trip preserves state."""
    out = _run_node(
        r"""
        const mod = await import("./src/ht_lens/api/static/js/components/summary_banner.js");
        const mount = new FakeEl("div");
        mod.renderSummaryBanner(mount, { id: 1, summary: "hello world" });
        const card = mount.findByClass("summary-banner");
        const toggle = mount.findByClass("summary-banner-toggle");
        const body = mount.findByClass("summary-banner-body");
        const actions = mount.findByClass("summary-banner-actions");

        toggle.dispatch("click");
        const expanded = {
          state: card.dataset.state,
          bodyHidden: body.hidden,
          actionsHidden: actions.hidden,
          aria: toggle.getAttribute("aria-expanded"),
        };
        toggle.dispatch("click");
        const collapsed = {
          state: card.dataset.state,
          bodyHidden: body.hidden,
          actionsHidden: actions.hidden,
          aria: toggle.getAttribute("aria-expanded"),
        };
        console.log(JSON.stringify({ expanded, collapsed }));
        """
    )
    assert out["expanded"]["state"] == "expanded"
    assert out["expanded"]["bodyHidden"] is False
    assert out["expanded"]["actionsHidden"] is False
    assert out["expanded"]["aria"] == "true"
    assert out["collapsed"]["state"] == "collapsed"
    assert out["collapsed"]["bodyHidden"] is True
    assert out["collapsed"]["actionsHidden"] is True
    assert out["collapsed"]["aria"] == "false"


def test_close_click_sets_localstorage_and_hides_mount() -> None:
    """✕ close click → localStorage key set, mount hidden, and a fresh
    render of the SAME doc respects the persisted dismiss."""
    out = _run_node(
        r"""
        const mod = await import("./src/ht_lens/api/static/js/components/summary_banner.js");
        const mount = new FakeEl("div");
        const doc = { id: 7, summary: "anything" };
        mod.renderSummaryBanner(mount, doc);
        const close = mount.findByClass("summary-banner-close");
        close.dispatch("click");
        const afterClose = {
          mountHidden: mount.hidden,
          stored: localStorage.getItem(`ht_lens.summary.dismissed.${doc.id}`),
        };
        // Second render of the SAME doc must respect the dismiss flag.
        const mount2 = new FakeEl("div");
        mod.renderSummaryBanner(mount2, doc);
        const afterReload = { mountHidden: mount2.hidden };
        console.log(JSON.stringify({ afterClose, afterReload }));
        """
    )
    assert out["afterClose"]["mountHidden"] is True
    assert out["afterClose"]["stored"] == "true"
    assert out["afterReload"]["mountHidden"] is True


def test_empty_summary_hides_toggle_shows_regenerate() -> None:
    """``doc.summary === null`` → toggle hidden (nothing to expand) but
    the actions row stays visible with the "요약 생성" prompt."""
    out = _run_node(
        r"""
        const mod = await import("./src/ht_lens/api/static/js/components/summary_banner.js");
        const mount = new FakeEl("div");
        mod.renderSummaryBanner(mount, { id: 9, summary: null });
        const toggle = mount.findByClass("summary-banner-toggle");
        const actions = mount.findByClass("summary-banner-actions");
        const regen = mount.findByClass("summary-banner-regenerate");
        console.log(JSON.stringify({
          mountHidden: mount.hidden,
          toggleHidden: toggle?.hidden,
          actionsHidden: actions?.hidden,
          regenLabel: regen?.textContent,
        }));
        """
    )
    assert out["mountHidden"] is False
    assert out["toggleHidden"] is True
    assert out["actionsHidden"] is False
    assert out["regenLabel"] == "요약 생성"


def test_renders_nothing_when_doc_is_null() -> None:
    out = _run_node(
        r"""
        const mod = await import("./src/ht_lens/api/static/js/components/summary_banner.js");
        const mount = new FakeEl("div");
        mod.renderSummaryBanner(mount, null);
        console.log(JSON.stringify({ mountHidden: mount.hidden }));
        """
    )
    assert out["mountHidden"] is True
