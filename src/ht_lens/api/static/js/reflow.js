"use strict";

// ht_lens 2.0 reflow reading view (Phase 8c).
// Single module (chat/pin components arrive in 8d). Renders chunk(8a) +
// translation(8b) as a flowed article; KaTeX via the vendored applyMath
// (Phase 6i). Compare mode does page-level sync (challenge): clicking a
// chunk scrolls the left PDF pane to that chunk's source page.

import { applyMath } from "./utils/render_markdown.js";
import { enrichInline } from "./utils/enrich_inline.js";
import { initChat } from "./chat.js";
import { syncPaneMargin } from "./resize.js";
import {
  buildSectionTree,
  jumpToSection,
  parseSectionNo,
  renderToc,
  selectSectionByHeading,
  wireRefJump,
} from "./sections.js";

const $ = (id) => document.getElementById(id);
const layout = $("layout");
const paneReflow = $("content");
const panePdf = $("pane-pdf");
const metaEl = $("meta");
const tocNav = $("toc");
const tocToggle = $("toc-toggle");

function parseQuery() {
  const q = new URLSearchParams(location.search);
  return { doc: q.get("doc") };
}

/** Build one reading-view chunk element. Returns the element (or null to skip). */
function renderChunk(chunk) {
  const text = chunk.translated ?? chunk.original ?? "";
  let el;
  if (chunk.type === "heading") {
    el = document.createElement(chunk.text_level && chunk.text_level >= 3 ? "h3" : "h2");
    el.className = "rf-heading";
    el.textContent = text;
    applyMath(el);
  } else if (chunk.type === "equation") {
    el = document.createElement("div");
    el.className = "rf-equation";
    el.textContent = chunk.original || ""; // LaTeX passthrough ($$...$$)
    applyMath(el);
  } else if (chunk.type === "image") {
    el = document.createElement("figure");
    el.className = "rf-figure";
    if (chunk.img_url) {
      const img = document.createElement("img");
      img.loading = "lazy";
      img.alt = chunk.caption_translated || chunk.caption || `figure ${chunk.id}`;
      img.src = chunk.img_url;
      img.addEventListener("error", () => {
        // Controlled fallback when the managed asset is missing.
        const ph = document.createElement("span");
        ph.className = "fig-missing";
        ph.textContent = "(이미지를 불러올 수 없음)";
        img.replaceWith(ph);
      });
      el.appendChild(img);
    }
    const capKo = chunk.caption_translated || "";
    const capEn = chunk.caption || "";
    if (capKo || capEn) {
      const box = document.createElement("figcaption");
      box.className = "figure-box";
      if (capKo) {
        const k = document.createElement("div");
        k.className = "fb-cap";
        k.textContent = capKo;
        applyMath(k);
        box.appendChild(k);
      }
      if (capEn) {
        const e = document.createElement("div");
        e.className = "fb-en";
        e.textContent = capEn;
        box.appendChild(e);
      }
      el.appendChild(box);
    }
  } else if (chunk.type === "table") {
    // Graceful fallback — full table UX deferred (challenge §3); never drop/crash.
    el = document.createElement("div");
    el.className = "rf-table";
    const pre = document.createElement("pre");
    pre.textContent = text;
    el.appendChild(pre);
  } else {
    // text / unknown → paragraph
    el = document.createElement("p");
    el.className = "rf-text";
    if (!text.trim()) {
      el.classList.add("rf-text--empty");
      el.textContent = "(빈 chunk)";
    } else {
      el.textContent = text;
      applyMath(el);
    }
  }
  el.classList.add("chunk");
  el.dataset.chunkId = String(chunk.id);
  el.dataset.pageIdx = String(chunk.page_idx);
  return el;
}

/** Left pane: one image per distinct page_idx (page-level compare). */
function buildPdfPane(docId, pageIdxs) {
  panePdf.replaceChildren();
  for (const idx of pageIdxs) {
    const wrap = document.createElement("div");
    wrap.className = "pdf-page";
    wrap.dataset.pageIdx = String(idx);
    const lbl = document.createElement("div");
    lbl.className = "lbl";
    lbl.textContent = `page ${idx}`;
    const img = document.createElement("img");
    img.loading = "lazy";
    img.alt = `source page ${idx}`;
    img.src = `/v2/documents/${docId}/page/${idx}/image`;
    img.addEventListener("error", () => {
      lbl.textContent = `page ${idx} (원문 렌더 없음)`;
    });
    wrap.append(lbl, img);
    panePdf.appendChild(wrap);
  }
}

