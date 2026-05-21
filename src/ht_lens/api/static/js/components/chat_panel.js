"use strict";

import {
  renderErrorMessage,
  renderLoadingMessage,
  renderMessage,
} from "./message.js";
import { renderMessageInput } from "./message_input.js";

/** Render the chat panel.
 *
 *  ``ctx`` carries the active block + thread snapshot:
 *    { block: BlockRead | null,
 *      thread: ThreadDetail | null,  // null when no thread exists yet
 *      loading: bool,                // request in flight
 *      error: string | null,
 *    }
 *  ``callbacks``: { onExplain, onSubmit, onClose, onRetry }
 *
 *  This component is dumb: viewer.js owns the state machine and calls
 *  ``renderChatPanel`` whenever the snapshot changes.
 */
export function renderChatPanel(container, ctx, callbacks) {
  container.innerHTML = "";
  container.classList.add("chat-panel");

  // Header: block preview + close button
  const header = document.createElement("header");
  header.className = "chat-panel-head";
  const preview = document.createElement("div");
  preview.className = "block-preview";
  if (ctx.block) {
    const orig = document.createElement("div");
    orig.className = "block-original";
    orig.textContent = ctx.block.original_text || "[빈 블록]";
    preview.appendChild(orig);
    if (ctx.block.translated_text) {
      const tr = document.createElement("div");
      tr.className = "block-translated";
      tr.textContent = ctx.block.translated_text;
      preview.appendChild(tr);
    }
  } else {
    preview.textContent = "block을 선택하세요";
  }
  header.appendChild(preview);

  const closeBtn = document.createElement("button");
  closeBtn.type = "button";
  closeBtn.className = "chat-close";
  closeBtn.title = "패널 닫기 (Esc)";
  closeBtn.textContent = "×";
  closeBtn.addEventListener("click", () => callbacks.onClose?.());
  header.appendChild(closeBtn);
  container.appendChild(header);

  // Messages
  const main = document.createElement("main");
  main.className = "chat-messages";
  const messages = ctx.thread?.messages || [];
  for (const m of messages) {
    renderMessage(main, m);
  }
  if (ctx.loading) {
    renderLoadingMessage(main);
  }
  if (ctx.error) {
    renderErrorMessage(main, ctx.error, callbacks.onRetry);
  }
  container.appendChild(main);

  // Footer: either the explain button (empty thread) or the message input.
  const footer = document.createElement("footer");
  footer.className = "chat-footer";

  const hasExplain = messages.some(
    (m) => m.role === "user" && m.content?.includes("자세히 설명해주세요"),
  );

  if (!hasExplain && !ctx.loading) {
    // First-time CTA: explain button is allowed at most once per thread.
    const explainBtn = document.createElement("button");
    explainBtn.type = "button";
    explainBtn.className = "explain-btn";
    explainBtn.textContent = "✨ AI에게 설명 요청";
    explainBtn.disabled = !ctx.block;
    explainBtn.addEventListener("click", () => callbacks.onExplain?.());
    footer.appendChild(explainBtn);
  }

  // Always show the input. The submit button is what guards re-entry; once a
  // thread exists, the explain CTA disappears but the user can still ask.
  const inputContainer = document.createElement("div");
  inputContainer.className = "chat-input-wrap";
  footer.appendChild(inputContainer);
  container.appendChild(footer);

  const inputApi = renderMessageInput(inputContainer, async (text) => {
    await callbacks.onSubmit?.(text);
  });
  if (ctx.loading) inputApi.setBusy(true);

  // Scroll to bottom on every paint unless the user is mid-scroll up.
  // The "user actively scrolling up" check uses scrollTop vs scrollHeight.
  queueMicrotask(() => {
    const dist = main.scrollHeight - main.scrollTop - main.clientHeight;
    if (dist < 80) {
      main.scrollTop = main.scrollHeight;
    }
  });

  return { inputApi };
}
