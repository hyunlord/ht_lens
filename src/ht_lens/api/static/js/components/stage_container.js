"use strict";

import { apiGet } from "../api.js";
import {
  clearPageData,
  setCurrentPage,
  setPageData,
  state,
} from "../state.js";
import { buildPanes, renderPane } from "./pane.js";

const FAR_PAGE_KEEP_RADIUS = 2; // mount window: currentPage ± 2
// Pages farther than this from currentPage get their block overlay unmounted.
const FAR_PAGE_UNMOUNT_RADIUS = 5;

/** Build placeholder rows for every page in the document. Heights are
 *  estimated from PageSummary so the scrollbar size is stable from frame 0.
 *  ``stageEl`` is the single scroll container (#stage).
 */
export function buildPlaceholderRows(stageEl, pageSummaries, zoom, viewMode) {
  stageEl.innerHTML = "";
  for (const summary of pageSummaries) {
    const row = document.createElement("div");
    row.className = "page-row";
    row.dataset.page = String(summary.page_num);
    row.dataset.rotation = String(summary.rotation || 0);
    row.dataset.mounted = "0";
    row.style.minHeight = `${estimateRowHeight(summary, zoom, viewMode)}px`;
    stageEl.appendChild(row);
  }
}

/** Estimate a row's height so the scrollbar stays accurate before the page
 *  is fetched. Side-by-side mode keeps the same vertical extent (panes are
 *  laid out horizontally), so the height does not change with viewMode.
 */
function estimateRowHeight(summary, zoom, _viewMode) {
  const px = summary?.render?.pixel_h || 1000;
  return Math.round(px * zoom + 24); // +24 for row gap/padding
}

/** A small map of page_num -> AbortController so an in-flight fetch can be
 *  cancelled when the page goes off-screen. */
const _abortByPage = new Map();
/** mountToken bumps per page to detect stale fetch resolutions. */
const _mountTokenByPage = new Map();
/** Set of page numbers currently mounted (overlay rendered). */
const _mountedPages = new Set();
/** Pending mount promises so navigateTo can await an in-flight mount. */
const _mountPromiseByPage = new Map();

function _bumpToken(pageNum) {
  const next = (_mountTokenByPage.get(pageNum) || 0) + 1;
  _mountTokenByPage.set(pageNum, next);
  return next;
}

/** Fetch + render a page if not already mounted. Returns a Promise that
 *  resolves once the page DOM is in place (img + blocks). Re-entry while a
 *  mount is in flight returns the same promise. */
export function mountPage(pageNum, ctx) {
  if (_mountedPages.has(pageNum)) return Promise.resolve();
  if (_mountPromiseByPage.has(pageNum)) return _mountPromiseByPage.get(pageNum);

  const promise = (async () => {
    const token = _bumpToken(pageNum);
    const controller = new AbortController();
    _abortByPage.set(pageNum, controller);
    try {
      const pageData = await apiGet(
        `/documents/${ctx.docId}/pages/${pageNum}`,
        { signal: controller.signal },
      );
      // Stale guard: token bumped or aborted — drop the result.
      if (_mountTokenByPage.get(pageNum) !== token) return;
      setPageData(pageNum, pageData);
      const row = ctx.stageEl.querySelector(
        `.page-row[data-page="${pageNum}"]`,
      );
      if (!row) return;
      renderRowContent(row, pageData, ctx);
      _mountedPages.add(pageNum);
      row.dataset.mounted = "1";
    } catch (err) {
      if (controller.signal.aborted || err.name === "AbortError") return;
      console.warn(`mountPage(${pageNum}) failed`, err);
    } finally {
      _abortByPage.delete(pageNum);
      _mountPromiseByPage.delete(pageNum);
    }
  })();
  _mountPromiseByPage.set(pageNum, promise);
  return promise;
}

/** Drop the block overlay for a far-off-screen page so the DOM stays
 *  bounded. Page metadata stays in state.pageDataById only until the row is
 *  unmounted (so subsequent mounts still hit cache). */
export function unmountPage(pageNum, ctx) {
  if (!_mountedPages.has(pageNum)) return;
  const controller = _abortByPage.get(pageNum);
  controller?.abort();
  _bumpToken(pageNum); // invalidate any late fetch resolution
  const row = ctx.stageEl.querySelector(`.page-row[data-page="${pageNum}"]`);
  if (row) {
    row.innerHTML = "";
    row.dataset.mounted = "0";
  }
  _mountedPages.delete(pageNum);
  clearPageData(pageNum);
}

/** Render the row's pane scaffold and populate each pane via renderPane. */
function renderRowContent(row, pageData, ctx) {
  const viewMode = state.viewModeActual;
  const panes = buildPanes(row, viewMode);
  for (const [side, container] of Object.entries(panes)) {
    renderPane(container, {
      doc: ctx.doc,
      page: pageData,
      side,
      zoom: state.zoom,
      overlayMode: viewMode,
      threadsByBlock: ctx.getThreadsByBlock?.() ?? null,
    });
  }
}

