"use strict";

import { apiGet, ApiError } from "./api.js";
import { state, subscribe, toggleOverlay, zoomIn, zoomOut } from "./state.js";
import { renderPageView } from "./components/page_view.js";
import { renderSidebar } from "./components/sidebar.js";
import { attachKeyboard } from "./utils/keyboard.js";

// --- DOM refs ---
const headerMeta = document.querySelector(".app-header .meta");
const sidebarEl = document.querySelector(".sidebar");
const pageEl = document.getElementById("page-mount");
const errorEl = document.getElementById("status");

// --- Query: viewer.js parses ?doc=N&page=M and clamps invalid values. ---
function parseQuery() {
  const params = new URL(window.location.href).searchParams;
  const docRaw = Number.parseInt(params.get("doc") || "", 10);
  const pageRaw = Number.parseInt(params.get("page") || "", 10);
  const docId = Number.isFinite(docRaw) && docRaw > 0 ? docRaw : null;
  const page = Number.isFinite(pageRaw) && pageRaw > 0 ? pageRaw : 1;
  return { docId, page };
}

function setStatus(msg, kind = "info") {
  if (!errorEl) return;
  errorEl.textContent = msg;
  errorEl.hidden = !msg;
  errorEl.classList.remove("error", "empty");
  if (kind === "error") errorEl.classList.add("error");
}

let currentDoc = null;
let currentPage = null;

async function loadAndRender({ docId, page, replaceUrl = false }) {
  if (!docId) {
    setStatus("문서 ID가 필요합니다. /static/index.html 에서 문서를 선택하세요.", "error");
    return;
  }
  try {
    setStatus("loading…");
    const doc = await apiGet(`/documents/${docId}`);
    const clampedPage = Math.max(1, Math.min(doc.num_pages, page));
    const pageData = await apiGet(`/documents/${docId}/pages/${clampedPage}`);
    currentDoc = doc;
    currentPage = pageData;

    document.title = `${doc.filename} · page ${clampedPage}`;
    if (headerMeta) {
      headerMeta.textContent = `${doc.filename} · page ${clampedPage}/${doc.num_pages}`;
    }
    renderSidebar(sidebarEl, doc, clampedPage, (p) => navigateTo(docId, p));
    renderPageView(pageEl, doc, pageData, state.overlayMode, state.zoom);
    setStatus("");

    const url = `viewer.html?doc=${docId}&page=${clampedPage}`;
    if (replaceUrl) {
      window.history.replaceState({ docId, page: clampedPage }, "", url);
    } else if (
      page !== clampedPage ||
      window.location.search !== `?doc=${docId}&page=${clampedPage}`
    ) {
      window.history.pushState({ docId, page: clampedPage }, "", url);
    }
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) {
      setStatus("문서 또는 페이지를 찾을 수 없습니다.", "error");
    } else {
      setStatus(`오류: ${err.message}`, "error");
      console.error(err);
    }
  }
}

function navigateTo(docId, page) {
  loadAndRender({ docId, page });
}

function rerenderInPlace() {
  if (!currentDoc || !currentPage) return;
  renderPageView(
    pageEl,
    currentDoc,
    currentPage,
    state.overlayMode,
    state.zoom,
  );
}

window.addEventListener("popstate", (e) => {
  const data = e.state;
  if (data && data.docId && data.page) {
    loadAndRender({ docId: data.docId, page: data.page, replaceUrl: true });
  } else {
    const q = parseQuery();
    loadAndRender({ docId: q.docId, page: q.page, replaceUrl: true });
  }
});

// Re-render when state (zoom / overlay mode) changes.
subscribe(rerenderInPlace);

attachKeyboard({
  onPrev: () => {
    if (currentDoc && currentPage && currentPage.page_num > 1) {
      navigateTo(currentDoc.id, currentPage.page_num - 1);
    }
  },
  onNext: () => {
    if (
      currentDoc &&
      currentPage &&
      currentPage.page_num < currentDoc.num_pages
    ) {
      navigateTo(currentDoc.id, currentPage.page_num + 1);
    }
  },
  onFirst: () => currentDoc && navigateTo(currentDoc.id, 1),
  onLast: () =>
    currentDoc && navigateTo(currentDoc.id, currentDoc.num_pages),
  onToggle: () => toggleOverlay(),
  onZoomIn: () => zoomIn(),
  onZoomOut: () => zoomOut(),
});

// Initial render.
const initial = parseQuery();
loadAndRender({ ...initial, replaceUrl: true });
