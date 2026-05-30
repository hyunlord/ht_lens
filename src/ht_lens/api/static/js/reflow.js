"use strict";

// ht_lens 2.0 reflow reading view (Phase 8c).
// Single module (chat/pin components arrive in 8d). Renders chunk(8a) +
// translation(8b) as a flowed article; KaTeX via the vendored applyMath
// (Phase 6i). Compare mode does page-level sync (challenge): clicking a
// chunk scrolls the left PDF pane to that chunk's source page.

import { applyMath } from "./utils/render_markdown.js";
import { enrichInline } from "./utils/enrich_inline.js";
import { initChat } from "./chat.js";
import {
  buildSectionTree,
  jumpToSection,
  parseSectionNo,
  renderToc,
  selectSection,
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
    // Section TOC drawer + ref-jump (capture handler intercepts before sync).
    if (tocNav) {
      renderToc(buildSectionTree(data.chunks), tocNav, {
        onJump: (sec) => jumpToSection(sec, paneReflow),
        onSelect: (sec) => selectSection(sec, data.chunks, paneReflow),
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
export { buildPdfPane, renderChunk, syncToChunk };
