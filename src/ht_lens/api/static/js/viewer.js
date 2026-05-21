"use strict";

import {
  apiGet,
  ApiError,
  createThread,
  explainThread,
  getThreadDetail,
  listThreadsForDoc,
  postMessage,
} from "./api.js";
import {
  closePanel,
  openPanel,
  setActiveThreadId,
  setLoadingMessage,
  setSidebarTab,
  setThreadDetail,
  setThreadsForDoc,
  state,
  subscribe,
  toggleOverlay,
  zoomIn,
  zoomOut,
} from "./state.js";
import { renderPageView } from "./components/page_view.js";
import { renderSidebar } from "./components/sidebar.js";
import { renderChatPanel } from "./components/chat_panel.js";
import { attachKeyboard } from "./utils/keyboard.js";

// --- DOM refs ---
const shellEl = document.querySelector(".viewer-shell");
const headerMeta = document.querySelector(".app-header .meta");
const sidebarEl = document.querySelector(".sidebar");
const pageEl = document.getElementById("page-mount");
const panelEl = document.querySelector(".right-slot");
const errorEl = document.getElementById("status");

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
let panelError = null; // string | null
let navToken = 0;

function buildThreadsByBlock(docId) {
  const list = state.threadsByDoc[docId] || [];
  const map = new Map();
  for (const t of list) {
    if (!map.has(t.block_id)) map.set(t.block_id, []);
    map.get(t.block_id).push(t);
  }
  return map;
}

function clearViewerDom() {
  if (pageEl) pageEl.innerHTML = "";
  if (sidebarEl) sidebarEl.innerHTML = "";
  if (panelEl) panelEl.innerHTML = "";
  if (headerMeta) headerMeta.textContent = "no document loaded";
  document.title = "ht_lens — viewer";
  currentDoc = null;
  currentPage = null;
}

function findBlockData(blockId) {
  if (!currentPage || !blockId) return null;
  return currentPage.blocks.find((b) => b.id === blockId) || null;
}

function repaintSidebar() {
  if (!currentDoc) return;
  renderSidebar(
    sidebarEl,
    {
      doc: currentDoc,
      currentPage: currentPage?.page_num,
      threads: state.threadsByDoc[currentDoc.id] || [],
      currentBlockId: state.activeBlockId,
      sidebarTab: state.sidebarTab,
    },
    {
      onNavigatePage: (p) => navigateTo(currentDoc.id, p),
      onTabChange: (tab) => setSidebarTab(tab),
      onSelectThread: (t) => jumpToThread(t),
    },
  );
}

function repaintPanel() {
  if (!panelEl) return;
  if (!state.panelOpen) {
    panelEl.hidden = true;
    panelEl.innerHTML = "";
    shellEl?.classList.remove("panel-open");
    return;
  }
  shellEl?.classList.add("panel-open");
  panelEl.hidden = false;
  const block = findBlockData(state.activeBlockId);
  const thread = state.activeThreadId
    ? state.threadDetailById[state.activeThreadId] || null
    : null;
  renderChatPanel(
    panelEl,
    { block, thread, loading: state.loadingMessage, error: panelError },
    {
      onClose: () => {
        panelError = null;
        closePanel();
      },
      onExplain: () => handleExplain(),
      onSubmit: (text) => handleSubmit(text),
      onRetry: () => {
        panelError = null;
        repaintPanel();
      },
    },
  );
}

function repaintPage() {
  if (!currentDoc || !currentPage) return;
  renderPageView(
    pageEl,
    currentDoc,
    currentPage,
    state.overlayMode,
    state.zoom,
    buildThreadsByBlock(currentDoc.id),
  );
}

