"use strict";

// ht_lens 2.0 reflow — section tree / jump / select (Phase 8d-1).
//
// Section identity comes from the heading's ENGLISH original ("28.4.2
// Multinomial PCA" -> "28.4.2"), never the translation, so a translated
// prefix like "[KO] 다항 PCA" can't break it (debate R2). The tree is
// built from observed headings only — no synthetic missing nodes
// (debate R9); each node parents to its nearest observed dotted-prefix
// ancestor, else becomes a root.

/** Leading dotted section number of a heading's original text, or null.
 *  Tolerates a leading "§"/whitespace and a single trailing dot. */
export function parseSectionNo(text) {
  if (!text) return null;
  const m = /^\s*§?\s*(\d+(?:\.\d+)*)\.?(?=\s|$)/.exec(text);
  return m ? m[1] : null;
}

const depthOf = (secNo) => secNo.split(".").length;
const isAncestor = (anc, sec) => sec.startsWith(anc + ".");

/** Nested tree of {secNo,title,chunkId,order,depth,children} from heading
 *  chunks (in document order). Unnumbered headings are depth-1 roots. */
export function buildSectionTree(chunks) {
  // Chunks arrive in document order: the reflow API orders by order_idx
  // but does NOT expose the field, so we trust response order rather than
  // re-sorting on an absent key (verify-cross R1).
  const headings = chunks
    .filter((c) => c.type === "heading")
    .map((c) => {
      const secNo = parseSectionNo(c.original ?? "");
      return {
        secNo,
        title: (c.translated ?? c.original ?? "").trim(),
        chunkId: c.id,
        depth: secNo ? depthOf(secNo) : 1,
        children: [],
      };
    });
  const roots = [];
  const stack = []; // observed ancestor chain, increasing depth
  for (const node of headings) {
    if (!node.secNo) {
      roots.push(node);
      stack.length = 0;
      continue;
    }
    while (stack.length && !isAncestor(stack[stack.length - 1].secNo, node.secNo)) {
      stack.pop();
    }
    if (stack.length) stack[stack.length - 1].children.push(node);
    else roots.push(node);
    stack.push(node);
  }
  return roots;
}

/** Chunk ids belonging to a section: from its heading until the next
 *  heading of same-or-shallower depth (so a parent includes its children;
 *  debate R7). Returns {secNo, headingChunkId, chunkIds}; headingChunkId is
 *  the concrete heading row the 8d-2 chat anchors to (challenge R1). */
export function computeSectionChunks(secNo, chunks) {
  // Trust document order from the API (verify-cross R1: no order_idx field).
  const ordered = chunks;
  const head = ordered.findIndex(
    (c) => c.type === "heading" && parseSectionNo(c.original ?? "") === secNo,
  );
  if (head < 0) return { secNo, headingChunkId: null, chunkIds: [] };
  const startDepth = depthOf(secNo);
  let end = ordered.length;
  for (let i = head + 1; i < ordered.length; i++) {
    const c = ordered[i];
    if (c.type !== "heading") continue;
    const sn = parseSectionNo(c.original ?? "");
    if (sn && depthOf(sn) <= startDepth) {
      end = i;
      break;
    }
  }
  return {
    secNo,
    headingChunkId: ordered[head].id,
    chunkIds: ordered.slice(head, end).map((c) => c.id),
  };
}

/** Highlight a section's chunks + emit a ``sectionselect`` CustomEvent
 *  carrying secNo + the heading chunk id. The 8d-2 chat anchors a section
 *  thread to ``headingChunkId`` (challenge R1) and resolves the range
 *  server-side rather than trusting opaque client ids (debate R3). */
export function selectSection(secNo, chunks, contentEl) {
  const { headingChunkId, chunkIds } = computeSectionChunks(secNo, chunks);
  const idset = new Set(chunkIds.map(String));
  for (const el of contentEl.querySelectorAll(".chunk.section-selected")) {
    el.classList.remove("section-selected");
  }
  for (const el of contentEl.querySelectorAll(".chunk")) {
    if (idset.has(el.dataset.chunkId)) el.classList.add("section-selected");
  }
  contentEl.dispatchEvent(
    new CustomEvent("sectionselect", {
      detail: { secNo, headingChunkId, chunkIds },
      bubbles: true,
    }),
  );
  return { secNo, headingChunkId, chunkIds };
}

