"use strict";

/** Render the "질문" sidebar tab. Lists every thread for the current document
 *  with a pin marker, title, page number, and message count. Clicking an
 *  item invokes ``onSelect(thread)`` — the viewer is responsible for
 *  navigating + opening the panel. */
export function renderThreadList(container, threads, currentBlockId, onSelect) {
  container.innerHTML = "";
  if (!threads || threads.length === 0) {
    const empty = document.createElement("div");
    empty.className = "thread-empty";
    empty.textContent = "아직 질문이 없습니다. block을 클릭해 시작하세요.";
    container.appendChild(empty);
    return;
  }
  const list = document.createElement("ol");
  list.className = "thread-list";
  for (const t of threads) {
    const li = document.createElement("li");
    li.className = "thread-item";
    if (t.block_id === currentBlockId) li.classList.add("thread-item--active");
    li.dataset.threadId = String(t.id);
    li.dataset.blockId = String(t.block_id);

    const pin = document.createElement("span");
    pin.className = "thread-pin";
    pin.textContent = "📌";
    li.appendChild(pin);

    const body = document.createElement("div");
    body.className = "thread-body";
    const titleEl = document.createElement("div");
    titleEl.className = "thread-title";
    titleEl.textContent = t.title || `[block #${t.block_id}]`;
    body.appendChild(titleEl);
    const meta = document.createElement("div");
    meta.className = "thread-meta";
    meta.textContent = `p.${t.page_num} · ${t.message_count}개 메시지`;
    body.appendChild(meta);
    li.appendChild(body);

    li.addEventListener("click", () => onSelect?.(t));
    list.appendChild(li);
  }
  container.appendChild(list);
}