/** Page-level sync: highlight the chunk + scroll the left pane to its page. */
function syncToChunk(chunkEl) {
  for (const c of paneReflow.querySelectorAll(".chunk.active")) c.classList.remove("active");
  chunkEl.classList.add("active");
  if (layout.dataset.mode !== "compare") return;
  const idx = chunkEl.dataset.pageIdx;
  const page = panePdf.querySelector(`.pdf-page[data-page-idx="${idx}"]`);
  if (page) {
    for (const p of panePdf.querySelectorAll(".pdf-page.hl")) p.classList.remove("hl");
    page.classList.add("hl");
    page.scrollIntoView({ behavior: "smooth", block: "start" });
  }
}

/**
 * Pure, deterministic: given ascending page boundaries [{pageIdx, offset}] and
 * the current scrollTop, return the pageIdx of the last boundary at/above the
 * scroll position (the page the reader is currently in). Binary search — no IO
 * callback-order ambiguity, fully unit-testable with synthetic offsets
 * (Phase 8e-4: replaces IntersectionObserver, which jsdom can't validate).
 */
function pickCurrentPage(boundaries, scrollTop) {
  if (!boundaries.length) return null;
  let lo = 0;
  let hi = boundaries.length - 1;
  let ans = boundaries[0].pageIdx;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (boundaries[mid].offset <= scrollTop + 1) {
      ans = boundaries[mid].pageIdx;
      lo = mid + 1;
    } else {
      hi = mid - 1;
    }
  }
  return ans;
}

/**
 * Continuous compare-mode sync (Phase 8e-4): scrolling the right reading pane
 * scrolls the left PDF pane to the current page. One-way (right→left) so there
 * is no feedback loop. Throttled via rAF; only acts in compare mode. Returns
 * {syncNow, recompute, teardown} — teardown is called on document reload so a
 * stale handler never drives the new left pane.
 */
