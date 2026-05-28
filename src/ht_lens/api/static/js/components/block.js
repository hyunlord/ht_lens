"use strict";

import { fitFontSize } from "../utils/font_fit.js";
import { applyMath } from "../utils/render_markdown.js";

// Phase 6i: paired-delimiter gate. Only trigger KaTeX when the text
// actually has a ``$...$`` or ``$$...$$`` pair so currency like ``$5.00``
// or single unmatched dollars never invoke the renderer. The newline
// guard on the inline pattern keeps multi-paragraph translations from
// matching across line breaks.
const INLINE_MATH_RE = /\$[^$\n]+\$/;
const DISPLAY_MATH_RE = /\$\$[\s\S]+?\$\$/;

function _hasPairedMath(text) {
  return DISPLAY_MATH_RE.test(text) || INLINE_MATH_RE.test(text);
}

/** Render a single block as an absolute-positioned div inside ``overlay``.
 *  Returns the created element (or null when the bbox is invalid).
 *
 *  Phase 5 additions:
 *   - ``threadsForBlock`` (array) drives the pin display via
 *     ``data-has-thread`` / ``data-thread-count`` so a single block can
 *     legally own multiple threads (see Phase 3 API contract).
 *   - click dispatches a bubbling ``ht-lens:block-click`` CustomEvent so
 *     ``viewer.js`` (the single panel owner) handles it without creating a
 *     circular module import.
 */
export function renderBlock(
  overlay,
  blockData,
  scale,
  overlayMode,
  threadsForBlock = [],
) {
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
      // Phase 6i: render LaTeX math in-place after text content is set.
      // ``fitFontSize`` already sized the box using raw character widths;
      // KaTeX inherits the chosen font-size via CSS (.block .katex
      // { font-size: inherit }). Only call when paired delimiters are
      // present so unrelated ``$`` (currency, OCR noise) is skipped.
      if (overlayMode === "translation" && _hasPairedMath(text)) {
        applyMath(el);
      }
      // Phase 6h hot-fix: flag blocks whose bbox is too small to display
      // the wrapped translation. The viewer's overlay clips text via
      // ``overflow: hidden`` and covers the bbox region with the dark
      // background; if the bbox is much shorter than the required text
      // area, the surrounding PDF original peeks through and looks like
      // a missing translation. Real fix is at extraction (Phase 6h-1),
      // but the warning sets the right mental model in the meantime.
      if (overlayMode === "translation" && hasBboxOverflow(text, w, h)) {
        el.classList.add("block--overflow-warning");
        el.title =
          "번역 영역이 짧음 — PDF 원문이 일부 노출될 수 있음 (Phase 6h fix 예정)";
      }
    }
  }

  // Pin display — multi-thread aware.
  if (threadsForBlock && threadsForBlock.length > 0) {
    el.dataset.hasThread = "true";
    if (threadsForBlock.length > 1) {
      el.dataset.threadCount = String(threadsForBlock.length);
    }
    // First thread title becomes the title tooltip; "+N more" appended if any.
    const first = threadsForBlock[0];
    let tip = first?.title || `block #${blockData.id}`;
    if (threadsForBlock.length > 1) {
      tip += ` (+${threadsForBlock.length - 1} more)`;
    }
    el.title = tip;
  }

  el.addEventListener("click", (e) => {
    e.stopPropagation();
    el.dispatchEvent(
      new CustomEvent("ht-lens:block-click", {
        detail: { blockId: blockData.id, blockData, threads: threadsForBlock },
        bubbles: true,
      }),
    );
  });

  // Phase 6b: hover sync across panes. Side-by-side both-mode shows the
  // same block twice (original + translation); the user should see both
  // outlined when hovering either one.
  el.addEventListener("mouseenter", () => syncBlockHover(blockData.id, true));
  el.addEventListener("mouseleave", () =>
    syncBlockHover(blockData.id, false),
  );

  // Phase 6a: contextmenu (right-click) for retranslate. Only text/header
  // blocks; the viewer decides whether to actually show the modal.
  el.addEventListener("contextmenu", (e) => {
    if (blockData.type !== "text" && blockData.type !== "header") return;
    e.preventDefault();
    e.stopPropagation();
    el.dispatchEvent(
      new CustomEvent("ht-lens:block-contextmenu", {
        detail: { blockId: blockData.id, blockData },
        bubbles: true,
      }),
    );
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

/** Phase 6h hot-fix: decide whether the bbox is too short for the rendered
 *  text. Uses the explicit newline count (lines authored in the source) and
 *  a ~16px-per-line baseline. Triggers when required height exceeds the
 *  bbox by more than 50% — the 1.5x threshold keeps false positives low
 *  while still catching the dominant Pattern A leaks documented in the
 *  Phase 6h diagnostic (multi-line section headers / table rows
 *  collapsed into single-line bboxes). */
function hasBboxOverflow(text, bboxW, bboxH) {
  if (!text || bboxH <= 0) return false;
  const explicitLines = (text.match(/\n/g) || []).length + 1;
  // Per-line baseline: 16px = comfortable Korean reading size (14) * 1.15
  // line-height. This deliberately under-estimates wrap-induced lines so
  // we only warn on bboxes that are structurally too short, not just
  // close to the fit limit.
  const requiredH = explicitLines * 16;
  return requiredH > bboxH * 1.5;
}

/** Phase 6b hover sync: toggle a ``block--hover-sync`` class on every block
 *  element that shares the same ``data-block-id``. The class drives the
 *  outline regardless of native ``:hover`` so the mirrored block in the
 *  other pane lights up too. */
function syncBlockHover(blockId, on) {
  const els = document.querySelectorAll(`.block[data-block-id="${blockId}"]`);
  for (const el of els) {
    el.classList.toggle("block--hover-sync", on);
  }
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