async function loadAndRender({ docId, page, replaceUrl = false }) {
  if (!docId) {
    clearViewerDom();
    setStatus(
      "문서 ID가 필요합니다. /static/index.html 에서 문서를 선택하세요.",
      "error",
    );
    return;
  }
  const token = ++navToken;
  try {
    setStatus("loading…");
    const doc = await apiGet(`/documents/${docId}`);
    if (token !== navToken) return;
    const clampedPage = Math.max(1, Math.min(doc.num_pages, page));
    const pageData = await apiGet(`/documents/${docId}/pages/${clampedPage}`);
    if (token !== navToken) return;

    // Pull the document-wide thread list (used for pins + sidebar tab).
    // Failure here is non-fatal — the viewer still renders without pins.
    try {
      const threads = await listThreadsForDoc(docId);
      if (token === navToken) setThreadsForDoc(docId, threads);
    } catch (err) {
      console.warn("threads fetch failed", err);
    }
    if (token !== navToken) return;

    currentDoc = doc;
    currentPage = pageData;

    document.title = `${doc.filename} · page ${clampedPage}`;
    if (headerMeta) {
      headerMeta.textContent = `${doc.filename} · page ${clampedPage}/${doc.num_pages}`;
    }
    repaintPage();
    repaintSidebar();
    repaintPanel();
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
    if (token !== navToken) return;
    clearViewerDom();
    if (err instanceof ApiError && err.status === 404) {
      setStatus("문서 또는 페이지를 찾을 수 없습니다.", "error");
    } else {
      setStatus(`오류: ${err.message}`, "error");
      console.error(err);
    }
  }
}

function navigateTo(docId, page) {
  // Close the panel before navigating so a stale thread cannot paint over
  // the new page (R1 navToken extension to chat ops — Phase 5 R1 fix).
  panelError = null;
  closePanel();
  loadAndRender({ docId, page });
}

async function ensureThreadDetail(threadId) {
  const fresh = await getThreadDetail(threadId);
  setThreadDetail(fresh);
  return fresh;
}

async function ensureThreadForActiveBlock() {
  const blockId = state.activeBlockId;
  if (!blockId) return null;
  // Already have a thread selected.
  if (state.activeThreadId) return state.activeThreadId;
  // Look up an existing thread on this block in the cached list.
  const docId = currentDoc?.id;
  const existing = (state.threadsByDoc[docId] || []).filter(
    (t) => t.block_id === blockId,
  );
  if (existing.length > 0) {
    // Pick the most recent (highest id).
    const target = existing.reduce((a, b) => (a.id > b.id ? a : b));
    setActiveThreadId(target.id);
    return target.id;
  }
  // Otherwise create a new thread server-side.
  const created = await createThread(blockId);
  // Refresh the document-wide thread list so pins + sidebar update.
  try {
    const refreshed = await listThreadsForDoc(docId);
    setThreadsForDoc(docId, refreshed);
  } catch (err) {
    console.warn("threads refresh after create failed", err);
  }
  setActiveThreadId(created.id);
  // Cache an empty detail snapshot until the first message arrives.
  setThreadDetail({ ...created, messages: created.messages || [] });
  return created.id;
}

async function handleExplain() {
  if (!currentDoc || !state.activeBlockId) return;
  const token = state.panelToken;
  setLoadingMessage(true);
  panelError = null;
  repaintPanel();
  try {
    const threadId = await ensureThreadForActiveBlock();
    if (state.panelToken !== token) return;
    await explainThread(threadId);
    if (state.panelToken !== token) return;
    const detail = await ensureThreadDetail(threadId);
    if (state.panelToken !== token) return;
    // Pin/sidebar update — refresh the doc-wide list.
    try {
      const refreshed = await listThreadsForDoc(currentDoc.id);
      setThreadsForDoc(currentDoc.id, refreshed);
    } catch (_e) {
      /* non-fatal */
    }
    repaintPage();
    repaintSidebar();
  } catch (err) {
    if (state.panelToken !== token) return;
    panelError = err.message || "AI 응답 실패. 다시 시도하세요.";
    console.error("explain failed", err);
  } finally {
    if (state.panelToken === token) {
      setLoadingMessage(false);
      repaintPanel();
    }
  }
}

