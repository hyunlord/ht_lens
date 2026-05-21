## 1. Over-engineering

- The file split in `.claude/phases/phase-4/plan.md` is too aggressive for a first static viewer: `src/ht_lens/api/static/js/{api,state,index,viewer,components/*,utils/*}` plus Phase 5 scaffolding like `state.onBlockClick`, hidden right-slot DOM, and shared CSS tokens. `ROADMAP.md` Phase 4 only requires a readable viewer with click placeholder; the extensibility hooks can wait until Phase 5 actually uses them.

- `index.html` as a document dashboard with cards showing `filename`, `src→tgt`, `num_pages`, `status`, and `created_at` is scope creep. The roadmap deliverable is the reader, not a mini home screen. Every extra empty/error/list-state here increases surface area before `viewer.html` itself is proven against the DoD.

- The planned `utils/font_fit.js` is trying to be a layout engine too early. Per-language width constants, header multipliers, empty-block placeholders, table handling, and ellipsis policy are a lot of speculative behavior for a phase whose acceptance is still manual “80% fit.” Start with a narrower text-block-only policy and collect concrete failure cases for Phase 6.

## 2. Hidden assumptions

- Approach §2/§7 uses `window.location.href = ...` for every page move. That assumes full reloads plus refetching `GET /documents/{doc}` and `src/ht_lens/api/routers/pages.py:get_page_image` 200dpi PNGs still satisfy the `ROADMAP.md` Phase 4 DoD item “줌·이동 부드러움.” That is unstated and likely false on larger documents.

- Approach §6’s `computeFontSize(bboxW, bboxH, text, lang)` assumes a single reliable language weight. But `src/ht_lens/api/schemas.py` exposes no per-block language, and the viewer switches between `original_text` and `translated_text`. Mixed CJK+Latin blocks and translated text expansion make the `ko/en/other` heuristic under-specified from the start.

- Approach §11 assumes `rotation != 0` pages can simply be replaced with a warning and no image/overlay. `ROADMAP.md` lists rotation as a Phase 4 risk, not a license to make pages unreadable. If the “실제 문서 한 권” used for verification contains rotated pages, this plan fails the DoD outright. The same plan also assumes silent `translated_text || original_text` fallback is acceptable, which hides partially untranslated pages.

## 3. Edge cases

- `src/ht_lens/api/routers/pages.py:get_page` returns raw bbox data from the DB, but Approach §5 multiplies it directly with no clamp or sanity check. Zero-width, negative, or out-of-bounds boxes from extraction noise will create inverted or off-canvas overlays.

- Long translated English strings, URLs, and mixed-script blocks will break the fitting model. The heuristic counts only explicit `\n`, while the CSS in Approach §6 uses `white-space: pre-wrap`, so browser wrapping creates extra lines the algorithm never budgets for. `text-overflow: ellipsis` also does not rescue multi-line `pre-wrap` blocks reliably.

- OCR-poor pages with empty text blocks will render `[빈 {type} 블록]` all over the page. That is synthetic content that was never in the document and will actively reduce readability on image-heavy or badly extracted pages, exactly the cases where the viewer needs to degrade gracefully.

## 4. Alternative approaches

- Keep vanilla JS, but make `viewer.html` a persistent shell and update page data in place with `history.pushState`. That is still framework-free, but it matches the Phase 4 “smooth navigation” DoD much better than full reloads on every arrow key.

- Use `PageRead.render.pixel_w` and `pixel_h` from `src/ht_lens/api/schemas.py` and `src/ht_lens/api/routers/pages.py:get_page` as the overlay’s intrinsic coordinate space. Size one stage to render pixels, place blocks there once, and zoom that stage. It is simpler and less error-prone than recomputing scale from browser layout every render.

- Replace hard-coded `avgCharW` weights with browser measurement in `utils/font_fit.js` using `canvas.measureText` or temporary DOM measurement plus binary search. No dependency is needed, and it will behave far better on mixed CJK+Latin text than the proposed constants.

## 5. Missing tests

- `test_viewer_html_references_resolvable_assets` should exist. The proposed `tests/integration/test_static_serving.py` checks files one by one and even `/static/.gitkeep`, but that will not catch broken `<script type="module">`, bad import paths, or wrong CSS links in `viewer.html`.

- `test_index_empty_state_for_no_documents` should exist. The plan promises a friendly “no documents yet” state in `index.js`, but the test strategy never exercises `/documents` returning `[]`.

- `test_viewer_handles_invalid_query_and_missing_page` should exist. `viewer.js` parses `doc` and `page` from the URL, but the plan has no test for malformed query strings, nonexistent document IDs, or `page` values beyond `DocumentRead.num_pages`.

- `test_font_fit_mixed_cjk_long_ascii_does_not_overflow_bbox` should exist. The core Phase 4 DoD item is font fitting, yet the plan explicitly chooses “JS unit test 없음.” That is the wrong place to skip automation.

- Verification should cover a rotated-page fixture and a partially translated fixture, not just “한국어 1, 영문 1 페이지.” The roadmap’s risks are rotated pages and real-world layout drift; the current verify plan is biased toward the easiest happy path.
