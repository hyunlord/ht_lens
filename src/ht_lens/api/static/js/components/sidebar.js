"use strict";

/** Render the page-list sidebar. Clicks delegate to ``onNavigate(page_num)``
 *  so the caller can use history.pushState instead of full reloads. */
export function renderSidebar(container, doc, currentPage, onNavigate) {
  container.innerHTML = "";

  const heading = document.createElement("h2");
  heading.textContent = doc.filename;
  container.appendChild(heading);

  const list = document.createElement("ol");
  list.className = "page-list";
  for (let p = 1; p <= doc.num_pages; p++) {
    const li = document.createElement("li");
    li.className = "page-item";
    if (p === currentPage) li.classList.add("page-item--active");
    const a = document.createElement("a");
    a.href = `viewer.html?doc=${doc.id}&page=${p}`;
    a.textContent = String(p);
    a.addEventListener("click", (e) => {
      e.preventDefault();
      onNavigate(p);
    });
    li.appendChild(a);
    list.appendChild(li);
  }
  container.appendChild(list);
}
