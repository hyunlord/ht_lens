"use strict";

import {
  apiGet,
  ApiError,
  createThread,
  explainThread,
  exportQuestions,
  getThreadDetail,
  listThreadsForDoc,
  postMessage,
  retranslateBlock,
  searchAll,
} from "./api.js";
import {
  closePanel,
  closeSearch,
  discardPanel,
  moveSearchSelection,
  openPanel,
  openSearch,
  setActiveThreadId,
  setLoadingMessage,
  setRetranslateInProgress,
  setSearchError,
  setSearchLoading,
  setSearchResults,
  setSidebarTab,
  setThreadDetail,
  setThreadsForDoc,
  state,
  subscribe,
  toggleOverlay,
  togglePanel,
  zoomIn,
  zoomOut,
} from "./state.js";
import { renderPageView } from "./components/page_view.js";
import { renderSidebar } from "./components/sidebar.js";
import { renderChatPanel } from "./components/chat_panel.js";
import { renderSearchModal } from "./components/search_modal.js";
import { renderConfirmModal } from "./components/confirm_modal.js";
import { attachKeyboard } from "./utils/keyboard.js";

// --- DOM refs ---
const shellEl = document.querySelector(".viewer-shell");
const headerMeta = document.querySelector(".app-header .meta");
const sidebarEl = document.querySelector(".sidebar");
const pageEl = document.getElementById("page-mount");
const panelEl = document.querySelector(".right-slot");
const errorEl = document.getElementById("status");
// Phase 6a — search modal mount + toast container (created lazily).
const searchEl = document.getElementById("search-modal-mount");

function toast(message, kind = "info", timeoutMs = 2400) {
  const el = document.createElement("div");
  el.className = `toast toast--${kind}`;
  if (kind === "error") el.classList.add("error");
  if (kind === "success") el.classList.add("success");
  el.textContent = message;
  document.body.appendChild(el);
  setTimeout(() => el.remove(), timeoutMs);
}

function parseQuery() {
  const params = new URL(window.location.href).searchParams;
  const docRaw = Number.parseInt(params.get("doc") || "", 10);
  const pageRaw = Number.parseInt(params.get("page") || "", 10);
  const blockRaw = Number.parseInt(params.get("block") || "", 10);
  const docId = Number.isFinite(docRaw) && docRaw > 0 ? docRaw : null;
  const page = Number.isFinite(pageRaw) && pageRaw > 0 ? pageRaw : 1;
  // Phase 6a: ?block=N is a deep link from /search results.
  const blockId = Number.isFinite(blockRaw) && blockRaw > 0 ? blockRaw : null;
  return { docId, page, blockId };
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
// R1 fix: remember the last failing async action so the "재시도" button can
// actually re-issue it instead of just clearing the error banner.
let lastFailedAction = null; // () => Promise<void> | null

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
      currentThreadId: state.activeThreadId,
      sidebarTab: state.sidebarTab,
    },
    {
      onNavigatePage: (p) => navigateTo(currentDoc.id, p),
      onTabChange: (tab) => setSidebarTab(tab),
      onSelectThread: (t) => jumpToThread(t),
      onExport: () => handleExport(),
      onOpenSearch: () => openSearch(),
    },
  );
}

