## 1. Over-engineering

The `reflow.js` plan observes every `.chunk` via `IntersectionObserver` and adds caching/safety flags for a one-way page-level sync. Phase 8c/ROADMAP only requires “좌우 비교 hilight sync (chunk bbox)” and Phase 8e requires “reflow viewer에서 전체 읽기”; for 8e-4, a simpler page-sentinel or scroll-handler keyed by `data-page-idx` would be easier to reason about than 3,338 observed targets.

The “scroll-sync 무한루프” mitigation is overstated. The plan is explicitly 우→좌 only, and current `syncToChunk()` in `src/ht_lens/api/static/js/reflow.js` has no left→right path. A safety flag and loop tests add complexity without protecting a real code path.

`_drop_nested_panel_images(chunks)` as a generic per-request render filter in `src/ht_lens/api/routers/reflow.py` is acceptable, but the plan’s “general 로직(doc 무관)” hides that the measured defect is exactly doc1 page2 Figure 28.18. Keep the helper narrow: image-only, same-page, caption-bearing container vs captionless child. Do not grow it into a general layout repair engine.

## 2. Hidden assumptions

The scroll-sync plan says `root=paneReflow`, but in current `reflow.js`, `paneReflow` is `#content` (`article`). The actual scroll container is `.pane--reflow` per `src/ht_lens/api/static/css/reflow.css:53`. If `IntersectionObserver` roots on the article instead of the scrollable pane, visibility calculations can be wrong or all chunks can appear inside the root.

The dedup rule assumes `caption truthy == whole figure` and `caption falsy == nested panel`. MinerU may emit captionless standalone figures, failed/empty captions, or a separate caption chunk. If that assumption is wrong, `_drop_nested_panel_images` will silently remove a real image from `/v2/documents/{doc_id}/reflow`.

The bbox containment rule assumes all image bboxes are normalized `[x0,y0,x1,y1]` in the same coordinate system. `ROADMAP.md` explicitly lists MinerU `content_list` schema stability as a risk; malformed, inverted, rotated-page, cropbox-adjusted, or page-scale-shifted bboxes would make “완전 포함” unreliable.

The plan assumes jsdom can validate `IntersectionObserver` behavior. It cannot unless the test fakes layout and callback ordering. That means the core behavior in `initCompareSync()` can pass tests while failing in Chromium.

## 3. Edge cases

A single very tall chunk or figure spanning most of the viewport can keep intersecting while the reader has moved into later chunks; with `threshold: 0` and a `-70%` bottom margin, “current top chunk” is not guaranteed. The plan does not define how to sort multiple `IntersectionObserverEntry` objects.

Fast scrolling across multiple pages can deliver entries out of document order. If the implementation picks the first callback entry, the left pane may jump backward or skip pages. The plan needs a deterministic rule based on `getBoundingClientRect().top` within `.pane--reflow`.

Mode toggling is underspecified. If the observer is initialized in reading mode, then the user switches to compare mode, the left PDF pane should sync to the already visible chunk immediately. Waiting for the next IO event will leave the left pane stale.

Dedup can break captionless legitimate figures: diagrams without captions, decorative model snapshots, or extracted charts where `image_caption` was not joined by `src/ht_lens/ingest_mineru/content_list.py`. “panel은 caption 없어 미임베딩” is not proof that it is safe to hide.

Equal bboxes are not discussed. `contains(a,b)` with `<=`/`>=` drops a captionless image with exactly the same bbox as a captioned one. That may be desired for duplicate crops, but it should be explicitly tested because it is not “nested panel” behavior.

## 4. Alternative approaches

For sync, prefer page sentinels over chunk observation: insert or identify the first rendered chunk per `page_idx`, observe only those page-boundary elements, and call the existing `syncToChunk()`-like page highlight path. This matches the phase’s page-level sync and reduces observer targets from thousands to page count.

Another viable frontend approach is a throttled `scroll` listener on `.pane--reflow` using precomputed chunk offsets and binary search. It is less elegant than IO, but it is deterministic, easy to test with synthetic offsets, and avoids IO callback-order ambiguity.

For dedup, consider applying the filter after `ReflowChunk` construction rather than on ORM `Chunk` rows. That uses already parsed `bbox` from `_bbox_or_none()` and avoids duplicating bbox parsing semantics. The downside is losing direct `bbox_json`, but this endpoint already owns the API representation.

If this defect is truly only MinerU multi-panel duplication, a named helper like `_drop_captionless_images_contained_by_captioned_image` is better than `_drop_nested_panel_images`; the latter sounds like semantic figure analysis, which the code is not doing.

## 5. Missing tests

Add `test_compare_sync_uses_scrollable_reflow_pane_not_article`: load real `reflow.html` structure and assert `IntersectionObserver.root` is `.pane--reflow`, not `#content`.

Add `test_compare_sync_selects_topmost_visible_chunk_when_multiple_intersect`: fake two entries from different pages in one callback and assert the page nearest the top of the scroll container wins.

Add `test_compare_toggle_immediately_syncs_current_visible_page`: initialize in `data-mode="single"`, mark a visible chunk, switch to compare, and assert the matching `.pdf-page[data-page-idx]` scrolls without requiring another scroll event.

Add `test_compare_sync_disconnects_or_noops_after_reloading_document`: call `load()` twice or simulate a document reload and assert old observed chunks cannot scroll the new left pane.

Add `test_dedup_preserves_captionless_standalone_image_inside_text_page`: a captionless image with no captioned containing image must stay visible.

Add `test_dedup_rejects_malformed_or_inverted_bbox_without_drop`: malformed `bbox_json`, `[]`, `NaN`, or `x1 < x0` should not drop anything.

Add `test_dedup_equal_bbox_duplicate_policy`: lock whether exact same bbox captioned/captionless images are dropped or preserved.

Add `test_get_reflow_dedup_keeps_chat_anchor_accessible`: after render filtering hides panel chunks, `/v2/chunks/{chunk_id}/image` and chunk chat for the hidden chunk should still behave consistently with the “DB 무변경” claim.
