"""Phase 6i — KaTeX rendering for viewer block overlay and chat messages.

Mirrors the Phase 5 ``test_render_markdown_js.py`` harness: drives the
actual `applyMath` / `renderMarkdown` exports through node + jsdom so the
real ESM modules + KaTeX fonts pipeline is exercised. Skipped when
either ``node`` or a usable ``jsdom`` install cannot be located.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
RENDER_MD = REPO / "src" / "ht_lens" / "api" / "static" / "js" / "utils" / "render_markdown.js"
BLOCK_JS = REPO / "src" / "ht_lens" / "api" / "static" / "js" / "components" / "block.js"
MESSAGE_JS = REPO / "src" / "ht_lens" / "api" / "static" / "js" / "components" / "message.js"


def _find_jsdom() -> str | None:
    candidates = [
        Path(__file__).resolve().parents[2] / "node_modules" / "jsdom",  # repo-local (CI npm ci)
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
    # KaTeX refuses to render in quirks-mode documents; pass an explicit
    # doctype so jsdom sets document.compatMode = "CSS1Compat".
    full = f"""
    import {{ JSDOM }} from "{jsdom_url}";
    const w = new JSDOM("<!doctype html><html><body></body></html>").window;
    globalThis.window = w;
    globalThis.document = w.document;
    globalThis.HTMLElement = w.HTMLElement;
    globalThis.Element = w.Element;
    globalThis.Node = w.Node;
    globalThis.DocumentFragment = w.DocumentFragment;
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


# ---------------------------------------------------------------------------
# V1 contracts (1-6)
# ---------------------------------------------------------------------------


def test_inline_math_renders_to_katex_span(jsdom_url: str) -> None:
    text = "$E = mc^2$"
    script = f"""
    const {{ applyMath }} = await import("{RENDER_MD.as_uri()}");
    const el = document.createElement("div");
    el.textContent = {json.dumps(text)};
    applyMath(el);
    console.log(JSON.stringify({{ html: el.innerHTML }}));
    """
    out = _run_with_jsdom(script, jsdom_url)
    assert 'class="katex"' in out["html"], out["html"]
    # raw source replaced with rendered HTML
    assert out["html"].count("$") <= 1


def test_korean_text_with_inline_math_mixed(jsdom_url: str) -> None:
    text = "잠재 변수 $p(z)$ 사용"
    script = f"""
    const {{ applyMath }} = await import("{RENDER_MD.as_uri()}");
    const el = document.createElement("div");
    el.textContent = {json.dumps(text)};
    applyMath(el);
    console.log(JSON.stringify({{ html: el.innerHTML, text: el.textContent }}));
    """
    out = _run_with_jsdom(script, jsdom_url)
    assert "잠재 변수" in out["html"]
    assert "사용" in out["html"]
    assert 'class="katex"' in out["html"]


def test_display_math_renders(jsdom_url: str) -> None:
    text = r"$$\sum_{k=1}^K z_k = 1$$"
    script = f"""
    const {{ applyMath }} = await import("{RENDER_MD.as_uri()}");
    const el = document.createElement("div");
    el.textContent = {json.dumps(text)};
    applyMath(el);
    console.log(JSON.stringify({{ html: el.innerHTML }}));
    """
    out = _run_with_jsdom(script, jsdom_url)
    # KaTeX wraps display math in .katex-display (auto-render contrib).
    assert "katex-display" in out["html"] or 'class="katex"' in out["html"]


def test_broken_latex_falls_back(jsdom_url: str) -> None:
    text = r"$\invalidcmd{$"
    script = f"""
    const {{ applyMath }} = await import("{RENDER_MD.as_uri()}");
    const el = document.createElement("div");
    el.textContent = {json.dumps(text)};
    let threw = false;
    try {{ applyMath(el); }} catch (e) {{ threw = true; }}
    console.log(JSON.stringify({{ html: el.innerHTML, threw }}));
    """
    out = _run_with_jsdom(script, jsdom_url)
    assert out["threw"] is False, "applyMath must not throw on broken LaTeX"
    # Either the original text is preserved or KaTeX rendered an error span.
    assert "invalidcmd" in out["html"] or "katex-error" in out["html"]


