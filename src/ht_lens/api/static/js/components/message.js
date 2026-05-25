"use strict";

import { renderMarkdown } from "../utils/render_markdown.js";
import { getRelatedBlocksForMessage } from "../state.js";

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

  // Phase 7a: render cross-doc references the LLM used in its context.
  // The /explain and /messages responses carry ``related_blocks``, but
  // the subsequent ``GET /threads/{id}`` reload rebuilds messages from
  // ORM rows and drops the computed-per-response field. Fall back to
  // the runtime cache in state.js (Phase 7a R1 verify-cross fix).
  if (msg.role === "assistant") {
    const refs = Array.isArray(msg.related_blocks) && msg.related_blocks.length > 0
      ? msg.related_blocks
      : getRelatedBlocksForMessage(msg.id);
    if (refs && refs.length > 0) {
      renderRelatedBlocks(wrap, refs);
    }
  }

  container.appendChild(wrap);
  return wrap;
}

/** Render the "다른 책의 관련 부분" section under an assistant message
 *  (Phase 7a / ROADMAP DoD ④). */
function renderRelatedBlocks(container, refs) {
  const section = document.createElement("section");
  section.className = "related-blocks";

  const heading = document.createElement("h4");
  heading.className = "related-blocks-title";
  heading.textContent = `다른 책의 관련 부분 (${refs.length})`;
  section.appendChild(heading);

  const list = document.createElement("ul");
  list.className = "related-blocks-list";
  for (const r of refs) {
    const li = document.createElement("li");
    li.className = "related-block";

    const head = document.createElement("div");
    head.className = "related-head";
    const docName = document.createElement("span");
    docName.className = "related-doc";
    docName.textContent = String(r.doc_filename || "");
    head.appendChild(docName);
    const page = document.createElement("span");
    page.className = "related-page";
    page.textContent = `p.${r.page_num}`;
    head.appendChild(page);
    const score = document.createElement("span");
    score.className = "related-score";
    score.textContent = `score ${(r.score ?? 0).toFixed(2)}`;
    head.appendChild(score);
    li.appendChild(head);

    if (r.original_preview) {
      const orig = document.createElement("div");
      orig.className = "related-original";
      orig.textContent = r.original_preview;
      li.appendChild(orig);
    }
    if (r.translated_preview) {
      const tr = document.createElement("div");
      tr.className = "related-translated";
      tr.textContent = r.translated_preview;
      li.appendChild(tr);
    }

    // Open the related block's viewer page in a new tab.
    // Phase 7a R1 fix (Codex verify-cross §4 #2): viewer.js
    // parseQuery() only honors ?doc=&page=&block= query params; the
    // earlier ``#block-N`` fragment was silently ignored and the
    // viewer landed on the page without highlighting the block.
    const link = document.createElement("a");
    link.className = "related-open";
    link.href = `/static/viewer.html?doc=${r.doc_id}&page=${r.page_num}&block=${r.block_id}`;
    link.target = "_blank";
    link.rel = "noopener";
    link.textContent = "→ 열기";
    li.appendChild(link);

    list.appendChild(li);
  }
  section.appendChild(list);
  container.appendChild(section);
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