function repaintSearch() {
  if (!searchEl) return;
  if (!state.searchOpen) {
    searchEl.innerHTML = "";
    searchEl.hidden = true;
    return;
  }
  searchEl.hidden = false;
  renderSearchModal(
    searchEl,
    {
      query: state.searchQuery,
      results: state.searchResults,
      selected: state.searchSelected,
      loading: state.searchLoading,
      error: state.searchError,
    },
    {
      onClose: () => closeSearch(),
      onQueryChange: (value) => handleSearchInput(value),
      onMove: (delta) => moveSearchSelection(delta),
      onSelect: (hit) => handleSearchSelect(hit),
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
        // R1 fix: actually re-issue the failed action.
        if (typeof lastFailedAction === "function") {
          const action = lastFailedAction;
          lastFailedAction = null;
          action().catch((err) => {
            console.error("retry action failed", err);
          });
        }
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

async function loadAndRender({ docId, page, replaceUrl = false, activateBlockId = null }) {
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

    // Phase 6a: search-result deep link — activate the target block, open
    // the panel for it, and scroll into view. This must run AFTER repaintPage
    // since the block DOM has just been created.
    if (activateBlockId) {
      openPanel({ blockId: activateBlockId, threadId: null, docId });
      // If the block already has a thread, hydrate it in the background.
      const existing = (state.threadsByDoc[docId] || []).filter(
        (t) => t.block_id === activateBlockId,
      );
      if (existing.length > 0) {
        const target = existing.reduce((a, b) => (a.id > b.id ? a : b));
        setActiveThreadId(target.id);
        try {
          await ensureThreadDetail(target.id);
        } catch (err) {
          console.warn("thread detail hydrate failed", err);
        }
      }
      const blockEl = document.querySelector(
        `.block[data-block-id="${activateBlockId}"]`,
      );
      if (blockEl) {
        blockEl.scrollIntoView({ behavior: "smooth", block: "center" });
        blockEl.classList.add("block--flash");
        setTimeout(() => blockEl.classList.remove("block--flash"), 1500);
      }
    }

    const baseUrl = `viewer.html?doc=${docId}&page=${clampedPage}`;
    const url = activateBlockId ? `${baseUrl}&block=${activateBlockId}` : baseUrl;
    if (replaceUrl) {
      window.history.replaceState({ docId, page: clampedPage }, "", url);
    } else if (
      page !== clampedPage ||
      window.location.search !==
        (activateBlockId
          ? `?doc=${docId}&page=${clampedPage}&block=${activateBlockId}`
          : `?doc=${docId}&page=${clampedPage}`)
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

function navigateTo(docId, page, opts = {}) {
  // Close the panel before navigating so a stale thread cannot paint over
  // the new page. Use discardPanel (not closePanel) because the new page's
  // blocks are unrelated to the current activeBlockId — a Ctrl/Cmd+B toggle
  // after page change should not reopen the previous conversation.
  panelError = null;
  lastFailedAction = null;
  discardPanel();
  loadAndRender({ docId, page, activateBlockId: opts.activateBlockId });
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
  lastFailedAction = null;
  repaintPanel();
  try {
    const threadId = await ensureThreadForActiveBlock();
    if (state.panelToken !== token) return;
    await explainThread(threadId);
    if (state.panelToken !== token) return;
    await ensureThreadDetail(threadId);
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
    panelError = err.message || "AI 응답 실패. 다시 시도하세요.";
    lastFailedAction = handleExplain; // R1 fix: retry actually re-issues
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
  lastFailedAction = null;
  repaintPanel();
  try {
    const threadId = await ensureThreadForActiveBlock();
    if (state.panelToken !== token) return;
    await postMessage(threadId, text);
    if (state.panelToken !== token) return;
    await ensureThreadDetail(threadId);
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
    lastFailedAction = () => handleSubmit(text); // R1 fix
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
  // R2 fix: jumping to a different block clears stale retry/error.
  if (state.activeBlockId !== thread.block_id) {
    panelError = null;
    lastFailedAction = null;
  }
  // Open panel state ahead of navigation so the reload restores it.
  openPanel({ blockId: thread.block_id, threadId: thread.id, docId });
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
  const docId = currentDoc?.id;
  // R2 fix: clear retry/error state on block transition. Same-block re-click
  // preserves it so the user can still hit "재시도".
  if (state.activeBlockId !== blockId) {
    panelError = null;
    lastFailedAction = null;
  }
  openPanel({ blockId, threadId: null, docId });
  // If the block already has a thread, auto-select the most recent.
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
  // Browser back/forward lands on a different page — discard the stale
  // panel context entirely (same rationale as navigateTo).
  panelError = null;
  lastFailedAction = null;
  discardPanel();
  if (data && data.docId && data.page) {
    loadAndRender({ docId: data.docId, page: data.page, replaceUrl: true });
  } else {
    const q = parseQuery();
    loadAndRender({
      docId: q.docId,
      page: q.page,
      activateBlockId: q.blockId,
      replaceUrl: true,
    });
  }
});

// Re-render when state (zoom / overlay / tab) changes.
subscribe(() => {
  // Search modal is doc-agnostic — repaint even before any doc is loaded.
  repaintSearch();
  if (!currentDoc || !currentPage) return;
  repaintPage();
  repaintSidebar();
  repaintPanel();
});

// --- Phase 6a: search + export + retranslate handlers ---

let _searchDebounce = null;
const _searchAbortRef = { current: null };

async function handleSearchInput(query) {
  state.searchQuery = query;
  if (_searchDebounce) {
    clearTimeout(_searchDebounce);
  }
  if (!query || query.trim().length < 2) {
    setSearchResults(query, []);
    return;
  }
  _searchDebounce = setTimeout(async () => {
    setSearchLoading(true);
    const localQuery = query;
    try {
      const docId = currentDoc?.id ?? null;
      const results = await searchAll(localQuery, { docId, limit: 50 });
      // Drop the response if the user has typed something else in the meantime.
      if (state.searchQuery !== localQuery) return;
      setSearchResults(localQuery, results);
    } catch (err) {
      setSearchError(err.message || "검색 실패");
    } finally {
      setSearchLoading(false);
    }
  }, 200);
}

function handleSearchSelect(hit) {
  closeSearch();
  // jump to the target page; openPanel with the matched block right after.
  navigateTo(hit.doc_id, hit.page_num, { activateBlockId: hit.block_id });
}

async function handleExport() {
  if (!currentDoc) return;
  try {
    const filename = await exportQuestions(currentDoc.id);
    toast(`${filename} 다운로드 완료`, "success");
  } catch (err) {
    console.error("export failed", err);
    toast(`내보내기 실패: ${err.message}`, "error");
  }
}

document.addEventListener("ht-lens:block-contextmenu", (e) => {
  const { blockId, blockData } = e.detail;
  if (!currentDoc) return;
  if (state.retranslateInProgress === blockId) {
    toast("재번역 진행 중...", "info");
    return;
  }
  const preview = (blockData.original_text || "").slice(0, 200);
  renderConfirmModal({
    title: "단락 재번역",
    message: "이 단락을 LLM에 다시 번역 요청하시겠습니까?",
    detail: preview,
    confirmLabel: "재번역",
    cancelLabel: "취소",
    onConfirm: () => handleRetranslate(blockId),
  });
});

async function handleRetranslate(blockId) {
  setRetranslateInProgress(blockId);
  try {
    const resp = await retranslateBlock(blockId);
    const newText = resp.translation.translated_text;
    // 1. Update the page snapshot so the overlay rerenders with the new text.
    if (currentPage) {
      const idx = currentPage.blocks.findIndex((b) => b.id === blockId);
      if (idx >= 0) {
        currentPage.blocks[idx] = {
          ...currentPage.blocks[idx],
          translated_text: newText,
        };
      }
    }
    // 2. Update any cached thread detail that hangs off this block so the
    //    chat panel preview matches the new translation.
    for (const detail of Object.values(state.threadDetailById)) {
      if (detail?.block?.id === blockId) {
        detail.block.translated_text = newText;
      }
    }
    repaintPage();
    repaintPanel();
    toast("재번역 완료", "success");
  } catch (err) {
    console.error("retranslate failed", err);
    toast(`재번역 실패: ${err.message}`, "error");
  } finally {
    setRetranslateInProgress(null);
  }
}

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
  onOpenSearch: () => openSearch(),
  onCloseSearch: () => closeSearch(),
  isSearchOpen: () => state.searchOpen,
  onClosePanel: () => {
    // Esc dismisses the panel but keeps the active block, so Ctrl/Cmd+B
    // (or a follow-up Esc cancel) can reopen the same conversation.
    if (state.panelOpen) {
      panelError = null;
      closePanel();
    }
  },
  onTogglePanel: () => {
    // togglePanel is the single source of truth: it closes if open and
    // reopens against the preserved activeBlockId otherwise. R2 fix.
    togglePanel();
  },
});

// Initial render. If localStorage restored an activeThreadId, hydrate its
// detail snapshot in the background so the panel can paint when ready.
//
// R1 fix: refuse to restore the panel if the persisted ``activeDocId`` does
// not match the document we are about to load. A cross-document restore
// would otherwise hydrate doc A's thread inside doc B's UI and let
// `handleSubmit` post into the wrong thread.
async function bootstrap() {
  const initial = parseQuery();
  const restoredDocId = state.activeDocId;
  if (
    state.panelOpen &&
    restoredDocId !== null &&
    restoredDocId !== initial.docId
  ) {
    console.info("discarding cross-document panel restore", {
      restoredDocId,
      urlDocId: initial.docId,
    });
    discardPanel();
  }
  await loadAndRender({
    docId: initial.docId,
    page: initial.page,
    activateBlockId: initial.blockId,
    replaceUrl: true,
  });
  if (state.panelOpen && state.activeThreadId) {
    try {
      await ensureThreadDetail(state.activeThreadId);
      repaintPanel();
    } catch (err) {
      console.warn("restored thread no longer available", err);
      discardPanel();
    }
  }
}
bootstrap();