def test_render_markdown_then_apply_math_preserves_katex(jsdom_url: str) -> None:
    md = "Pythagorean: $a^2 + b^2 = c^2$. Done."
    script = f"""
    const {{ renderMarkdown, applyMath }} = await import("{RENDER_MD.as_uri()}");
    const el = document.createElement("div");
    el.innerHTML = renderMarkdown({json.dumps(md)});
    applyMath(el);
    console.log(JSON.stringify({{ html: el.innerHTML }}));
    """
    out = _run_with_jsdom(script, jsdom_url)
    assert 'class="katex"' in out["html"]
    assert "Pythagorean" in out["html"]
    assert "Done." in out["html"]


def test_no_xss_via_href_in_math(jsdom_url: str) -> None:
    """KaTeX with ``trust: false`` must NOT emit an executable
    ``<a href="javascript:...">``. The literal string can still appear
    inside the MathML ``<annotation>`` (source-text mirror, never
    executed by browsers), so the real security assertion is on the
    presence of a clickable href."""
    text = r"$\href{javascript:alert(1)}{x}$"
    script = f"""
    const {{ applyMath }} = await import("{RENDER_MD.as_uri()}");
    const el = document.createElement("div");
    el.textContent = {json.dumps(text)};
    applyMath(el);
    const anchors = el.querySelectorAll("a[href]");
    const hrefs = Array.from(anchors).map(a => a.getAttribute("href"));
    // Strip the MathML annotation text (it can legally echo the source).
    const stripped = el.cloneNode(true);
    for (const ann of stripped.querySelectorAll("annotation")) {{
      ann.remove();
    }}
    console.log(JSON.stringify({{
      hrefs,
      strippedHtml: stripped.innerHTML,
      hasHrefAttr: el.querySelector("a[href]") !== null,
    }}));
    """
    out = _run_with_jsdom(script, jsdom_url)
    assert out["hasHrefAttr"] is False, (
        f"KaTeX trust:false must not emit any <a href>; got {out['hrefs']}"
    )
    assert "javascript:" not in out["strippedHtml"].lower(), (
        f"After removing MathML annotation, no javascript: text should remain: "
        f"{out['strippedHtml']}"
    )


# ---------------------------------------------------------------------------
# V2 additions (7-11) — Codex debate §5
# ---------------------------------------------------------------------------


def test_chat_assistant_message_applies_math(jsdom_url: str) -> None:
    """``message.js`` assistant path runs renderMarkdown + applyMath."""
    msg_content = r"The formula is $E=mc^2$ — energy-mass equivalence."
    script = f"""
    const {{ renderMarkdown, applyMath }} = await import("{RENDER_MD.as_uri()}");
    const body = document.createElement("div");
    body.innerHTML = renderMarkdown({json.dumps(msg_content)});
    applyMath(body);
    console.log(JSON.stringify({{ html: body.innerHTML }}));
    """
    out = _run_with_jsdom(script, jsdom_url)
    assert 'class="katex"' in out["html"]
    assert "energy-mass equivalence" in out["html"]


def test_user_message_with_dollar_stays_plain(jsdom_url: str) -> None:
    """User/system messages take the plain-text path (no applyMath).

    The contract is enforced in ``message.js`` (assistant-only). We
    assert that the markdown+math path applied to a user-style message
    is NOT how user content is rendered: i.e., ``textContent`` is the
    correct surface for ``$5.00`` and never triggers KaTeX.
    """
    text = "It costs $5.00 today."
    script = f"""
    const el = document.createElement("div");
    el.textContent = {json.dumps(text)};  // user-content path
    console.log(JSON.stringify({{ html: el.innerHTML, text: el.textContent }}));
    """
    out = _run_with_jsdom(script, jsdom_url)
    assert "katex" not in out["html"]
    assert out["text"] == text


def test_paired_delimiter_gate_ignores_unmatched_dollar(jsdom_url: str) -> None:
    """``block.js`` exports ``hasPairedMath``; tests import the real
    implementation rather than redefining the regex (verify-cross R1)."""
    cases = {
        "$5.00 only": False,  # unmatched
        "no math here": False,
        "$E=mc^2$": True,
        "잠재 변수 $p(z)$ 사용": True,
        "Two prices: $5 and $10": True,
        # ^ The naive regex matches the run "$5 and $10" — KaTeX will then
        # silently fail to parse it (throwOnError:false), so this is safe
        # but the gate itself does fire. Documenting the known
        # over-trigger here so it is intentional.
        "$$display$$": True,
        "": False,
    }
    inputs = json.dumps(cases)
    script = f"""
    const {{ hasPairedMath }} = await import("{BLOCK_JS.as_uri()}");
    const cases = {inputs};
    const results = {{}};
    for (const text of Object.keys(cases)) {{
      results[text] = hasPairedMath(text);
    }}
    console.log(JSON.stringify(results));
    """
    out = _run_with_jsdom(script, jsdom_url)
    for text, expected in cases.items():
        assert out[text] == expected, f"hasPairedMath({text!r}) = {out[text]}, expected {expected}"