/** Repaint a single page row using the cached pageData (e.g. after retranslate
 *  or viewMode change). No-op if the page isn't mounted. */
export function repaintMountedPage(pageNum, ctx) {
  if (!_mountedPages.has(pageNum)) return;
  const pageData = state.pageDataById[pageNum];
  if (!pageData) return;
  const row = ctx.stageEl.querySelector(`.page-row[data-page="${pageNum}"]`);
  if (!row) return;
  renderRowContent(row, pageData, ctx);
}

/** Repaint every currently-mounted page (e.g. on view-mode toggle). */
export function repaintAllMountedPages(ctx) {
  for (const pageNum of _mountedPages) {
    repaintMountedPage(pageNum, ctx);
  }
}

/** Recompute placeholder heights for unmounted rows after zoom changes. */
export function resizePlaceholderRows(stageEl, pageSummaries, zoom, viewMode) {
  const byPage = new Map(pageSummaries.map((s) => [s.page_num, s]));
  for (const row of stageEl.querySelectorAll(".page-row")) {
    if (row.dataset.mounted === "1") continue;
    const summary = byPage.get(Number(row.dataset.page));
    if (!summary) continue;
    row.style.minHeight = `${estimateRowHeight(summary, zoom, viewMode)}px`;
  }
}

/** Initialise the intersection observer that drives lazy mount/unmount and
 *  tracks the currently-most-visible page. Returns a disconnect function. */
export function attachIntersectionObserver(stageEl, ctx) {
  // Track the most visible page for currentPage updates.
  const visibility = new Map();
  let urlReplaceTimer = null;

  const io = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        const pageNum = Number(entry.target.dataset.page);
        if (entry.isIntersecting) {
          visibility.set(pageNum, entry.intersectionRatio);
          // Mount target page + ±FAR_PAGE_KEEP_RADIUS around it.
          mountPage(pageNum, ctx);
        } else {
          visibility.delete(pageNum);
        }
      }
      // Compute the most-visible page among current entries.
      if (visibility.size > 0) {
        let bestPage = -1;
        let bestRatio = -1;
        for (const [page, ratio] of visibility) {
          if (ratio > bestRatio) {
            bestRatio = ratio;
            bestPage = page;
          }
        }
        if (bestPage > 0) {
          setCurrentPage(bestPage);
          // Phase 6b: pre-fetch ±KEEP_RADIUS neighbours.
          for (let d = 1; d <= FAR_PAGE_KEEP_RADIUS; d++) {
            mountPage(bestPage + d, ctx);
            mountPage(bestPage - d, ctx);
          }
          // Schedule unmount sweep + URL replaceState.
          scheduleFarPageUnmount(bestPage, ctx);
          if (urlReplaceTimer) clearTimeout(urlReplaceTimer);
          urlReplaceTimer = setTimeout(() => {
            ctx.onScrollPageChange?.(bestPage);
          }, 500);
        }
      }
    },
    {
      root: stageEl,
      rootMargin: "100% 0px 100% 0px",
      threshold: [0, 0.25, 0.5, 0.75, 1],
    },
  );

  for (const row of stageEl.querySelectorAll(".page-row")) {
    io.observe(row);
  }

  return () => {
    io.disconnect();
    if (urlReplaceTimer) clearTimeout(urlReplaceTimer);
  };
}

/** Unmount pages that are too far from the currently-visible page. */
function scheduleFarPageUnmount(currentPage, ctx) {
  for (const pageNum of Array.from(_mountedPages)) {
    if (Math.abs(pageNum - currentPage) > FAR_PAGE_UNMOUNT_RADIUS) {
      unmountPage(pageNum, ctx);
    }
  }
}

/** Smoothly scroll to a target page's row. Returns the row element (or null). */
export function scrollToPage(stageEl, pageNum, behavior = "smooth") {
  const row = stageEl.querySelector(`.page-row[data-page="${pageNum}"]`);
  if (!row) return null;
  row.scrollIntoView({ behavior, block: "start" });
  return row;
}

/** Wait for a block element to appear in the DOM (typically after a scroll
 *  triggered a lazy mount). Polls every 50ms up to ``timeoutMs``. */
export async function waitForBlockMounted(blockId, timeoutMs = 2000) {
  const t0 = performance.now();
  while (performance.now() - t0 < timeoutMs) {
    const el = document.querySelector(`[data-block-id="${blockId}"]`);
    if (el) return el;
    await new Promise((r) => setTimeout(r, 50));
  }
  return null;
}

/** Add a temporary flash highlight to the target block (and its mirror in
 *  the other pane if both are mounted). */
export function flashBlock(blockId) {
  const els = document.querySelectorAll(`[data-block-id="${blockId}"]`);
  for (const el of els) {
    el.classList.add("block--flash");
    setTimeout(() => el.classList.remove("block--flash"), 1500);
  }
}

/** Test-helper: mounted set + token map (consumed by jsdom tests). */
export function _internals() {
  return {
    mountedPages: _mountedPages,
    mountTokens: _mountTokenByPage,
    abortControllers: _abortByPage,
    mountPromises: _mountPromiseByPage,
  };
}