/** Section range from a CONCRETE heading chunk id (mirrors the Python
 *  ``section_chunk_range``). Resolves duplicate/unnumbered section numbers
 *  unambiguously — the chat path must use this, not the secNo-first variant
 *  (verify-cross R1). Returns {headingChunkId, secNo, chunkIds}. */
export function computeSectionByHeading(headingChunkId, chunks) {
  const head = chunks.findIndex((c) => c.id === headingChunkId);
  if (head < 0) return { headingChunkId, secNo: null, chunkIds: [] };
  const secNo = parseSectionNo(chunks[head].original ?? "");
  const startDepth = secNo ? depthOf(secNo) : null;
  let end = chunks.length;
  for (let i = head + 1; i < chunks.length; i++) {
    const c = chunks[i];
    if (c.type !== "heading") continue;
    if (startDepth === null) {
      end = i; // unnumbered heading → stop at the next heading of any kind
      break;
    }
    const sn = parseSectionNo(c.original ?? "");
    if (sn && depthOf(sn) <= startDepth) {
      end = i;
      break;
    }
  }
  return { headingChunkId, secNo, chunkIds: chunks.slice(head, end).map((c) => c.id) };
}

/** Highlight + emit ``sectionselect`` for a section identified by its heading
 *  chunk id (verify-cross R1 — duplicate-safe). The TOC/chat path uses this. */
export function selectSectionByHeading(headingChunkId, chunks, contentEl) {
  const { secNo, chunkIds } = computeSectionByHeading(headingChunkId, chunks);
  const idset = new Set(chunkIds.map(String));
  for (const el of contentEl.querySelectorAll(".chunk.section-selected")) {
    el.classList.remove("section-selected");
  }
  for (const el of contentEl.querySelectorAll(".chunk")) {
    if (idset.has(el.dataset.chunkId)) el.classList.add("section-selected");
  }
  contentEl.dispatchEvent(
    new CustomEvent("sectionselect", {
      detail: { secNo, headingChunkId, chunkIds },
      bubbles: true,
    }),
  );
  return { secNo, headingChunkId, chunkIds };
}

/** Scroll to a section's heading chunk and flash it. */
export function jumpToSection(secNo, contentEl) {
  const target = contentEl.querySelector(`.chunk[data-sec="${secNo}"]`);
  if (!target) return false;
  for (const f of contentEl.querySelectorAll(".rf-flash")) f.classList.remove("rf-flash");
  target.classList.add("rf-flash");
  target.scrollIntoView({ behavior: "smooth", block: "start" });
  return true;
}

/** Capture-phase delegation: a ``.rf-ref`` click jumps WITHOUT bubbling
 *  into the per-chunk syncToChunk handler (debate R4). */
export function wireRefJump(contentEl) {
  contentEl.addEventListener(
    "click",
    (e) => {
      const ref = e.target.closest && e.target.closest(".rf-ref");
      if (ref && ref.dataset.sec) {
        e.preventDefault();
        e.stopPropagation();
        jumpToSection(ref.dataset.sec, contentEl);
      }
    },
    true,
  );
}

function buildUl(nodes, onJump, onSelect) {
  const ul = document.createElement("ul");
  for (const node of nodes) {
    const li = document.createElement("li");
    const a = document.createElement("a");
    a.className = "toc-link";
    a.textContent = node.title || node.secNo || "(untitled)";
    if (node.secNo) {
      a.dataset.sec = node.secNo;
      a.addEventListener("click", (e) => {
        e.preventDefault();
        if (onJump) onJump(node.secNo);
      });
    }
    li.appendChild(a);
    if (node.chunkId != null && onSelect) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "toc-select";
      btn.textContent = "선택";
      btn.dataset.chunkId = String(node.chunkId);
      btn.addEventListener("click", (e) => {
        e.preventDefault();
        onSelect(node.chunkId); // pass the concrete heading chunk id (R1, dup-safe)
      });
      li.appendChild(btn);
    }
    if (node.children && node.children.length) {
      li.appendChild(buildUl(node.children, onJump, onSelect));
    }
    ul.appendChild(li);
  }
  return ul;
}

/** Render the nested TOC (textContent-only; debate R10). Callbacks:
 *  ``onJump(secNo)`` / ``onSelect(secNo)``. */
export function renderToc(tree, navEl, { onJump, onSelect } = {}) {
  navEl.replaceChildren();
  navEl.appendChild(buildUl(tree, onJump, onSelect));
}
