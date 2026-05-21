"use strict";

/** Render assistant markdown to HTML safely.
 *
 * - ``marked`` handles GFM (tables, fenced code, autolinks, line breaks).
 * - ``DOMPurify`` strips XSS payloads (script/iframe/javascript: href/on*).
 * - External links open in a new tab (rel="noopener noreferrer").
 */

import { marked } from "../../vendor/marked.esm.js";
import DOMPurifyFactory from "../../vendor/purify.es.mjs";

// In the browser the default export is already initialised with `window`;
// the factory call is a no-op fallback for harnesses (jsdom-based tests).
const DOMPurify =
  typeof globalThis.window === "object" && globalThis.window
    ? DOMPurifyFactory.sanitize
      ? DOMPurifyFactory
      : DOMPurifyFactory(globalThis.window)
    : DOMPurifyFactory(globalThis.window || globalThis);

marked.setOptions({ breaks: true, gfm: true });

// Force-attach safe link attributes to every <a>.
DOMPurify.addHook("afterSanitizeAttributes", (node) => {
  if (node.tagName === "A" && node.getAttribute("href")) {
    node.setAttribute("target", "_blank");
    node.setAttribute("rel", "noopener noreferrer");
  }
});

/** Markdown -> sanitised HTML string. Empty/null -> "". */
export function renderMarkdown(text) {
  if (!text) return "";
  const html = marked.parse(text);
  return DOMPurify.sanitize(html, {
    USE_PROFILES: { html: true },
    ADD_ATTR: ["target", "rel"],
  });
}

export { DOMPurify };
