"use strict";

/** Tiny global state. ``zoom`` and ``overlayMode`` persist in localStorage.
 *  Doc/page indices are URL-driven (the URL is the source of truth). */

const ZOOM_STEPS = [0.5, 0.75, 1.0, 1.25, 1.5, 2.0];
const STORAGE_ZOOM = "ht_lens.zoom";
const STORAGE_OVERLAY = "ht_lens.overlay";

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

function safeWrite(key, value) {
  try {
    localStorage.setItem(key, String(value));
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
    idx === -1
      ? 1.0
      : ZOOM_STEPS[Math.min(ZOOM_STEPS.length - 1, idx + 1)];
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

export { ZOOM_STEPS };
