## 1. Over-engineering

- Deleting [page_view.js](/home/hyunlord/github/ht_lens/src/ht_lens/api/static/js/components/page_view.js) and replacing it with `stage_container.js` + `page_row.js` + `pane.js` + a `viewer.js` bootstrap rewrite is too much surface for one phase. `renderPageView()` already owns rotation fallback, overlay `data-mode`, pin rendering, and bbox scaling; wrap it in virtualization first and defer renderer decomposition.

- The planned `PageSummary` shape in [schemas.py](/home/hyunlord/github/ht_lens/src/ht_lens/api/schemas.py) includes `rotation`, `render`, and `block_count`, but the placeholder-row use case only needs stable row dimensions. `block_count`, `viewMode` localStorage migration, and debounced `?page=N` persistence are not required by the ROADMAP Phase 6b DoD and add new failure modes for no DoD gain.

## 2. Hidden assumptions

- The plan assumes the current single-page state model survives a continuous-scroll viewer. It does not. [viewer.js](/home/hyunlord/github/ht_lens/src/ht_lens/api/static/js/viewer.js) still revolves around one `currentPage`; `findBlockData()`, `repaintPage()`, `jumpToThread()`, and `handleRetranslate()` all depend on that singleton. Adding `pageMetaById` in [state.js](/home/hyunlord/github/ht_lens/src/ht_lens/api/static/js/state.js) does not solve page-data ownership.

- `waitForBlockMounted()` polling 50ms x 40 assumes page fetch + mount + font-fit completes within 2 seconds and that `.block[data-block-id=...]` points at the right element after mode switches. If that assumption fails, search hits and sidebar jumps become nondeterministic instead of merely slow.

- The plan silently changes URL/history semantics from the current `history.pushState` page-navigation model in [viewer.js](/home/hyunlord/github/ht_lens/src/ht_lens/api/static/js/viewer.js) to debounced `replaceState`. That assumes losing per-page back/forward behavior is acceptable. It is not stated, and it directly conflicts with the existing `popstate` contract.

- The DoD requires “200 페이지 PDF” smoothness, but the evidence plan only measures 52 pages on `sample_ko.pdf`. That assumes page count is the dominant factor. In this codebase, PNG dimensions (`Page.pixel_width`/`pixel_height` in [models.py](/home/hyunlord/github/ht_lens/src/ht_lens/db/models.py)) are the real memory driver.

## 3. Edge cases

- Rotated pages are a known open issue from Phase 4/6, and [page_view.js](/home/hyunlord/github/ht_lens/src/ht_lens/api/static/js/components/page_view.js) currently degrades safely with `rotation-banner`. The plan deletes that file while Phase 6c explicitly defers rotation support. Mixed-rotation documents will regress unless the new row/pane path preserves the same fallback.

- Partially translated documents are not handled. [block.js](/home/hyunlord/github/ht_lens/src/ht_lens/api/static/js/components/block.js) currently marks translation fallback with `data-fallback="original"`. In `both` mode, if `pane.js` does not preserve that behavior, the user gets two identical panes with no indication that translation is missing.

- Async races are under-specified: `mountPage()` fetch resolving after `unmountPage()`, `cycleViewMode()` rebuilding rows during in-flight fetches, and `openPanel()` coercing `viewModeActual` while jump navigation is waiting. The current code uses `navToken` and `panelToken` to prevent stale paints; the plan defines no equivalent per-page cancellation rule.

## 4. Alternative approaches

- Keep [page_view.js](/home/hyunlord/github/ht_lens/src/ht_lens/api/static/js/components/page_view.js) and virtualize around it. A `stage_container` that mounts existing `renderPageView()` output gives you continuous scroll with far less regression risk than re-implementing page rendering across `page_row.js` and `pane.js`.

- Preserve `history.pushState` for explicit navigation in `navigateTo()` and use `replaceState` only for passive scroll-driven active-page updates. That keeps browser back/forward useful while still avoiding history spam during free scroll.

- Replace `waitForBlockMounted()` polling with an event or Promise from `mountPage()`, plus `AbortController` for stale fetch cancellation. Browser APIs already solve this; hard-coded 2-second polling is the weakest synchronization point in the plan.

## 5. Missing tests

- `tests/integration/test_static_serving.py` grep markers are not enough for this phase. Add a runtime JS test such as `tests/integration/test_stage_container_js.py::test_mount_page_ignores_stale_fetch_after_unmount`. The repo already uses real jsdom-style tests in [test_confirm_modal_js.py](/home/hyunlord/github/ht_lens/tests/integration/test_confirm_modal_js.py) and [test_render_markdown_js.py](/home/hyunlord/github/ht_lens/tests/integration/test_render_markdown_js.py); use that pattern here.

- Add `tests/integration/test_viewer_history_js.py::test_explicit_navigation_pushes_history_but_scroll_updates_replace_state`. The plan changes navigation semantics in [viewer.js](/home/hyunlord/github/ht_lens/src/ht_lens/api/static/js/viewer.js) without any regression guard.

- Add `tests/integration/test_viewer_multpage_js.py::test_retranslate_updates_target_block_in_all_visible_panes`. `handleRetranslate()` in [viewer.js](/home/hyunlord/github/ht_lens/src/ht_lens/api/static/js/viewer.js) currently mutates only `currentPage.blocks`, which is incompatible with mounted multi-page state.

- Add `tests/integration/test_viewer_multpage_js.py::test_jump_to_thread_waits_for_mount_then_opens_panel_on_target_page`. The plan claims Phase 5 chat flows remain intact, but `jumpToThread()` is one of the highest-risk paths after moving from single-page to continuous scroll.

- Add `tests/integration/test_api_pages_summary.py::test_pages_summary_preserves_rotation_and_render_dims_per_page` and `::test_pages_summary_handles_mixed_page_sizes`. A simple count/order test will miss placeholder-height bugs that directly break the Phase 6b scroll DoD.

- Add `tests/integration/test_viewer_multpage_js.py::test_translation_pane_marks_original_fallback_when_translation_missing` and `::test_rotated_page_row_shows_rotation_banner`. Both are existing viewer contracts today; the plan deletes the current renderer without locking either regression.
