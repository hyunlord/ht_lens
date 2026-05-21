"use strict";

/** Tiny global state.
 *
 * - ``zoom``, ``overlayMode``, ``sidebarTab``, ``panelOpen``, ``activeBlockId``,
 *   ``activeThreadId`` persist in localStorage so reload restores the view.
 * - doc/page are URL-driven (the URL is the source of truth).
 * - ``threadsByDoc`` and ``threadDetailById`` are runtime caches refreshed by
 *   server refetches; never persisted.
 */

const ZOOM_STEPS = [0.5, 0.75, 1.0, 1.25, 1.5, 2.0];
const STORAGE_ZOOM = "ht_lens.zoom";
const STORAGE_OVERLAY = "ht_lens.overlay";
const STORAGE_SIDEBAR_TAB = "ht_lens.sidebarTab";
const STORAGE_PANEL_OPEN = "ht_lens.panelOpen";
const STORAGE_ACTIVE_BLOCK = "ht_lens.activeBlockId";
const STORAGE_ACTIVE_THREAD = "ht_lens.activeThreadId";

function safeReadFloat(key, fallback) {
  try {
    const raw = localStorage.getItem(key);
    if (raw === null) return fallback;
    const v = parseFloat(raw);
    return Number.isFinite(v) ? v : fallback;
  } catch (_e) {
    return fallback;
  }
}

function safeReadString(key, fallback) {
  try {
    return localStorage.getItem(key) || fallback;
  } catch (_e) {
    return fallback;
  }
}

function safeReadInt(key) {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return null;
    const v = parseInt(raw, 10);
    return Number.isFinite(v) && v > 0 ? v : null;
  } catch (_e) {
    return null;
  }
}

function safeReadBool(key, fallback) {
  try {
    const raw = localStorage.getItem(key);
    if (raw === null) return fallback;
    return raw === "1" || raw === "true";
  } catch (_e) {
    return fallback;
  }
}

function safeWrite(key, value) {
  try {
    if (value === null || value === undefined) {
      localStorage.removeItem(key);
    } else {
      localStorage.setItem(key, String(value));
    }
  } catch (_e) {
    /* ignore — private mode or quota */
  }
}

function snapToStep(z) {
  return ZOOM_STEPS.reduce((best, s) =>
    Math.abs(s - z) < Math.abs(best - z) ? s : best,
  );
}

export const state = {
  // Snap on init so a stale or hand-edited localStorage value can't render a
  // non-step zoom on first paint.
  zoom: snapToStep(safeReadFloat(STORAGE_ZOOM, 1.0)),
  overlayMode: (() => {
    const v = safeReadString(STORAGE_OVERLAY, "translation");
    return v === "original" || v === "translation" ? v : "translation";
  })(),
  // Phase 5 additions
  sidebarTab: (() => {
    const v = safeReadString(STORAGE_SIDEBAR_TAB, "pages");
    return v === "questions" || v === "pages" ? v : "pages";
  })(),
  panelOpen: safeReadBool(STORAGE_PANEL_OPEN, false),
  activeBlockId: safeReadInt(STORAGE_ACTIVE_BLOCK),
  activeThreadId: safeReadInt(STORAGE_ACTIVE_THREAD),
  // Runtime caches — do NOT persist.
  threadsByDoc: {}, // { [docId]: Thread[] }
  threadDetailById: {}, // { [threadId]: ThreadDetail (full incl. messages) }
  loadingMessage: false,
  panelToken: 0, // bumped on every panel async op to cancel stale results
  listeners: new Set(),
};

/** Subscribe to state changes. Returns an unsubscribe function. */
export function subscribe(fn) {
  state.listeners.add(fn);
  return () => state.listeners.delete(fn);
}

function notify() {
  for (const fn of state.listeners) fn(state);
}

/** Set zoom to the nearest step. */
export function setZoom(z) {
  const clamped = snapToStep(z);
  state.zoom = clamped;
  safeWrite(STORAGE_ZOOM, clamped);
  notify();
}

/** Bump zoom up one step (capped at the largest step). */
export function zoomIn() {
  const idx = ZOOM_STEPS.indexOf(state.zoom);
  const next =
    idx === -1 ? 1.0 : ZOOM_STEPS[Math.min(ZOOM_STEPS.length - 1, idx + 1)];
  setZoom(next);
}

/** Bump zoom down one step. */
export function zoomOut() {
  const idx = ZOOM_STEPS.indexOf(state.zoom);
  const next = idx === -1 ? 1.0 : ZOOM_STEPS[Math.max(0, idx - 1)];
  setZoom(next);
}

/** Flip translation <-> original. */
export function toggleOverlay() {
  state.overlayMode =
    state.overlayMode === "translation" ? "original" : "translation";
  safeWrite(STORAGE_OVERLAY, state.overlayMode);
  notify();
}

/** Phase 5: switch sidebar tab and persist. */
export function setSidebarTab(tab) {
  if (tab !== "pages" && tab !== "questions") return;
  state.sidebarTab = tab;
  safeWrite(STORAGE_SIDEBAR_TAB, tab);
  notify();
}

/** Phase 5: open the chat panel for a block (and possibly a thread). */
export function openPanel({ blockId, threadId = null }) {
  state.panelOpen = true;
  state.activeBlockId = blockId ?? null;
  state.activeThreadId = threadId;
  state.panelToken++;
  safeWrite(STORAGE_PANEL_OPEN, "1");
  safeWrite(STORAGE_ACTIVE_BLOCK, blockId ?? null);
  safeWrite(STORAGE_ACTIVE_THREAD, threadId);
  notify();
}

/** Phase 5: close the chat panel. */
export function closePanel() {
  state.panelOpen = false;
  state.activeBlockId = null;
  state.activeThreadId = null;
  state.panelToken++;
  safeWrite(STORAGE_PANEL_OPEN, "0");
  safeWrite(STORAGE_ACTIVE_BLOCK, null);
  safeWrite(STORAGE_ACTIVE_THREAD, null);
  notify();
}

/** Cache helper: replace the thread-list snapshot for a document. */
export function setThreadsForDoc(docId, threads) {
  state.threadsByDoc[docId] = threads;
  notify();
}

/** Cache helper: store/replace a full thread detail (incl. messages). */
export function setThreadDetail(detail) {
  state.threadDetailById[detail.id] = detail;
  notify();
}

/** Cache helper: replace activeThreadId persisted state. */
export function setActiveThreadId(id) {
  state.activeThreadId = id;
  safeWrite(STORAGE_ACTIVE_THREAD, id);
  notify();
}

export function setLoadingMessage(flag) {
  state.loadingMessage = Boolean(flag);
  notify();
}

export { ZOOM_STEPS };
