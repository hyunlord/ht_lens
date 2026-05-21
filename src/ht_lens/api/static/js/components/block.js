"use strict";

import { fitFontSize } from "../utils/font_fit.js";

/** Render a single block as an absolute-positioned div inside ``overlay``.
 *  Returns the created element (or null when the bbox is invalid). */
export function renderBlock(overlay, blockData, scale, overlayMode) {
  const bbox = sanitizeBbox(blockData, scale.pageW, scale.pageH);
  if (!bbox) return null;

  const el = document.createElement("div");
  el.className = `block block--${blockData.type}`;
  el.dataset.blockId = String(blockData.id);
  el.style.left = `${bbox.x0 * scale.x}px`;
  el.style.top = `${bbox.y0 * scale.y}px`;
  const w = (bbox.x1 - bbox.x0) * scale.x;
  const h = (bbox.y1 - bbox.y0) * scale.y;
  el.style.width = `${w}px`;
  el.style.height = `${h}px`;

  const isImage = blockData.type === "image";
  if (!isImage) {
    const text = pickText(blockData, overlayMode);
    if (text === null) {
      // Empty block — leave transparent (no synthetic placeholder).
      el.classList.add("block--empty");
    } else {
      if (
        overlayMode === "translation" &&
        (blockData.translated_text === null ||
          blockData.translated_text === undefined)
      ) {
        el.dataset.fallback = "original";
      }
      const weight = blockData.type === "header" ? "600" : "normal";
      const size = fitFontSize(text, w, h, weight);
      el.style.fontSize = `${size}px`;
      el.textContent = text;
    }
  }

  el.addEventListener("click", () => {
    // Phase 4: just log. Phase 5 will replace this with the chat-panel hook.
    // eslint-disable-next-line no-console
    console.log("block clicked", { id: blockData.id, type: blockData.type });
  });
  overlay.appendChild(el);
  return el;
}

/** Choose the visible text for ``mode``. Returns ``null`` for empty content. */
function pickText(blockData, mode) {
  let text;
  if (mode === "original") {
    text = blockData.original_text;
  } else {
    text =
      blockData.translated_text !== null &&
      blockData.translated_text !== undefined
        ? blockData.translated_text
        : blockData.original_text;
  }
  if (!text) return null;
  return text;
}

/** Validate and clamp the bbox to the page. Returns ``null`` if unusable. */
function sanitizeBbox(blockData, pageW, pageH) {
  const raw = blockData.bbox;
  if (!Array.isArray(raw) || raw.length !== 4) {
    console.warn("block bbox not a 4-tuple", blockData);
    return null;
  }
  const [x0, y0, x1, y1] = raw.map(Number);
  if (![x0, y0, x1, y1].every(Number.isFinite)) {
    console.warn("block bbox not finite", blockData);
    return null;
  }
  if (x1 <= x0 || y1 <= y0) {
    console.warn("block bbox not positive", blockData);
    return null;
  }
  const tol = 1.1; // 10% tolerance for slight extraction overshoot
  if (x0 < 0 || y0 < 0 || x1 > pageW * tol || y1 > pageH * tol) {
    console.warn("block bbox outside page", blockData);
    return null;
  }
  return { x0, y0, x1, y1 };
}
