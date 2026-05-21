"use strict";

import { renderThreadList } from "./thread_list.js";

/** Render the left sidebar with two tabs ("📄 페이지" / "❓ 질문").
 *  Phase 4 used a flat page list; Phase 5 wraps it in a tab UI.
 *
 *  ``ctx`` = { doc, currentPage, threads, currentBlockId, sidebarTab }
 *  ``callbacks`` = { onNavigatePage, onSelectThread, onTabChange, onExport,
 *                    onOpenSearch }
 *
 *  Phase 6a additions: search hint + export button (questions tab only).
 */
export function renderSidebar(container, ctx, callbacks) {
  container.innerHTML = "";

  const head = document.createElement("h2");
  head.textContent = ctx.doc?.filename || "no document loaded";
  container.appendChild(head);

  const tabs = document.createElement("nav");
  tabs.className = "sidebar-tabs";
  for (const [key, label] of [
    ["pages", "📄 페이지"],
    ["questions", "❓ 질문"],
  ]) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "sidebar-tab";
    btn.dataset.tab = key;
    btn.textContent = label;
    if (ctx.sidebarTab === key) btn.classList.add("sidebar-tab--active");
    btn.addEventListener("click", () => callbacks.onTabChange?.(key));
    tabs.appendChild(btn);
  }
  container.appendChild(tabs);

  // Phase 6a — search hint visible on every tab.
  const hint = document.createElement("div");
  hint.className = "search-hint";
  hint.textContent = "🔍 Ctrl/Cmd+K 검색";
  hint.style.cursor = "pointer";
  hint.addEventListener("click", () => callbacks.onOpenSearch?.());
  container.appendChild(hint);

  if (ctx.sidebarTab === "pages") {
    const pageList = document.createElement("ol");
    pageList.className = "page-list";
    const total = ctx.doc?.num_pages || 0;
    for (let p = 1; p <= total; p++) {
      const li = document.createElement("li");
      li.className = "page-item";
      if (p === ctx.currentPage) li.classList.add("page-item--active");
      const a = document.createElement("a");
      a.href = `viewer.html?doc=${ctx.doc.id}&page=${p}`;
      a.textContent = String(p);
      a.addEventListener("click", (e) => {
        e.preventDefault();
        callbacks.onNavigatePage?.(p);
      });
      li.appendChild(a);
      pageList.appendChild(li);
    }
    container.appendChild(pageList);
  } else {
    // Phase 6a — export-to-markdown button on top of the questions tab.
    if (ctx.doc) {
      const actions = document.createElement("div");
      actions.className = "sidebar-actions";
      const exportBtn = document.createElement("button");
      exportBtn.type = "button";
      exportBtn.className = "export-btn";
      exportBtn.textContent = "📥 마크다운으로 내보내기";
      exportBtn.addEventListener("click", () => callbacks.onExport?.());
      actions.appendChild(exportBtn);
      container.appendChild(actions);
    }
    const wrap = document.createElement("div");
    wrap.className = "thread-list-wrap";
    renderThreadList(
      wrap,
      ctx.threads || [],
      ctx.currentThreadId || null,
      callbacks.onSelectThread,
    );
    container.appendChild(wrap);
  }
}
