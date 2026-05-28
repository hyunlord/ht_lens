"use strict";

/** Render assistant markdown to HTML safely + render LaTeX math.
 *
 * - ``marked`` handles GFM (tables, fenced code, autolinks, line breaks).
 * - ``DOMPurify`` strips XSS payloads (script/iframe/javascript: href/on*).
 * - External links open in a new tab (rel="noopener noreferrer").
 * - ``applyMath(el)`` (Phase 6i): walks ``el`` and renders ``$...$`` /
 *   ``$$...$$`` runs with KaTeX in-place. Callers decide WHEN to call it
 *   so currency/raw prose never accidentally trigger math rendering.
 *   KaTeX output is **not** re-sanitised — KaTeX's own ``trust: false``
 *   plus ``ignoredTags`` is the security boundary for that path.
 */

import { marked } from "../../vendor/marked.esm.js";
import DOMPurifyFactory from "../../vendor/purify.es.mjs";
import renderMathInElementExt from "../../vendor/katex/auto-render.mjs";

// In the browser the default export is already initialised with `window`;
// the factory call is a no-op fallback for harnesses (jsdom-based tests).
const DOMPurify =
  typeof globalThis.window === "object" && globalThis.window
    ? DOMPurifyFactory.sanitize
      ? DOMPurifyFactory
      : DOMPurifyFactory(globalThis.window)
    : DOMPurifyFactory(globalThis.window || globalThis);

marked.setOptions({ breaks: true, gfm: true });

// Force-attach safe link attributes to every <a>. Guarded because some
// non-browser harnesses load this module purely for ``applyMath`` without
// providing a window — in that case DOMPurifyFactory returns an object
// without ``addHook``; tolerating it lets viewport/block tests import
// transitively (Phase 6i regression fix).
if (typeof DOMPurify?.addHook === "function") {
  DOMPurify.addHook("afterSanitizeAttributes", (node) => {
    if (node.tagName === "A" && node.getAttribute("href")) {
      node.setAttribute("target", "_blank");
      node.setAttribute("rel", "noopener noreferrer");
    }
  });
}

/** Markdown -> sanitised HTML string. Empty/null -> "". */
export function renderMarkdown(text) {
  if (!text) return "";
  const html = marked.parse(text);
  return DOMPurify.sanitize(html, {
    USE_PROFILES: { html: true },
    ADD_ATTR: ["target", "rel"],
  });
}

/** Render ``$...$`` (inline) and ``$$...$$`` (display) math inside ``el``
 *  using KaTeX's auto-render contrib. In-place; ignores ``pre`` / ``code``
 *  / ``script`` / ``style`` / ``textarea`` / ``noscript`` / ``option`` so
 *  fenced code blocks and prose about LaTeX syntax stay literal.
 *
 *  Hardened against bad input:
 *  - ``throwOnError: false`` — broken LaTeX renders the source in
 *    ``errorColor`` rather than throwing.
 *  - ``trust: false`` — ``\href`` only accepts http/https/mailto, blocks
 *    ``javascript:`` and other risky protocols.
 *  - ``strict: false`` — unknown commands warn to console instead of
 *    raising.
 *
 *  KaTeX output is NOT re-sanitised by DOMPurify; the configuration
 *  above is the post-sanitise security boundary. See
 *  ``tests/integration/test_katex_render_js.py``.
 */
export function applyMath(el) {
  if (!el) return;
  try {
    renderMathInElementExt(el, {
      delimiters: [
        { left: "$$", right: "$$", display: true },
        { left: "$", right: "$", display: false },
      ],
      ignoredTags: ["script", "noscript", "style", "textarea", "pre", "code", "option"],
      throwOnError: false,
      errorColor: "#cc0000",
      trust: false,
      strict: false,
    });
  } catch (e) {
    // Last-resort guard: with throwOnError:false the extension should
    // not throw, but if upstream KaTeX changes behaviour we still want
    // the host page to keep working.
    console.warn("KaTeX renderMathInElement failed", e);
  }
}

export { DOMPurify };
