"use strict";

// ht_lens 2.0 reflow chat panel (Phase 8d-2a).
//
// Two selection modes drive the chat anchor:
// - paragraph: clicking a .chunk → anchor_type='chunk' (that chunk + ±radius).
// - section: the 8d-1 ``sectionselect`` event → anchor_type='section', anchored
//   to the heading chunk id (challenge R1; the server derives the range).
// A question creates a /v2/thread for the current selection (once) then posts
// messages. Assistant text is rendered with the vendored marked + DOMPurify
// (render_markdown.js), so HTML/script payloads are sanitised (challenge R7).
// Self-contained module — reflow.js only calls initChat() (R10).

import { applyMath, renderMarkdown } from "./utils/render_markdown.js";

const $ = (id) => document.getElementById(id);

let docId = null;
let selection = null; // { type: 'chunk'|'section', chunkId, label }
let threadId = null; // reset whenever the selection changes → new context

/** Update the current chat anchor + the status line. Exported for tests. */
export function setSelection(sel) {
  selection = sel;
  threadId = null; // new selection → new backend thread
  const status = $("chat-status");
  if (status) {
    status.textContent = sel
      ? `${sel.type === "section" ? "섹션" : "문단"} 선택: ${sel.label}`
      : "선택된 항목 없음";
  }
  // Clear the visible transcript so a new selection never shows another
  // anchor's conversation while posting to a fresh thread (verify-cross R1).
  const messages = $("chat-messages");
  if (messages) messages.replaceChildren();
}

/** Render assistant markdown into a sanitised bubble (challenge R7). */
export function renderAssistant(container, text) {
  const bubble = document.createElement("div");
  bubble.className = "msg msg--assistant";
  bubble.innerHTML = renderMarkdown(text); // DOMPurify-sanitised
  applyMath(bubble);
  container.appendChild(bubble);
  return bubble;
}

function appendUser(container, text) {
  const b = document.createElement("div");
  b.className = "msg msg--user";
  b.textContent = text; // user text is never HTML
  container.appendChild(b);
}

async function ensureThread() {
  if (threadId != null) return threadId;
  if (!selection) return null;
  const r = await fetch("/v2/threads", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      doc_id: docId,
      anchor_type: selection.type,
      chunk_id: Number(selection.chunkId),
    }),
  });
  if (!r.ok) throw new Error(`thread ${r.status}`);
  threadId = (await r.json()).id;
  return threadId;
}

async function ask(question) {
  const messages = $("chat-messages");
  if (!selection) {
    const hint = document.createElement("div");
    hint.className = "msg msg--err";
    hint.textContent = "먼저 문단이나 목차의 섹션을 선택하세요.";
    messages.appendChild(hint);
    return;
  }
  appendUser(messages, question);
  try {
    const tid = await ensureThread();
    const r = await fetch(`/v2/threads/${tid}/messages`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content: question }),
    });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    renderAssistant(messages, (await r.json()).content);
  } catch (e) {
    const err = document.createElement("div");
    err.className = "msg msg--err";
    err.textContent = `오류: ${e.message}`;
    messages.appendChild(err);
  }
}

async function pinCurrent() {
  if (!selection) return;
  await fetch("/v2/pins", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ doc_id: docId, chunk_id: Number(selection.chunkId) }),
  });
  loadPins();
}

async function loadPins() {
  const box = $("chat-pins");
  if (!box || docId == null) return;
  try {
    const r = await fetch(`/v2/documents/${docId}/pins`, { cache: "no-store" });
    if (!r.ok) return;
    const pins = await r.json();
    box.replaceChildren();
    for (const p of pins) {
      const a = document.createElement("a");
      a.className = "pin-link";
      a.textContent = `📌 chunk ${p.chunk_id}`;
      a.dataset.chunkId = String(p.chunk_id);
      a.addEventListener("click", () => {
        const el = document.querySelector(`.chunk[data-chunk-id="${p.chunk_id}"]`);
        if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
      });
      box.appendChild(a);
    }
  } catch {
    /* pins are best-effort */
  }
}

/** Wire the panel against a document + the reflow content element. */
export function initChat({ docId: id, contentEl }) {
  docId = id;
  // paragraph selection (ignore citation/ref clicks — those jump, not select)
  contentEl.addEventListener("click", (e) => {
    if (e.target.closest(".rf-ref")) return;
    const chunk = e.target.closest(".chunk");
    if (chunk && chunk.dataset.chunkId) {
      setSelection({
        type: "chunk",
        chunkId: chunk.dataset.chunkId,
        label: `#${chunk.dataset.chunkId}`,
      });
    }
  });
  // section selection (8d-1 event → heading chunk anchor)
  contentEl.addEventListener("sectionselect", (e) => {
    setSelection({
      type: "section",
      chunkId: e.detail.headingChunkId,
      label: e.detail.secNo || "섹션",
    });
  });
  const form = $("chat-form");
  if (form) {
    form.addEventListener("submit", (e) => {
      e.preventDefault();
      const inp = $("chat-input");
      const q = (inp.value || "").trim();
      if (q) {
        inp.value = "";
        ask(q);
      }
    });
  }
  const pinBtn = $("chat-pin");
  if (pinBtn) pinBtn.addEventListener("click", pinCurrent);
  const toggle = $("chat-toggle");
  const panel = $("chat");
  if (toggle && panel) {
    toggle.addEventListener("click", () => {
      const opening = panel.hasAttribute("hidden");
      if (opening) panel.removeAttribute("hidden");
      else panel.setAttribute("hidden", "");
      toggle.setAttribute("aria-expanded", String(opening));
    });
  }
  loadPins();
}

export { ask, loadPins, pinCurrent };
