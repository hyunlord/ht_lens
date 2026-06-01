## 1. Over-engineering

The plan pulls `Page` row generation into Phase 8c under “v2 page render,” including `width/height/bg_image_path/pixel_*` population. That is a schema/data-topology concern deferred from Phase 8a/8e, not required to prove the Phase 8c ROADMAP DoD. A deterministic render cache plus `/v2/documents/{id}/page/{page_idx}/image` would prove the side-by-side viewer without mutating the shared `pages` table.

Decision A hard-codes a second DB, `data/ht_lens_v2.db`, as a phase artifact. That adds operational complexity to every API/test path while `src/ht_lens/api/app.py` still defaults to `data/ht_lens.db` via `_db_path_from_env()`. The plan should either make the DB override an explicit verified env contract or avoid baking a dev DB into the feature design.

The proposed split into `reflow.js` plus `js/components/chunk_render.js` is probably premature. Phase 8c has one page and one renderer. A single module is simpler until Phase 8d adds chat/pin interaction and proves reusable chunk components are needed.

`/v2/chunks/{id}/image` plus `/v2/documents/{doc_id}/page/{page_idx}/image` duplicates image-serving patterns already present in `src/ht_lens/api/routers/pages.py`. Reusing a common path validator/helper is enough; do not create parallel security behavior that later has to be reconciled.

## 2. Hidden assumptions

The plan assumes the API will actually run against `data/ht_lens_v2.db`, but `create_app()` only reads `HT_LENS_DB_URL` or falls back to `data/ht_lens.db`. If tests or verification forget the env var, Phase 8c will silently inspect the 1.x DB with no chunks and produce false failures or empty “success.”

The page render plan assumes the original source PDF path is available. `Document` in `src/ht_lens/db/models.py` has `filename`, `src_pdf_sha256`, and `markdown_path`, but no durable `source_pdf_path`. Rendering “source PDF page → PNG” is underspecified unless Phase 8a’s ingest pipeline already stores a recoverable PDF path outside the model.

The DoD mapping downgrades ROADMAP’s “좌우 비교 hilight sync (chunk bbox)” to page-level sync. That is not a harmless interpretation; it changes chunk bbox sync into page sync. If exact bbox sync is out of scope, the plan needs a Planner-visible DoD exception, not a parenthetical “best-effort.”

The image-serving plan assumes MinerU image assets fit the existing `pages._validate_image_path` pattern, but that validator only accepts `.png`. `tests/fixtures/mineru/content_list_sample.json` and `parse_content_list()` preserve image paths like `images/fig1.jpg`; a copied PNG-only guard will break normal figure rendering.

The JS test strategy assumes jsdom coverage is dependable, but existing tests such as `tests/integration/test_render_markdown_js.py` skip when system jsdom is absent. A skipped jsdom test cannot be the primary evidence for KaTeX, DOM rendering, or side-by-side toggle behavior.

## 3. Edge cases

Table chunks are explicitly out of scope, but `src/ht_lens/ingest_mineru/content_list.py` preserves `table` chunks and `src/ht_lens/translate/chunk_pipeline.py` translates them. If doc7 contains a table, the reflow stream will either drop it or render it as an unknown block, damaging the “읽기 자연스러움” DoD. Add at least a graceful table fallback.

Missing or empty `bbox_json` is already valid: `parse_content_list()` stores `"[]"` for malformed bboxes. The sync plan needs behavior for chunks with no bbox: page scroll only, no overlay, and no JS exception.

Rotated pages are not covered. `Page.rotation` exists in `src/ht_lens/db/models.py`, and existing tests include rotated-page coverage. A page-level PNG rendered by PyMuPDF may have pixel dimensions and coordinate orientation that do not match MinerU `bbox`, especially for cropbox/rotation cases.

Long display equations and mixed Korean/Latin paragraphs can overflow a 760px reading column. The plan names typography but does not specify overflow handling for KaTeX display blocks, long URLs, model names, or unbreakable math tokens.

Image chunks can have missing files, relative paths, absolute paths, `.jpg`, `.jpeg`, or `.png`. The plan only mentions traversal guards; it does not define the response for a DB-valid but missing MinerU asset, which should be a controlled 404/500 and a visible fallback in `reflow.html`.

## 4. Alternative approaches

Use a pure read-model endpoint first: build `ReflowResponse` from `Document`, `Chunk`, and `ChunkTranslation`, and render source pages from a cache helper keyed by `(doc_id, page_idx)` without inserting `Page` rows. This keeps Phase 8c focused on the viewer and avoids entangling 2.0 chunks with 1.x `Page`/`Block` assumptions.

For sync, implement an explicit two-tier contract: mandatory page sync now, optional bbox overlay only when a valid four-number bbox and page render dimensions exist. Report `sync_mode: "page"` or `"bbox"` per chunk in `/v2/documents/{id}/reflow`. That is easier to test than hidden “best-effort” DOM behavior.

For frontend tests, prefer Playwright as the authoritative viewer check and keep jsdom for small pure functions only. Phase 8c is a visual/layout phase; Playwright can verify real module loading, real KaTeX CSS, image loading, scroll behavior, and console errors better than opportunistic jsdom.

## 5. Missing tests

Add `test_reflow_api_uses_only_translated_rows`: failed or missing `ChunkTranslation.status` must not masquerade as valid translated content; fallback behavior should be explicit per type.

Add `test_reflow_api_preserves_table_chunk_with_fallback`: a `table` chunk from `parse_content_list()` must appear in the response and render safely, even if full table UX is deferred to 8e.

Add `test_v2_figure_image_allows_mineru_jpg_and_rejects_traversal`: lock the real MinerU `.jpg` path case separately from traversal rejection.

Add `test_reflow_page_image_requires_configured_source_pdf`: if no source PDF path is available, the endpoint should fail deterministically instead of creating bogus `Page` rows or crashing inside PyMuPDF.

Add `test_reflow_click_chunk_without_bbox_scrolls_page_only`: chunks with `bbox=[]` must not throw and must still satisfy page-level sync.

Add a Playwright test named `test_reflow_viewer_doc7_console_clean_katex_figure_and_toggle`: load real `reflow.html`, assert no `pageerror`, at least one `.katex`, at least one figure image, and successful single/compare toggle.