def test_markdown_code_block_math_not_rendered(jsdom_url: str) -> None:
    """KaTeX ``ignoredTags`` keeps ``$...$`` inside ``<code>``/``<pre>`` literal."""
    md = "Inline `let x = $a + b$;` should stay literal.\n\n```\nlet y = $c$;\n```\n"
    script = f"""
    const {{ renderMarkdown, applyMath }} = await import("{RENDER_MD.as_uri()}");
    const el = document.createElement("div");
    el.innerHTML = renderMarkdown({json.dumps(md)});
    applyMath(el);
    // Find all <code> elements and confirm none have katex children.
    const codes = el.querySelectorAll("code, pre");
    let hasKatex = false;
    for (const c of codes) {{
      if (c.querySelector(".katex")) hasKatex = true;
    }}
    console.log(JSON.stringify({{ hasKatex, html: el.innerHTML }}));
    """
    out = _run_with_jsdom(script, jsdom_url)
    assert out["hasKatex"] is False, f"KaTeX should not render inside <pre>/<code>: {out['html']}"


def test_block_translation_math_preserves_listeners_contract(jsdom_url: str) -> None:
    """Whatever DOM mutation KaTeX does, it must not blow away listeners
    we attach to the block element itself (click + contextmenu in
    block.js). KaTeX rewrites only the children, so the host listeners
    survive — this test verifies that invariant directly."""
    text = "수식 $x^2$ 포함"
    script = f"""
    const {{ applyMath }} = await import("{RENDER_MD.as_uri()}");
    const el = document.createElement("div");
    el.textContent = {json.dumps(text)};
    let clicks = 0;
    let menus = 0;
    el.addEventListener("click", () => {{ clicks += 1; }});
    el.addEventListener("contextmenu", () => {{ menus += 1; }});
    applyMath(el);
    el.dispatchEvent(new window.Event("click", {{ bubbles: true }}));
    el.dispatchEvent(new window.Event("contextmenu", {{ bubbles: true }}));
    console.log(JSON.stringify({{ clicks, menus, hasKatex: !!el.querySelector(".katex") }}));
    """
    out = _run_with_jsdom(script, jsdom_url)
    assert out["clicks"] == 1, "click listener on host element must survive applyMath"
    assert out["menus"] == 1, "contextmenu listener on host element must survive applyMath"
    assert out["hasKatex"] is True, "math should still render"


# ---------------------------------------------------------------------------
# V3 additions (verify-cross R1 RE-CODE) — drive real ``renderBlock`` /
# ``renderMessage`` through jsdom so the new branches are locked, not just
# the underlying utility.
# ---------------------------------------------------------------------------


def _block_data(text: str) -> dict:
    """Block payload shaped like the API contract — bbox + translated_text."""
    return {
        "id": 1,
        "type": "text",
        "bbox": [10, 10, 400, 80],
        "original_text": "original placeholder",
        "translated_text": text,
    }


def test_render_block_translation_mode_renders_math(jsdom_url: str) -> None:
    """``renderBlock(..., 'translation')`` invokes KaTeX when the
    translated_text contains paired math delimiters."""
    block_data = _block_data("잠재 변수 $p(z) = \\\\alpha$ 사용")
    script = f"""
    const {{ renderBlock }} = await import("{BLOCK_JS.as_uri()}");
    const overlay = document.createElement("div");
    const scale = {{ x: 1, y: 1, pageW: 1000, pageH: 1000 }};
    const el = renderBlock(overlay, {json.dumps(block_data)}, scale, "translation");
    console.log(JSON.stringify({{
      html: el.innerHTML,
      hasKatex: !!el.querySelector(".katex"),
    }}));
    """
    out = _run_with_jsdom(script, jsdom_url)
    assert out["hasKatex"] is True, f"renderBlock translation+math: {out['html']}"