function initCompareSync({ contentEl, panePdf: pdfPane, layout: layoutEl }) {
  const paneEl = contentEl.closest(".pane--reflow") || contentEl.parentElement;
  let boundaries = [];
  let lastPage = null;
  let raf = 0;
  // Offsets are a snapshot of getBoundingClientRect; lazy figure images load
  // (no width/height attrs) and window resizes shift later pages, so a cached
  // boundary can select the wrong PDF page (verify-cross R1 §4#1). ``dirty``
  // forces a lazy recompute on the next sync; ``invalidate`` also schedules one
  // so the left pane self-corrects without waiting for a user scroll.
  let dirty = true;

  function recompute() {
    boundaries = [];
    const seen = new Set();
    const base = paneEl.getBoundingClientRect().top - paneEl.scrollTop;
    for (const el of contentEl.querySelectorAll(".chunk")) {
      const p = Number(el.dataset.pageIdx);
      if (seen.has(p)) continue;
      seen.add(p);
      boundaries.push({ pageIdx: p, offset: el.getBoundingClientRect().top - base });
    }
    boundaries.sort((a, b) => a.offset - b.offset);
    lastPage = null;
    dirty = false;
  }

  function syncNow() {
    if (layoutEl.dataset.mode !== "compare") return;
    if (dirty || !boundaries.length) recompute();
    const p = pickCurrentPage(boundaries, paneEl.scrollTop);
    if (p === null || p === lastPage) return;
    lastPage = p;
    const page = pdfPane.querySelector(`.pdf-page[data-page-idx="${p}"]`);
    if (page) {
      for (const x of pdfPane.querySelectorAll(".pdf-page.hl")) x.classList.remove("hl");
      page.classList.add("hl");
      page.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  }

  function onScroll() {
    if (raf) return;
    raf = requestAnimationFrame(() => {
      raf = 0;
      syncNow();
    });
  }

  // Mark offsets stale and schedule a recompute+sync (compare mode only acts;
  // single mode keeps dirty=true until the next compare toggle recomputes).
  function invalidate() {
    dirty = true;
    onScroll();
  }

  paneEl.addEventListener("scroll", onScroll, { passive: true });
  window.addEventListener("resize", invalidate);
  // ``load`` AND ``error``: a failed image is replaced by a .fig-missing span
  // (renderChunk), which also shifts later page offsets (verify-cross R2 §4#2).
  const imgs = contentEl.querySelectorAll("img");
  for (const img of imgs) {
    img.addEventListener("load", invalidate);
    img.addEventListener("error", invalidate);
  }
  recompute();

  function teardown() {
    paneEl.removeEventListener("scroll", onScroll);
    window.removeEventListener("resize", invalidate);
    for (const img of imgs) {
      img.removeEventListener("load", invalidate);
      img.removeEventListener("error", invalidate);
    }
    if (raf) cancelAnimationFrame(raf);
  }

  return { syncNow, recompute, teardown };
}

let compareSync = null;

async function load() {
  const { doc } = parseQuery();
  if (!doc) {
    paneReflow.innerHTML = '<div class="err">?doc=&lt;id&gt; 필요</div>';
    return;
  }
  try {
    const r = await fetch(`/v2/documents/${doc}/reflow`, { cache: "no-store" });
    if (!r.ok) {
      const body = await r.text();
      throw new Error(`HTTP ${r.status}: ${body.slice(0, 160)}`);
    }
    const data = await r.json();
    metaEl.textContent = `${data.filename} · ${data.chunks.length} chunks · ${data.extractor}`;
    paneReflow.replaceChildren();
    // Section identity from heading ORIGINALS (translation-independent).
    const sectionNums = new Set();
    for (const c of data.chunks) {
      if (c.type === "heading") {
        const s = parseSectionNo(c.original ?? "");
        if (s) sectionNums.add(s);
      }
    }
    const pageIdxs = [];
    let lastPage = null;
    for (const chunk of data.chunks) {
      if (chunk.page_idx !== lastPage) {
        pageIdxs.push(chunk.page_idx);
        lastPage = chunk.page_idx;
      }
      const el = renderChunk(chunk);
      if (chunk.type === "heading") {
        const secNo = parseSectionNo(chunk.original ?? "");
        if (secNo) el.dataset.sec = secNo;
        // Headings are titles, not prose — don't enrich, so a heading never
        // wraps its own section number as a self-referential link (R1).
      } else {
        enrichInline(el, sectionNums); // after renderChunk's applyMath → KaTeX-safe
      }
      el.addEventListener("click", () => syncToChunk(el));
      paneReflow.appendChild(el);
    }
    buildPdfPane(doc, [...new Set(pageIdxs)]);
    // Continuous compare-mode scroll-sync (8e-4). Tear down any previous one
    // first so a reloaded document never leaves a stale handler driving the
    // new left pane (verify-cross §5.4).
    if (compareSync) compareSync.teardown();
    compareSync = initCompareSync({ contentEl: paneReflow, panePdf, layout });
    // Section TOC drawer + ref-jump (capture handler intercepts before sync).
    if (tocNav) {
      renderToc(buildSectionTree(data.chunks), tocNav, {
        onJump: (sec) => jumpToSection(sec, paneReflow),
        onSelect: (headingChunkId) =>
          selectSectionByHeading(headingChunkId, data.chunks, paneReflow),
      });
    }
    wireRefJump(paneReflow);
    initChat({ docId: Number(doc), contentEl: paneReflow });
  } catch (e) {
    paneReflow.innerHTML = `<div class="err">로드 실패: ${e.message}</div>`;
    console.error(e);
  }
}

// Auto-init only when the real page DOM is present (so unit tests can
// import ``renderChunk`` without the fetch/listener side effects firing).
if (paneReflow && layout) {
  for (const radio of document.querySelectorAll('input[name="mode"]')) {
    radio.addEventListener("change", (e) => {
      layout.dataset.mode = e.target.value;
      // compare → overlay (clear body margin); single → restore it (R9).
      syncPaneMargin({ doc: document });
      // Switching INTO compare: sync the left pane to the already-visible page
      // immediately, rather than waiting for the next scroll event (§5.3).
      if (e.target.value === "compare" && compareSync) {
        compareSync.recompute();
        compareSync.syncNow();
      }
    });
  }
  if (tocToggle && tocNav) {
    tocToggle.addEventListener("click", () => {
      const opening = tocNav.hasAttribute("hidden");
      if (opening) tocNav.removeAttribute("hidden");
      else tocNav.setAttribute("hidden", "");
      tocToggle.setAttribute("aria-expanded", String(opening));
    });
  }
  load();
}

// ``buildPdfPane`` is exported only as a test seam (the page-render error
// fallback at L112-114 lives inside it). Nothing in production imports it;
// auto-init is unchanged — so this adds no behavior, only testability.
export { buildPdfPane, initCompareSync, pickCurrentPage, renderChunk, syncToChunk };
