"use strict";

/** Render a minimal confirmation modal. Returns a function to close it.
 *  ``opts`` = { title, message, detail (optional small text), confirmLabel,
 *  cancelLabel, onConfirm, onCancel }. */
export function renderConfirmModal(opts) {
  const root = document.createElement("div");
  root.className = "confirm-modal";
  root.setAttribute("role", "dialog");
  root.setAttribute("aria-modal", "true");

  const backdrop = document.createElement("div");
  backdrop.className = "confirm-modal-backdrop";
  root.appendChild(backdrop);

  const card = document.createElement("div");
  card.className = "confirm-modal-card";

  const title = document.createElement("h3");
  title.textContent = opts.title || "확인";
  card.appendChild(title);

  if (opts.message) {
    const msg = document.createElement("p");
    msg.textContent = opts.message;
    card.appendChild(msg);
  }
  if (opts.detail) {
    const det = document.createElement("small");
    det.textContent = opts.detail;
    card.appendChild(det);
  }

  const actions = document.createElement("div");
  actions.className = "confirm-actions";
  const cancel = document.createElement("button");
  cancel.type = "button";
  cancel.className = "btn-cancel";
  cancel.textContent = opts.cancelLabel || "취소";
  const confirm = document.createElement("button");
  confirm.type = "button";
  confirm.className = "btn-confirm";
  confirm.textContent = opts.confirmLabel || "확인";
  actions.appendChild(cancel);
  actions.appendChild(confirm);
  card.appendChild(actions);
  root.appendChild(card);

  function close() {
    root.remove();
  }

  cancel.addEventListener("click", () => {
    opts.onCancel?.();
    close();
  });
  backdrop.addEventListener("click", () => {
    opts.onCancel?.();
    close();
  });
  confirm.addEventListener("click", () => {
    opts.onConfirm?.();
    close();
  });

  document.body.appendChild(root);
  queueMicrotask(() => confirm.focus());
  return close;
}
