## 1. Over-engineering

The plan is doing a full client-side document outline system (`buildSectionTree`, `renderToc`, `jumpToSection`, `selectSection`) inside Phase 8d-1 even though ROADMAP Phase 8d’s actual DoD is chat/pins/RAG chunk reanchor. A minimal section selector for 8d-2 context would satisfy the user need with less UI/state surface; nested TOC rendering, synthetic missing-prefix groups, flash behavior, and `CustomEvent('sectionselect')` are already a separate navigation feature.

`js/sections.js` risks becoming a premature frontend domain model. The source of truth for sections should probably be closer to `/v2/documents/{doc_id}/reflow` or the chunk API, because 8d-2 chat and pins will need the same section boundaries. Deriving the tree only in `reflow.js` means later backend chat context must reimplement the same boundary logic or trust opaque client `chunkIds`.

The “prefix group graceful” behavior is underspecified and likely overbuilt. If this phase only needs selectable sections present in doc7, synthetic labels for missing `28.3` nodes can be deferred; otherwise tests will lock arbitrary UX that may not generalize to other extracted chapters.

## 2. Hidden assumptions

The plan assumes heading text still begins with the numeric section prefix. Current `renderChunk` uses `chunk.translated ?? chunk.original` in `src/ht_lens/api/static/js/reflow.js:24`, so if qwen translates or prefixes headings as `[KO] 28.4 ...`, `parseSectionNo(text)` may fail unless it explicitly parses `chunk.original`. The plan does not state which field drives section identity.

The citation regex is unsafe for this codebase’s own fixture convention. `\[[A-Za-z][A-Za-z.'-]*(?:\+)?\d{0,4}[a-z]?\]` allows zero digits, so `[KO]` matches. Existing reflow tests and sample chunks use `[KO]` prefixes in `tests/integration/test_reflow_viewer_js.py`; the plan would style translation markers as citations.

The “innerHTML 미사용 → XSS 무관” claim is too broad. New `renderToc(tree)` is not specified as `textContent`-only, and existing `load()` already writes `e.message` into `paneReflow.innerHTML` at `src/ht_lens/api/static/js/reflow.js:162`. Do not let the challenge accept this as a security proof.

The plan assumes all useful references are intra-document headings. ROADMAP Phase 8d is moving toward cross-doc RAG, and academic prose often references sections not present in the current `/v2/reflow` response. Membership-only linkification silently drops valid references outside the current chapter.

## 3. Edge cases

Reference clicks will bubble into the existing chunk click handler added at `src/ht_lens/api/static/js/reflow.js:157`. Without explicit `preventDefault()` and `stopPropagation()`, clicking `.rf-ref` can both jump to the referenced heading and mark/sync the source chunk, causing wrong active state and compare-pane scroll.

Section selection boundaries are brittle around non-heading chunks. A section starting at `28.4.2` followed by figures, tables, equations, then `28.4.2.1` needs clear inclusion rules. The plan says “next 동급/상위 section 직전” but does not define whether child subsections are included when selecting a parent.

Dotted-number parsing will confuse chapter numbers, decimals, versions, and equation-like text if headings happen to contain them. Membership filtering protects body references, but `parseSectionNo` on headings still needs cases like `Appendix A.1`, `28.4.2. Multinomial PCA`, `§28.4`, full-width punctuation, and headings with Korean/English prefixes.

KaTeX safety is under-tested. Running `enrichInline` after `applyMath` must skip every text node under KaTeX output, including `.katex`, `.katex-html`, `.katex-mathml`, and display wrappers. A `closest(".katex")` check is required; checking only direct parent classes will corrupt rendered math.

The layout change is not analyzed. `reflow.html` currently has only `.pane--pdf` and `.pane--reflow` inside `.layout`, with compare mode fixed at `grid-template-columns: 1fr 1fr` in `reflow.css:38`. Adding `<nav id="toc">` can break compare mode, sticky header height, mobile width, and scroll containers unless grid modes are redesigned.

## 4. Alternative approaches

Add section metadata to the `/v2/documents/{doc_id}/reflow` response in `src/ht_lens/api/routers/reflow.py`: `sections: [{sec_no, title, heading_chunk_id, start_order_idx, end_order_idx}]`. This avoids duplicating section-boundary logic in 8d-2 chat and makes tests backend-verifiable with real chunk ordering.

If frontend-only is locked, derive section identity from `chunk.original` and attach `data-sec` during `renderChunk(chunk)`, not by reparsing rendered DOM text later. That keeps parsing independent from Korean translation artifacts and lets `selectSection` operate over `.chunk[data-sec]` / order, not fragile text content.

For inline enrichment, use a single `TreeWalker` that emits a `DocumentFragment` per text node and requires a digit in citations. That is still dependency-free but safer than repeated `splitText` mutation, which is easy to get wrong with adjacent matches, multiple matches in one node, and nested wrappers.

For the TOC, a flat list grouped by observed heading order may be better for 8d-1 than a nested synthetic tree. It directly supports jump/select, avoids fake missing nodes, and can be upgraded later when 8e gives better heading hierarchy.

## 5. Missing tests

Add `test_citation_regex_does_not_style_digitless_translation_markers`: verify `[KO]`, `[EN]`, and `[Note]` are not `.rf-cite`, while `[BJ05]` and `[Kha+10]` are.

Add `test_section_tree_parses_original_heading_when_translation_changes_prefix`: seed a heading with `original: "28.4.2 Multinomial PCA"` and `translated: "[KO] 다항 PCA"` and require section `28.4.2` to exist.

Add `test_ref_click_does_not_trigger_chunk_sync`: clicking `.rf-ref` should call `jumpToSection` without adding `.active` to the source chunk or scrolling the PDF pane via `syncToChunk`.

Add `test_select_parent_section_includes_child_subsections_until_next_sibling`: selecting `28.4` should include `28.4.1` and `28.4.2` chunks but stop before `28.5`.

Add `test_enrich_inline_handles_multiple_adjacent_matches_in_one_text_node`: one paragraph containing `[BJ05][CDS02] see 28.3.5 and 28.4.2` should produce all wrappers without dropping text.

Add `test_toc_compare_layout_keeps_pdf_and_reflow_visible`: jsdom/CSS-light check or Playwright screenshot for `data-mode="compare"` after adding `#toc`, because the current grid only accounts for two panes.
