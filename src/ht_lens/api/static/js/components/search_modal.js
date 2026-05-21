"use strict";

import DOMPurifyFactory from "../../vendor/purify.es.mjs";

// Reuse the browser-bound DOMPurify (Phase 5 vendor) but with a tiny
// whitelist: only <mark> survives the sanitiser. Everything else is
// stripped before insertion.
const DOMPurify =
  typeof globalThis.window === "object" && globalThis.window
    ? DOMPurifyFactory.sanitize
      ? DOMPurifyFactory
      : DOMPurifyFactory(globalThis.window)
    : DOMPurifyFactory(globalThis.window || globalThis);

const SANITIZE_OPTS = {
  ALLOWED_TAGS: ["mark"],
  ALLOWED_ATTR: [],
};

/** Render the search modal into ``container`` based on ``ctx``.
 *  ``callbacks``: { onClose, onSelect(hit), onQueryChange(value), onMove(delta) }
 */
export function renderSearchModal(container, ctx, callbacks) {
  container.innerHTML = "";
  container.classList.add("search-modal");
  container.setAttribute("role", "dialog");
  container.setAttribute("aria-modal", "true");
  container.setAttribute("aria-label", "전체 검색");

  const backdrop = document.createElement("div");
  backdrop.className = "search-modal-backdrop";
  backdrop.addEventListener("click", () => callbacks.onClose?.());
  container.appendChild(backdrop);

  const card = document.createElement("div");
  card.className = "search-modal-card";
  container.appendChild(card);

  const input = document.createElement("input");
  input.type = "text";
  input.className = "search-input";
  input.placeholder = "원문 / 번역 검색 (Esc로 닫기, ↑↓로 이동, Enter 점프)";
  input.autocomplete = "off";
  input.spellcheck = false;
  input.value = ctx.query || "";
  input.addEventListener("input", () => callbacks.onQueryChange?.(input.value));
  input.addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      callbacks.onMove?.(1);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      callbacks.onMove?.(-1);
    } else if (e.key === "Enter") {
      const hit = ctx.results?.[ctx.selected ?? 0];
      if (hit) callbacks.onSelect?.(hit);
    }
  });
  card.appendChild(input);

  const status = document.createElement("div");
  status.className = "search-status";
  if (ctx.loading) {
    status.textContent = "검색 중...";
  } else if (ctx.error) {
    status.textContent = `검색 오류: ${ctx.error}`;
    status.classList.add("error");
  } else if (!ctx.query || ctx.query.trim().length < 2) {
    status.textContent = "두 글자 이상 입력하세요.";
  } else if (!ctx.results || ctx.results.length === 0) {
    status.textContent = "결과 없음";
  } else {
    status.textContent = `${ctx.results.length}개 결과`;
  }
  card.appendChild(status);

  if (ctx.results && ctx.results.length > 0) {
    const list = document.createElement("ol");
    list.className = "search-results";
    list.setAttribute("role", "listbox");
    for (let i = 0; i < ctx.results.length; i++) {
      const hit = ctx.results[i];
      const li = document.createElement("li");
      li.className = "search-result";
      li.setAttribute("role", "option");
      if (i === (ctx.selected ?? 0)) {
        li.classList.add("search-result--selected");
        li.setAttribute("aria-selected", "true");
      }
      const head = document.createElement("div");
      head.className = "search-result-head";
      head.textContent = `${hit.doc_filename} · p.${hit.page_num} · ${hit.block_local_id} (${hit.matched_field})`;
      li.appendChild(head);
      const preview = document.createElement("div");
      preview.className = "search-result-preview";
      // hit.preview already comes with the safe ``<mark>`` wrap; the
      // sanitiser keeps only ``<mark>`` and strips everything else.
      preview.innerHTML = DOMPurify.sanitize(hit.preview || "", SANITIZE_OPTS);
      li.appendChild(preview);
      li.addEventListener("click", () => callbacks.onSelect?.(hit));
      list.appendChild(li);
    }
    card.appendChild(list);
  }

  queueMicrotask(() => input.focus());
  return { focusInput: () => input.focus() };
}