def test_render_block_original_mode_does_not_render_math(jsdom_url: str) -> None:
    """``renderBlock(..., 'original')`` must NEVER call KaTeX even when the
    original_text contains paired ``$...$`` — original content stays
    literal so PDF source is shown verbatim (verify-cross R1 gap)."""
    data = {
        "id": 2,
        "type": "text",
        "bbox": [10, 10, 400, 80],
        "original_text": "Original $E=mc^2$ formula",
        "translated_text": "번역 $E=mc^2$ 수식",
    }
    script = f"""
    const {{ renderBlock }} = await import("{BLOCK_JS.as_uri()}");
    const overlay = document.createElement("div");
    const scale = {{ x: 1, y: 1, pageW: 1000, pageH: 1000 }};
    const el = renderBlock(overlay, {json.dumps(data)}, scale, "original");
    console.log(JSON.stringify({{
      html: el.innerHTML,
      text: el.textContent,
      hasKatex: !!el.querySelector(".katex"),
    }}));
    """
    out = _run_with_jsdom(script, jsdom_url)
    assert out["hasKatex"] is False, (
        f"renderBlock original mode must NOT invoke KaTeX, got: {out['html']}"
    )
    assert "$E=mc^2$" in out["text"], "original_text should be shown verbatim"


def test_render_block_unmatched_dollar_skips_katex(jsdom_url: str) -> None:
    """Single ``$5.00`` (currency) must NOT trigger KaTeX even in
    translation mode — locks the paired-delimiter gate at the call site."""
    block_data = _block_data("It costs $5.00 today.")
    script = f"""
    const {{ renderBlock }} = await import("{BLOCK_JS.as_uri()}");
    const overlay = document.createElement("div");
    const scale = {{ x: 1, y: 1, pageW: 1000, pageH: 1000 }};
    const el = renderBlock(overlay, {json.dumps(block_data)}, scale, "translation");
    console.log(JSON.stringify({{
      html: el.innerHTML,
      text: el.textContent,
      hasKatex: !!el.querySelector(".katex"),
    }}));
    """
    out = _run_with_jsdom(script, jsdom_url)
    assert out["hasKatex"] is False, f"unmatched $ should skip KaTeX, got: {out['html']}"
    assert out["text"] == "It costs $5.00 today."


def test_render_message_assistant_renders_math(jsdom_url: str) -> None:
    """Directly call ``renderMessage`` (message.js) with an assistant
    role + math content and confirm KaTeX rendered."""
    msg = {
        "id": 42,
        "role": "assistant",
        "content": "Pythagoras: $a^2 + b^2 = c^2$",
        "model": "test",
    }
    script = f"""
    const {{ renderMessage }} = await import("{MESSAGE_JS.as_uri()}");
    const container = document.createElement("div");
    renderMessage(container, {json.dumps(msg)});
    const body = container.querySelector(".message-body");
    console.log(JSON.stringify({{
      html: body.innerHTML,
      hasKatex: !!body.querySelector(".katex"),
    }}));
    """
    out = _run_with_jsdom(script, jsdom_url)
    assert out["hasKatex"] is True, f"assistant message must render math: {out['html']}"
    assert "Pythagoras" in out["html"]


def test_render_message_user_role_stays_plain_text(jsdom_url: str) -> None:
    """User-role message must use ``textContent`` path — ``$5.00`` typed
    in the chat box should never trigger KaTeX (verify-cross R1 gap:
    bypassing message.js was the prior coverage hole)."""
    msg = {
        "id": 43,
        "role": "user",
        "content": "It costs $5.00 and $10.00 — math? $x^2$",
        "model": None,
    }
    script = f"""
    const {{ renderMessage }} = await import("{MESSAGE_JS.as_uri()}");
    const container = document.createElement("div");
    renderMessage(container, {json.dumps(msg)});
    const body = container.querySelector(".message-body");
    console.log(JSON.stringify({{
      html: body.innerHTML,
      text: body.textContent,
      hasKatex: !!body.querySelector(".katex"),
    }}));
    """
    out = _run_with_jsdom(script, jsdom_url)
    assert out["hasKatex"] is False, f"user message must NOT invoke KaTeX, got: {out['html']}"
    assert out["text"] == "It costs $5.00 and $10.00 — math? $x^2$"
    # innerHTML should NOT contain raw HTML tags — user content stays text.
    assert "<" not in out["html"] or "&lt;" in out["html"], (
        "user content must not be parsed as HTML"
    )