async function handleSubmit(text) {
  if (!currentDoc || !state.activeBlockId) return;
  const token = state.panelToken;
  setLoadingMessage(true);
  panelError = null;
  repaintPanel();
  try {
    const threadId = await ensureThreadForActiveBlock();
    if (state.panelToken !== token) return;
    await postMessage(threadId, text);
    if (state.panelToken !== token) return;
    const detail = await ensureThreadDetail(threadId);
    if (state.panelToken !== token) return;
    try {
      const refreshed = await listThreadsForDoc(currentDoc.id);
      setThreadsForDoc(currentDoc.id, refreshed);
    } catch (_e) {
      /* non-fatal */
    }
    repaintPage();
    repaintSidebar();
  } catch (err) {
    if (state.panelToken !== token) return;
    panelError = err.message || "메시지 전송 실패";
    console.error("submit failed", err);
  } finally {
    if (state.panelToken === token) {
      setLoadingMessage(false);
      repaintPanel();
    }
  }
}

async function jumpToThread(thread) {
  // Sidebar -> thread click: navigate to the thread's page (if different)
  // and open the chat panel for that block + thread.
  if (!currentDoc) return;
  const docId = currentDoc.id;
  const needNav = thread.page_num !== currentPage?.page_num;
  // Open panel state ahead of navigation so the reload restores it.
  openPanel({ blockId: thread.block_id, threadId: thread.id });
  if (needNav) {
    await loadAndRender({ docId, page: thread.page_num });
  }
  try {
    await ensureThreadDetail(thread.id);
  } catch (err) {
    console.warn("thread detail fetch failed", err);
  }
  repaintPanel();
}

// Block click delegation (Phase 5).
document.addEventListener("ht-lens:block-click", async (e) => {
  const { blockId } = e.detail;
  openPanel({ blockId, threadId: null });
  // If the block already has a thread, auto-select the most recent.
  const docId = currentDoc?.id;
  const existing = (state.threadsByDoc[docId] || []).filter(
    (t) => t.block_id === blockId,
  );
  if (existing.length > 0) {
    const target = existing.reduce((a, b) => (a.id > b.id ? a : b));
    setActiveThreadId(target.id);
    try {
      await ensureThreadDetail(target.id);
    } catch (err) {
      console.warn("thread detail fetch failed", err);
    }
  }
  repaintPanel();
});

window.addEventListener("popstate", (e) => {
  const data = e.state;
  panelError = null;
  closePanel();
  if (data && data.docId && data.page) {
    loadAndRender({ docId: data.docId, page: data.page, replaceUrl: true });
  } else {
    const q = parseQuery();
    loadAndRender({ docId: q.docId, page: q.page, replaceUrl: true });
  }
});

// Re-render when state (zoom / overlay / tab) changes.
subscribe(() => {
  if (!currentDoc || !currentPage) return;
  repaintPage();
  repaintSidebar();
  repaintPanel();
});

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
  onLast: () => currentDoc && navigateTo(currentDoc.id, currentDoc.num_pages),
  onToggle: () => toggleOverlay(),
  onZoomIn: () => zoomIn(),
  onZoomOut: () => zoomOut(),
  onClosePanel: () => {
    if (state.panelOpen) {
      panelError = null;
      closePanel();
    }
  },
  onTogglePanel: () => {
    if (state.panelOpen) {
      closePanel();
    } else if (state.activeBlockId) {
      openPanel({
        blockId: state.activeBlockId,
        threadId: state.activeThreadId,
      });
    }
  },
});

// Initial render. If localStorage restored an activeThreadId, hydrate its
// detail snapshot in the background so the panel can paint when ready.
async function bootstrap() {
  const initial = parseQuery();
  await loadAndRender({ ...initial, replaceUrl: true });
  if (state.panelOpen && state.activeThreadId) {
    try {
      await ensureThreadDetail(state.activeThreadId);
      repaintPanel();
    } catch (err) {
      // Stale thread id — close panel cleanly.
      console.warn("restored thread no longer available", err);
      closePanel();
    }
  }
}
bootstrap();
