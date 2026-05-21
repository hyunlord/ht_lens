"use strict";

import { renderThreadList } from "./thread_list.js";

/** Render the left sidebar with two tabs ("📄 페이지" / "❓ 질문").
 *  Phase 4 used a flat page list; Phase 5 wraps it in a tab UI.
 *
 *  ``ctx`` = { doc, currentPage, threads, currentBlockId, sidebarTab }
 *  ``callbacks`` = { onNavigatePage, onSelectThread, onTabChange }
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
    const wrap = document.createElement("div");
    wrap.className = "thread-list-wrap";
    renderThreadList(
      wrap,
      ctx.threads || [],
      ctx.currentBlockId || null,
      callbacks.onSelectThread,
    );
    container.appendChild(wrap);
  }
}
