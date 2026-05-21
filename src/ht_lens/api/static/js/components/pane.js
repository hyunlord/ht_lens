"use strict";

import { renderPageView } from "./page_view.js";

/** Create or replace the contents of a single pane (one side of the page
 *  row). A pane is a thin wrapper around ``renderPageView`` that pins it to
 *  one side and lets the layered viewer compose 1 or 2 panes per page.
 *
 *  In ``viewMode === "both"`` we render TWO panes for the same page — the
 *  left one with ``side: "original"`` (overlay shows original text) and the
 *  right with ``side: "translation"``. In ``translation`` / ``original``
 *  viewMode we render one pane whose overlay matches the mode.
 *
 *  Phase 4/5/6a contracts preserved: pin markers, ``data-fallback``,
 *  ``data-mode``, rotation-banner all come from ``renderBlock`` /
 *  ``renderPageView`` unchanged.
 */
export function renderPane(container, ctx) {
  const { doc, page, side, zoom, threadsByBlock } = ctx;
  // Reuse renderPageView's DOM with the side hint so its overlay forces the
  // right text. overlayMode passes through for non-side (single-pane) calls.
  renderPageView(container, doc, page, ctx.overlayMode || side, zoom, threadsByBlock, {
    side,
  });
}

/** Build the dual-pane DOM scaffold for a page row, returning the inner
 *  pane containers. ``viewMode`` decides whether 1 or 2 panes are created.
 *  The page bg/overlay rendering is left to the caller (so it can defer
 *  until page data is fetched).
 */
export function buildPanes(rowEl, viewMode) {
  rowEl.innerHTML = "";
  if (viewMode === "both") {
    const left = document.createElement("div");
    left.className = "pane pane-original";
    left.dataset.side = "original";
    rowEl.appendChild(left);
    const right = document.createElement("div");
    right.className = "pane pane-translation";
    right.dataset.side = "translation";
    rowEl.appendChild(right);
    return { original: left, translation: right };
  }
  // Single pane fits the full row width.
  const single = document.createElement("div");
  single.className = `pane pane-${viewMode}`;
  single.dataset.side = viewMode;
  rowEl.appendChild(single);
  return { [viewMode]: single };
}
