"use strict";

const MAX_LENGTH = 4000;

/** Build a chat input form. ``onSubmit(content)`` is awaited; while it is
 *  in flight the form disables itself. Returns a `setBusy(bool)` helper. */
export function renderMessageInput(container, onSubmit) {
  container.innerHTML = "";
  const form = document.createElement("form");
  form.className = "message-input";

  const textarea = document.createElement("textarea");
  textarea.rows = 3;
  textarea.maxLength = MAX_LENGTH;
  textarea.placeholder =
    "질문을 입력하세요... (Ctrl/Cmd+Enter 전송, Enter 줄바꿈)";
  form.appendChild(textarea);

  const row = document.createElement("div");
  row.className = "message-input-row";
  const hint = document.createElement("span");
  hint.className = "hint";
  hint.textContent = "Ctrl/Cmd+Enter ↵";
  const btn = document.createElement("button");
  btn.type = "submit";
  btn.textContent = "전송";
  row.appendChild(hint);
  row.appendChild(btn);
  form.appendChild(row);

  function autoGrow() {
    textarea.style.height = "auto";
    const next = Math.min(textarea.scrollHeight, 220);
    textarea.style.height = `${next}px`;
  }

  textarea.addEventListener("input", autoGrow);
  textarea.addEventListener("keydown", (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
      e.preventDefault();
      form.requestSubmit();
    }
  });

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const value = textarea.value.trim();
    if (!value) return;
    if (value.length > MAX_LENGTH) return;
    btn.disabled = true;
    textarea.disabled = true;
    try {
      await onSubmit(value);
      textarea.value = "";
      autoGrow();
    } finally {
      btn.disabled = false;
      textarea.disabled = false;
      textarea.focus();
    }
  });

  container.appendChild(form);
  autoGrow();
  return {
    focus: () => textarea.focus(),
    setBusy: (busy) => {
      btn.disabled = Boolean(busy);
      textarea.disabled = Boolean(busy);
    },
  };
}
