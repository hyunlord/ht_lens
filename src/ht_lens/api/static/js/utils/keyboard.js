"use strict";

/** Attach the viewer's keyboard handler. Returns a detach function.
 *
 *  Phase 5 additions:
 *  - ``Esc``: ``onClosePanel`` (panel close)
 *  - ``Cmd/Ctrl+B``: ``onTogglePanel`` (panel toggle)
 *  Esc fires even when the focus is inside the chat textarea.
 *
 *  Phase 6a additions:
 *  - ``Cmd/Ctrl+K``: ``onOpenSearch`` (search modal). Fires even from inside
 *    chat input/textarea so the global shortcut is always available.
 *  - ``Esc`` ordering: when ``isSearchOpen()`` returns true, ``onCloseSearch``
 *    is called instead of ``onClosePanel``. This keeps the layered modals
 *    (search > panel) behaving in LIFO order.
 */
export function attachKeyboard(handlers) {
  const onKey = (e) => {
    const typing =
      e.target &&
      typeof e.target.matches === "function" &&
      e.target.matches("input, textarea");

    const meta = e.metaKey || e.ctrlKey;

    // Cmd/Ctrl+K opens the search modal from anywhere, including the chat
    // input — power users type in any context.
    if (meta && (e.key === "k" || e.key === "K")) {
      e.preventDefault();
      handlers.onOpenSearch && handlers.onOpenSearch();
      return;
    }

    // Esc: search modal > panel. The handler decides which is open.
    if (e.key === "Escape") {
      if (
        typeof handlers.isSearchOpen === "function" &&
        handlers.isSearchOpen()
      ) {
        handlers.onCloseSearch && handlers.onCloseSearch();
      } else {
        handlers.onClosePanel && handlers.onClosePanel();
      }
      return;
    }

    if (typing) return;
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
