"use strict";

/** Attach the viewer's keyboard handler. Returns a detach function.
 *
 *  Phase 5 additions:
 *  - ``Esc``: ``onClosePanel`` (panel close)
 *  - ``Cmd/Ctrl+B``: ``onTogglePanel`` (panel toggle)
 *  Esc fires even when the focus is inside the chat textarea (it's the
 *  panel close shortcut). Other shortcuts still skip input/textarea.
 */
export function attachKeyboard(handlers) {
  const onKey = (e) => {
    const typing =
      e.target &&
      typeof e.target.matches === "function" &&
      e.target.matches("input, textarea");

    // Esc is always honoured — even while typing, since the user expects
    // it to close the panel.
    if (e.key === "Escape") {
      handlers.onClosePanel && handlers.onClosePanel();
      return;
    }

    if (typing) return;
    const meta = e.metaKey || e.ctrlKey;
    if (e.key === "ArrowLeft") {
      handlers.onPrev && handlers.onPrev();
    } else if (e.key === "ArrowRight") {
      handlers.onNext && handlers.onNext();
    } else if (e.key === "t" || e.key === "T") {
      handlers.onToggle && handlers.onToggle();
    } else if (meta && e.key === "ArrowUp") {
      e.preventDefault();
      handlers.onZoomIn && handlers.onZoomIn();
    } else if (meta && e.key === "ArrowDown") {
      e.preventDefault();
      handlers.onZoomOut && handlers.onZoomOut();
    } else if (meta && (e.key === "b" || e.key === "B")) {
      e.preventDefault();
      handlers.onTogglePanel && handlers.onTogglePanel();
    } else if (e.key === "Home") {
      handlers.onFirst && handlers.onFirst();
    } else if (e.key === "End") {
      handlers.onLast && handlers.onLast();
    }
  };
  document.addEventListener("keydown", onKey);
  return () => document.removeEventListener("keydown", onKey);
}
