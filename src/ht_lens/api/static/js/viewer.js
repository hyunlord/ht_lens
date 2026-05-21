"use strict";

import {
  apiGet,
  ApiError,
  createThread,
  explainThread,
  exportQuestions,
  getPagesSummary,
  getThreadDetail,
  listThreadsForDoc,
  postMessage,
  retranslateBlock,
  searchAll,
} from "./api.js";
import {
  closePanel,
  closeSearch,
  cycleViewMode,
  discardPanel,
  findBlockInPageData,
  moveSearchSelection,
  openPanel,
  openSearch,
  setActiveThreadId,
  setLoadingMessage,
  setPageSummaries,
  setRetranslateInProgress,
  setSearchError,
  setSearchLoading,
  setSearchResults,
  setSidebarTab,
  setThreadDetail,
  setThreadsForDoc,
  state,
  subscribe,
  togglePanel,
  zoomIn,
  zoomOut,
} from "./state.js";
import { renderSidebar } from "./components/sidebar.js";
import { renderChatPanel } from "./components/chat_panel.js";
import { renderSearchModal } from "./components/search_modal.js";
import { renderConfirmModal } from "./components/confirm_modal.js";
import {
  attachIntersectionObserver,
  buildPlaceholderRows,
  flashBlock,
  mountPage,
  repaintAllMountedPages,
  repaintMountedPage,
  resizePlaceholderRows,
  scrollToPage,
  waitForBlockMounted,
} from "./components/stage_container.js";
import { attachKeyboard } from "./utils/keyboard.js";

// --- DOM refs ---
const shellEl = document.querySelector(".viewer-shell");
const headerMeta = document.querySelector(".app-header .meta");
const sidebarEl = document.querySelector(".sidebar");
const stageEl = document.getElementById("stage");
const panelEl = document.querySelector(".right-slot");
const errorEl = document.getElementById("status");
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
let panelError = null;
let navToken = 0;
let lastFailedAction = null;
let _detachIO = null;

function buildThreadsByBlock(docId) {
  const list = state.threadsByDoc[docId] || [];
  const map = new Map();
  for (const t of list) {
    if (!map.has(t.block_id)) map.set(t.block_id, []);
    map.get(t.block_id).push(t);
  }
  return map;
}

function stageContext() {
  return {
    doc: currentDoc,
    docId: currentDoc?.id,
    stageEl,
    getThreadsByBlock: () => buildThreadsByBlock(currentDoc?.id),
    onScrollPageChange: (pageNum) => {
      // Free-scroll page change uses replaceState so back/forward stays
      // tied to explicit navigateTo calls (debate §2 fix).
      const url = `viewer.html?doc=${currentDoc?.id}&page=${pageNum}`;
      window.history.replaceState(
        { docId: currentDoc?.id, page: pageNum },
        "",
        url,
      );
    },
  };
}

function clearViewerDom() {
  if (stageEl) stageEl.innerHTML = "";
  if (sidebarEl) sidebarEl.innerHTML = "";
  if (panelEl) panelEl.innerHTML = "";
  if (headerMeta) headerMeta.textContent = "no document loaded";
  document.title = "ht_lens — viewer";
  currentDoc = null;
  _detachIO?.();
  _detachIO = null;
}

function findBlockData(blockId) {
  if (!blockId) return null;
  return findBlockInPageData(blockId)?.block || null;
}

