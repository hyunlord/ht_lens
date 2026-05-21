"use strict";

/** Attach the viewer's keyboard handler. Returns a detach function. */
export function attachKeyboard(handlers) {
  const onKey = (e) => {
    // Don't capture keys while the user is typing.
    if (
      e.target &&
      typeof e.target.matches === "function" &&
      e.target.matches("input, textarea")
    ) {
      return;
    }
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
    } else if (e.key === "Home") {
      handlers.onFirst && handlers.onFirst();
    } else if (e.key === "End") {
      handlers.onLast && handlers.onLast();
    }
  };
  document.addEventListener("keydown", onKey);
  return () => document.removeEventListener("keydown", onKey);
}
