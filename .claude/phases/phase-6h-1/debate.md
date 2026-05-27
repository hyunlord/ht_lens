## 1. Over-engineering
- `scripts/backfill_block_bbox.py` is trying to solve extraction repair, PDF discovery (`Document.src_pdf_sha256` / `filename`), fleet-wide iteration (`--all`), and fuzzy matching (`bbox center proximity`) at once. `ROADMAP.md` Phase 6h-1 is an extraction-quality fix, not a mini migration framework. This is too much machinery for one phase.
- The backfill mutates `blocks.original_text` as well as `bbox_json`. That widens a geometry fix into a semantic data rewrite and drags translation, search, export, and RAG behavior into scope. If the phase is really Pattern A bbox aggregation, changing source text is unnecessary blast radius.
- Removing hot-fix A1 in `src/ht_lens/api/static/js/components/block.js` and `src/ht_lens/api/static/css/viewer.css` in the same phase is premature coupling. The plan makes backfill optional and best-effort, so old docs will still exist with Phase 6h symptoms; defer A1 removal until repaired docs are guaranteed.

## 2. Hidden assumptions
- The plan assumes the roadmap can be reinterpreted. `ROADMAP.md` says Phase 6h-1 deliverables are “multi-line bbox union”, “backfill script”, and `Alembic 0005`; the plan explicitly says frontend unchanged and “Alembic migration out”. If that reinterpretation is wrong, this plan cannot claim the phase DoD.
- It assumes the single probe on doc 7 p.862 invalidates the roadmap audit numbers (`1,613 severe`, `6,912 visual leak`) system-wide. But the plan drops those KPI checks entirely; there is no evidence path showing the new logic will move either metric.
- It assumes “translation / embedding preserve” survives `original_text` edits. That is false as written: `src/ht_lens/embedding/lookup.py::get_or_encode_block_vector` only protects the query block, while `src/ht_lens/embedding/search.py::search` still ranks candidate blocks by stale stored vectors with no `source_hash` validation.
- It assumes header detection is preserved by leaving `len(para_lines) <= _HEADER_MAX_LINES` untouched in `src/ht_lens/extract/blocks.py::group_page`. That only preserves raw PyMuPDF line count, not semantic line count. A one-line title split into 3 raw lines would still stop being a `header`.

## 3. Edge cases
- Tight-leading real multi-line text, superscripts/subscripts, equations, and ruby/furigana can exceed 50% Y-overlap without being the same visual line. `_should_concat_inline` would flatten real line breaks into spaces and corrupt `original_text`.
- The inverse case also exists: same visual-line fragments with slightly different ascender/descender boxes can miss the 50% threshold and stay newline-split. The plan presents 50% as if it were stable across fonts, but PyMuPDF bbox variance is exactly the problem domain here.
- `RawLine.direction` exists in `src/ht_lens/extract/_fitz.py`, but the proposed helper ignores it. Rotated pages and vertical writing already have regression surface in `tests/integration/test_rotated_page.py`; Y-overlap is not a safe predicate there.
- The backfill flow can create hybrid documents. If one page hits “bbox drift > 20pt” after earlier pages already queued updates, the plan still commits the accumulated mutations. Partial doc rewrites are worse than an all-or-nothing abort.

## 4. Alternative approaches
- Fix the roadmap defect at the extraction layer, not the string-join layer. Aggregate visual lines from spans/words in `src/ht_lens/extract/_fitz.py` or just before `group_page()` using `get_text("words", sort=True)` or span-level baseline clustering. That addresses text, bbox, and header semantic line count together.
- For repair, prefer a document-level re-extract/rewrite path that aborts the entire document on any mismatch. Matching by exact `(page_num, order_idx, block count)` for the whole doc is safer than per-page fuzzy center checks that can silently produce mixed old/new semantics.
- If the real UX symptom is `fitFontSize` miscounting explicit newlines, then treat that as a viewer fix in `src/ht_lens/api/static/js/utils/font_fit.js` or `block.js`. Do not claim Phase 6h-1 completion while leaving the roadmap’s bbox-aggregation contract unmet.

## 5. Missing tests
- There is no audit-style test or rerunnable script that measures the actual Phase 6h-1 KPI from `ROADMAP.md` (`1,613 -> <50`, `6,912 -> <500`). Five synthetic tests around `_join_lines` do not prove the phase outcome.
- Add a header regression test such as `test_inline_join_preserves_header_classification_for_split_visual_title` and another for the 3-fragment case. Right now the plan asserts “Header heuristic 보존” without evidence.
- Add a backfill atomicity test: `test_backfill_aborts_doc_without_writes_on_block_count_mismatch_or_bbox_drift`. “manual smoke” is not enough for the riskiest code in the plan.
- Add an embedding consistency test: mutate `blocks.original_text` after backfill and assert `/blocks/{id}/related` or `build_block_context_with_refs()` does not use stale candidate embeddings. The current code path in `embedding/search.py` makes this a real regression, not a theoretical one.
- If `ROADMAP.md` still requires `Alembic 0005`, add the corresponding migration test in `tests/integration/test_alembic.py` and bump `src/ht_lens/db/session.py::ALEMBIC_HEAD`. If the phase intentionally rejects that roadmap item, the plan must say so explicitly instead of silently omitting it.