function repaintSidebar() {
  if (!currentDoc) return;
  renderSidebar(
    sidebarEl,
    {
      doc: currentDoc,
      currentPage: state.currentPage,
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

async function loadDocument({ docId, initialPage, initialBlockId, replaceUrl }) {
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
    const summaries = await getPagesSummary(docId);
    if (token !== navToken) return;
    try {
      const threads = await listThreadsForDoc(docId);
      if (token === navToken) setThreadsForDoc(docId, threads);
    } catch (err) {
      console.warn("threads fetch failed", err);
    }
    if (token !== navToken) return;

    currentDoc = doc;
    setPageSummaries(summaries);

    document.title = `${doc.filename} · ${doc.num_pages} pages`;
    if (headerMeta) {
      headerMeta.textContent = `${doc.filename} · ${doc.num_pages} pages`;
    }

    // Build placeholder rows + attach IO observer.
    buildPlaceholderRows(stageEl, summaries, state.zoom, state.viewModeActual);
    _detachIO?.();
    _detachIO = attachIntersectionObserver(stageEl, stageContext());

    repaintSidebar();
    repaintPanel();
    setStatus("");

    const clampedPage = Math.max(1, Math.min(doc.num_pages, initialPage || 1));
    // First scroll uses ``auto`` (instant) — the page is already loading
    // bg+blocks via IO so we want to land users on the right page without
    // a smooth-scroll delay that re-fires IO entries.
    const row = scrollToPage(stageEl, clampedPage, "auto");
    if (row) {
      // Force-mount the landing page immediately (IO might fire late on
      // first load) so search/sidebar deep links resolve their block fast.
      await mountPage(clampedPage, stageContext());
    }

    if (initialBlockId) {
      openPanel({ blockId: initialBlockId, threadId: null, docId });
      const existing = (state.threadsByDoc[docId] || []).filter(
        (t) => t.block_id === initialBlockId,
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
      const blockEl = await waitForBlockMounted(initialBlockId, 2000);
      if (blockEl) {
        blockEl.scrollIntoView({ behavior: "smooth", block: "center" });
        flashBlock(initialBlockId);
      }
    }

    const baseUrl = `viewer.html?doc=${docId}&page=${clampedPage}`;
    const url = initialBlockId
      ? `${baseUrl}&block=${initialBlockId}`
      : baseUrl;
    if (replaceUrl) {
      window.history.replaceState({ docId, page: clampedPage }, "", url);
    } else {
      // Explicit navigation (cross-doc reload, popstate replay) — pushState.
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

async function navigateTo(docId, page, opts = {}) {
  // Cross-document jump — full reload (cleanest state reset).
  if (currentDoc && currentDoc.id !== docId) {
    panelError = null;
    lastFailedAction = null;
    discardPanel();
    const url =
      `viewer.html?doc=${docId}&page=${page}` +
      (opts.activateBlockId ? `&block=${opts.activateBlockId}` : "");
    window.location.href = url;
    return;
  }

  // Same document — natural scroll to target page row.
  if (state.activeBlockId !== opts.activateBlockId) {
    panelError = null;
    lastFailedAction = null;
  }

  // Push an explicit history entry so browser back/forward navigates between
  // search jumps + sidebar jumps (debate §2 fix). Free-scroll uses replaceState.
  const url =
    `viewer.html?doc=${docId}&page=${page}` +
    (opts.activateBlockId ? `&block=${opts.activateBlockId}` : "");
  window.history.pushState({ docId, page }, "", url);

  const row = scrollToPage(stageEl, page, "smooth");
  if (!row) return;
  if (opts.activateBlockId) {
    // Ensure the target page is mounted before we look for the block — IO
    // observer would do this eventually but we want flashBlock to be
    // reliable (debate §4 fix: Promise + waitFor, not a polling-only loop).
    await mountPage(page, stageContext());
    openPanel({
      blockId: opts.activateBlockId,
      threadId: null,
      docId,
    });
    const existing = (state.threadsByDoc[docId] || []).filter(
      (t) => t.block_id === opts.activateBlockId,
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
    const blockEl = await waitForBlockMounted(opts.activateBlockId, 2000);
    if (blockEl) {
      blockEl.scrollIntoView({ behavior: "smooth", block: "center" });
      flashBlock(opts.activateBlockId);
    }
    repaintPanel();
  }
}

async function ensureThreadDetail(threadId) {
  const fresh = await getThreadDetail(threadId);
  setThreadDetail(fresh);
  return fresh;
}

async function ensureThreadForActiveBlock() {
  const blockId = state.activeBlockId;
  if (!blockId) return null;
  if (state.activeThreadId) return state.activeThreadId;
  const docId = currentDoc?.id;
  const existing = (state.threadsByDoc[docId] || []).filter(
    (t) => t.block_id === blockId,
  );
  if (existing.length > 0) {
    const target = existing.reduce((a, b) => (a.id > b.id ? a : b));
    setActiveThreadId(target.id);
    return target.id;
  }
  const created = await createThread(blockId);
  try {
    const refreshed = await listThreadsForDoc(docId);
    setThreadsForDoc(docId, refreshed);
  } catch (err) {
    console.warn("threads refresh after create failed", err);
  }
  setActiveThreadId(created.id);
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
    repaintAllMountedPages(stageContext());
    repaintSidebar();
  } catch (err) {
    if (state.panelToken !== token) return;
    panelError = err.message || "AI 응답 실패. 다시 시도하세요.";
    lastFailedAction = handleExplain;
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
    repaintAllMountedPages(stageContext());
    repaintSidebar();
  } catch (err) {
    if (state.panelToken !== token) return;
    panelError = err.message || "메시지 전송 실패";
    lastFailedAction = () => handleSubmit(text);
    console.error("submit failed", err);
  } finally {
    if (state.panelToken === token) {
      setLoadingMessage(false);
      repaintPanel();
    }
  }
}

async function jumpToThread(thread) {
  if (!currentDoc) return;
  const docId = currentDoc.id;
  if (state.activeBlockId !== thread.block_id) {
    panelError = null;
    lastFailedAction = null;
  }
  openPanel({ blockId: thread.block_id, threadId: thread.id, docId });
  // navigateTo handles scroll + mount + flashBlock for cross-page jumps.
  // For same-page thread jumps it's still safe (scrollToPage will scroll
  // to the row top, which is what we want for confirming the location).
  await navigateTo(docId, thread.page_num, { activateBlockId: thread.block_id });
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
  if (state.activeBlockId !== blockId) {
    panelError = null;
    lastFailedAction = null;
  }
  openPanel({ blockId, threadId: null, docId });
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
  lastFailedAction = null;
  discardPanel();
  const target = data && data.docId && data.page ? data : parseQuery();
  if (target.docId === currentDoc?.id) {
    // Same doc — just scroll to the recorded page.
    scrollToPage(stageEl, target.page, "auto");
  } else {
    loadDocument({
      docId: target.docId,
      initialPage: target.page,
      initialBlockId: target.blockId,
      replaceUrl: true,
    });
  }
});

// Re-render derived UI when state changes.
let _lastViewMode = state.viewModeActual;
let _lastZoom = state.zoom;
subscribe(() => {
  repaintSearch();
  if (!currentDoc) return;
  // Repaint mounted pages on viewMode (e.g. cycle T) or panel-driven mode override.
  if (state.viewModeActual !== _lastViewMode) {
    _lastViewMode = state.viewModeActual;
    repaintAllMountedPages(stageContext());
  }
  if (state.zoom !== _lastZoom) {
    _lastZoom = state.zoom;
    resizePlaceholderRows(
      stageEl,
      state.pageSummaries,
      state.zoom,
      state.viewModeActual,
    );
    repaintAllMountedPages(stageContext());
  }
  repaintSidebar();
  repaintPanel();
});

// --- Search ---
let _searchDebounce = null;

async function handleSearchInput(query) {
  state.searchQuery = query;
  if (_searchDebounce) clearTimeout(_searchDebounce);
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
    // Phase 6b: find every page that has this block and update each entry,
    // not just currentPage (which no longer exists as a singleton).
    for (const pageData of Object.values(state.pageDataById)) {
      const idx = pageData.blocks?.findIndex((b) => b.id === blockId);
      if (idx >= 0) {
        pageData.blocks[idx] = {
          ...pageData.blocks[idx],
          translated_text: newText,
        };
        repaintMountedPage(pageData.page_num, stageContext());
      }
    }
    for (const detail of Object.values(state.threadDetailById)) {
      if (detail?.block?.id === blockId) {
        detail.block.translated_text = newText;
      }
    }
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
    if (!currentDoc) return;
    const target = Math.max(1, state.currentPage - 1);
    navigateTo(currentDoc.id, target);
  },
  onNext: () => {
    if (!currentDoc) return;
    const target = Math.min(currentDoc.num_pages, state.currentPage + 1);
    navigateTo(currentDoc.id, target);
  },
  onFirst: () => currentDoc && navigateTo(currentDoc.id, 1),
  onLast: () => currentDoc && navigateTo(currentDoc.id, currentDoc.num_pages),
  onCycleViewMode: () => cycleViewMode(),
  onZoomIn: () => zoomIn(),
  onZoomOut: () => zoomOut(),
  onOpenSearch: () => openSearch(),
  onCloseSearch: () => closeSearch(),
  isSearchOpen: () => state.searchOpen,
  onClosePanel: () => {
    if (state.panelOpen) {
      panelError = null;
      closePanel();
    }
  },
  onTogglePanel: () => togglePanel(),
});

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
  await loadDocument({
    docId: initial.docId,
    initialPage: initial.page,
    initialBlockId: initial.blockId,
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
