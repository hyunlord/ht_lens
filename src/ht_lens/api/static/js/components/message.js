"use strict";

import { renderMarkdown } from "../utils/render_markdown.js";

/** Render a single message into ``container``. ``role === 'assistant'`` goes
 *  through the markdown pipeline; user messages stay plain text to avoid any
 *  user-content HTML interpretation. */
export function renderMessage(container, msg) {
  const wrap = document.createElement("article");
  wrap.className = `message message--${msg.role}`;
  wrap.dataset.messageId = String(msg.id);

  const head = document.createElement("header");
  head.className = "message-head";
  const roleEl = document.createElement("span");
  roleEl.className = "role";
  roleEl.textContent = msg.role === "assistant" ? "AI" : "나";
  head.appendChild(roleEl);
  if (msg.model) {
    const model = document.createElement("span");
    model.className = "model";
    model.textContent = msg.model;
    head.appendChild(model);
  }
  wrap.appendChild(head);

  const body = document.createElement("div");
  body.className = "message-body";
  if (msg.role === "assistant") {
    body.innerHTML = renderMarkdown(msg.content || "");
  } else {
    // user / system content: plain text so user input cannot inject HTML.
    body.textContent = msg.content || "";
  }
  wrap.appendChild(body);
  container.appendChild(wrap);
  return wrap;
}

/** Skeleton "AI is thinking" placeholder shown while a request is in flight. */
export function renderLoadingMessage(container) {
  const el = document.createElement("article");
  el.className = "message message--assistant message--loading";
  el.innerHTML = `
    <header class="message-head"><span class="role">AI</span></header>
    <div class="message-body">
      <span class="spinner" aria-hidden="true"></span>
      <span class="loading-text">AI가 응답 중...</span>
    </div>
  `;
  container.appendChild(el);
  return el;
}

/** Inline error row + retry button. ``onRetry`` is invoked when clicked. */
export function renderErrorMessage(container, errText, onRetry) {
  const el = document.createElement("article");
  el.className = "message message--error";
  const body = document.createElement("div");
  body.className = "message-body";
  body.textContent = errText || "AI 응답 실패. 다시 시도하세요.";
  el.appendChild(body);
  if (typeof onRetry === "function") {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "retry-btn";
    btn.textContent = "재시도";
    btn.addEventListener("click", onRetry);
    el.appendChild(btn);
  }
  container.appendChild(el);
  return el;
}
