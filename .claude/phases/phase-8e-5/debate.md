## 1. Over-engineering

- The plan is trying to solve three different problems in one phase: degraded image replacement, caption mapping diagnosis, and render-time caption correction. Phase 8e ROADMAP DoD only requires 7 docs migrated, readable in reflow, and rollback; Phase 8e-5 should not grow into a general MinerU caption-repair subsystem.

- The proposed Stage A “전 docs caption 정합성 스캔” is too broad for a confirmed ch54 defect. A full heuristic scanner for “Figure N.M” order, bbox adjacency, and pattern classification should be deferred unless it directly changes the fix. For this phase, an explicit audit report plus a known correction set is enough.

- Adding `black_bg_fraction()` and `is_degraded_diagram()` as general detection logic in `src/ht_lens/api/routers/reflow.py` is misplaced. The router currently serves API responses (`get_reflow`, `chunk_image`, `page_image`) and should not absorb image-quality classification. Put one-off backfill/audit logic under `scripts/` or a small service module.

- The “육안 샘플 게이트” inside a backfill CLI is incompatible with the non-interactive `codex exec` / Claude Code workflow in `WORKFLOW.md`. If human confirmation is required, the plan needs a manifest-first workflow, not a CLI that may pause or depend on manual review during Stage 4.

- Render-time `(doc, chunk)→caption` correction inside `get_reflow()` creates a hidden data patch in the API layer. That duplicates the Phase 8e-4 render-only philosophy but goes further: it mutates semantic content, not just hides duplicate rendering. Use an explicit manifest or a data backfill, not hard-coded API conditionals.

## 2. Hidden assumptions

- The plan assumes all future `Chunk.bbox_json` values are MinerU 1000×1000 normalized coordinates because doc1/doc5 matched and doc3 looked “타당”. `Chunk.bbox_json` in `src/ht_lens/db/models.py` explicitly says raw MinerU coordinates are kept verbatim; the contract does not guarantee normalization.

- It assumes cached page renders under `data/extracts_v2/<doc>/pages/page_NNNN.png` have the same orientation, crop box, and page index semantics as MinerU `page_idx`. `page_image()` and `render_doc_pages()` in `src/ht_lens/api/routers/reflow.py` do not account for PDF crop boxes, rotation, or MinerU page numbering drift.

- It assumes `images_fixed/<basename>` is unique per document. MinerU image basenames can collide across pages or re-extractions, and `chunk_image()` currently trusts the absolute `Chunk.img_path`; deriving an override by basename can serve the wrong replacement if two chunks share a filename.

- It assumes fixed images can be selected only by file existence. That means a stale `images_fixed/<basename>` from a previous run silently overrides current DB content after re-ingest, with no source hash, chunk id, bbox, or page validation.

- It assumes chunk ids like ch1/ch84/ch85/ch54 are stable. They are DB surrogate ids from `chunks.id`; any reingest, overwrite, or document ordering change can invalidate the hard-coded mapping.

- The scope says “전 docs” but Stage 0 and tests repeatedly say docs 1-5, while ROADMAP Phase 8e is 7 docs. If docs 6-7 are absent from this phase, the plan should state why; otherwise the claimed “정상 158 무회귀” is not the full Phase 8e surface.

## 3. Edge cases

- Inverted or degenerate bbox values (`x1 <= x0`, `y1 <= y0`) are not explicitly handled in `page_crop_box`; “범위 이탈” is not enough. A zero-width crop with padding could produce a plausible but wrong fixed image.

- Slightly out-of-range normalized bboxes such as `[-1, 10, 1001, 500]` may be valid MinerU noise. The plan says skip on negative or `>1000+ε`, but does not define ε or whether clamping is allowed before padding.

- Rotated PDF pages will crop the wrong region. The repo already has `tests/integration/test_rotated_page.py`, and `render_doc_pages()` uses PyMuPDF rendering; the plan needs to address how MinerU bbox coordinates map when the source page has `/Rotate`.

- The black-background detector will miss degraded diagrams that are white-background vector fragments, and it can falsely catch legitimate black-background charts, screenshots, or microscopy images. The Stage 0 dark-photo sample is not enough coverage for academic PDFs.

- Caption parsing by `"Figure N.M"` fails on `(a) Figure 28.20`, multi-line captions, “Fig.” abbreviations, tables/charts, captions below versus above, and captions that include multiple figure references in one sentence.

- Current Phase 8e-4 dedup drops captionless nested images in `get_reflow()`. If caption correction moves a caption from ch54 to ch53, it may change which image is considered captioned and alter `_drop_captionless_images_contained_by_captioned()` behavior on page 4.

- `chunk_image()` currently returns media type from the served path suffix. If an override is generated as PNG while the original basename is `.jpg`, either the plan must preserve extension/content consistency or test the media-type behavior.

## 4. Alternative approaches

- Prefer an explicit `image_overrides.json` / `caption_overrides.json` manifest under `data/extracts_v2/<doc>/` keyed by stable evidence (`doc_id`, `page_idx`, original `img_path` basename, bbox hash), then have `chunk_image()` and `get_reflow()` consult it. This keeps one-off corrections auditable and avoids hard-coded API rules.

- For image repair, use PyMuPDF clipping directly from the source PDF (`page.get_pixmap(clip=fitz.Rect(...))`) after converting normalized bbox to page coordinates. Cropping cached page PNGs compounds render-cache DPI, padding, and stale-cache assumptions; direct clip rendering can be deterministic and higher quality.

- For this phase, an allowlist backfill is safer than a detector: repair exactly the three confirmed degraded chunks and verify no others change. General detection can be a later audit tool once docs 6-7 and more dark-image negatives are available.

- If caption mapping is a MinerU content-list pairing defect, the durable fix belongs near `src/ht_lens/ingest_mineru/content_list.py` or a reingest-side correction manifest, not in `src/ht_lens/api/routers/reflow.py`.

## 5. Missing tests

- Add `test_page_crop_box_rejects_inverted_and_degenerate_bbox` for `[10,10,5,20]`, `[10,10,10,20]`, and `[10,10,20,10]`.

- Add `test_page_crop_box_rotation_not_silently_applied` or an equivalent rotated-page integration test using the existing rotated-page fixture pattern.

- Add `test_chunk_image_fixed_override_scoped_to_same_doc` to prove `images_fixed/<basename>` from another document cannot override a chunk.

- Add `test_chunk_image_fixed_override_rejects_traversal_and_non_image_suffix` because `_validate_v2_image()` currently protects DB paths, but the override path construction will be new.

- Add `test_fixed_image_stale_override_requires_matching_original` so a leftover fixed file does not override after `Chunk.img_path` changes.

- Add `test_caption_correction_runs_before_or_after_dedup_intentionally` for doc1 page4-style chunks ch53/ch54/ch55, proving the correction does not accidentally drop or duplicate images.

- Add `test_caption_scan_handles_subfigure_prefix_and_fig_abbreviation` covering `(b) Figure 28.20` and `Fig. 28.19`.

- Add `test_backfill_dry_run_does_not_write_images_fixed` and `test_backfill_apply_writes_only_detected_or_allowlisted_chunks`; the plan’s human gate is not enough evidence.

- Add a live/regression check for docs 6-7 or explicitly name `test_phase_8e5_scope_excludes_docs_6_7_with_reason`; the current “docs 1-5” evidence does not satisfy the 7-doc Phase 8e surface.
