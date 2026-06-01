// Phase 8d-2c — chat drawer width drag-resize + single-mode body coupling.
//
// The chat is a position:fixed right-edge drawer (8d-2a). Dragging its left
// handle resizes it; in SINGLE reading mode the reflow body's right margin
// follows the width so text isn't hidden under the drawer. In COMPARE mode the
// drawer OVERLAYS — no margin, so the 1fr|1fr PDF/reflow grid is never squeezed
// (challenge R9). Width persists in sessionStorage (NOT localStorage — viewer
// rule). Margin is applied as an inline style gated on mode+open here in JS (not
// a CSS selector) so the gating is directly testable under jsdom.

export const MIN_WIDTH = 280;
export const DEFAULT_WIDTH = 380;
export const MAX_VW_FRACTION = 0.6;
export const STORAGE_KEY = "htlens.chatWidth";

// Clamp to [MIN_WIDTH, 60vw]; on a narrow viewport MIN_WIDTH wins (drawer's own
// max-width:90vw caps the visual overflow).
export function clampWidth(px, viewportWidth) {
  const max = Math.max(MIN_WIDTH, Math.round((viewportWidth || 0) * MAX_VW_FRACTION));
  return Math.min(max, Math.max(MIN_WIDTH, Math.round(px)));
}

export function readStoredWidth(win) {
  try {
    const raw = win.sessionStorage.getItem(STORAGE_KEY);
    const n = raw == null ? NaN : Number(raw);
    return Number.isFinite(n) ? n : null;
  } catch {
    return null;
  }
}

// Set the drawer width (CSS var drives `.chat { width }`) and persist it.
export function applyChatWidth(px, { doc, win }) {
  doc.documentElement.style.setProperty("--chat-w", `${px}px`);
  try {
    win.sessionStorage.setItem(STORAGE_KEY, String(px));
  } catch {
    /* sessionStorage may throw in private mode — width still applies visually */
  }
}

// Couple the reflow body's right margin to the drawer — ONLY single mode while
// the chat is open. Compare mode (overlay) or a closed drawer clears it (R9).
export function syncPaneMargin({ doc }) {
  const pane = doc.querySelector(".pane--reflow");
  if (!pane) return "";
  const layout = doc.querySelector(".layout");
  const chat = doc.querySelector("#chat");
  const single = !layout || layout.dataset.mode === "single";
  const open = chat != null && !chat.hasAttribute("hidden");
  if (single && open) {
    const w = doc.documentElement.style.getPropertyValue("--chat-w") || `${DEFAULT_WIDTH}px`;
    pane.style.marginRight = w;
    return w;
  }
  pane.style.marginRight = ""; // compare overlay OR closed → clear
  return "";
}

// Wire the `.chat-resizer` drag handle, restore persisted width, and return a
// { refresh } handle so the chat toggle / mode switch can re-sync the margin.
export function initResize({ doc, win }) {
  const stored = readStoredWidth(win);
  const initial = clampWidth(stored == null ? DEFAULT_WIDTH : stored, win.innerWidth);
  applyChatWidth(initial, { doc, win });
  syncPaneMargin({ doc });

  const resizer = doc.querySelector(".chat-resizer");
  if (resizer && resizer.addEventListener) {
    let startX = 0;
    let startW = initial;
    let dragging = false;
    const onMove = (e) => {
      if (!dragging) return;
      // Drawer sits on the right edge: dragging the handle LEFT widens it.
      const next = clampWidth(startW - (e.clientX - startX), win.innerWidth);
      applyChatWidth(next, { doc, win });
      syncPaneMargin({ doc });
    };
    const onUp = () => {
      dragging = false;
      doc.removeEventListener("pointermove", onMove);
      doc.removeEventListener("pointerup", onUp);
    };
    resizer.addEventListener("pointerdown", (e) => {
      dragging = true;
      startX = e.clientX;
      startW = parseInt(doc.documentElement.style.getPropertyValue("--chat-w"), 10) || initial;
      doc.addEventListener("pointermove", onMove);
      doc.addEventListener("pointerup", onUp);
      if (e.preventDefault) e.preventDefault();
    });
  }
  return { refresh: () => syncPaneMargin({ doc }) };
}
