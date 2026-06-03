## 1. Over-engineering

The plan expands Phase 8e beyond the ROADMAP DoD, which only requires “7 docs 2.0 DB 완료 / reflow viewer에서 전체 읽기 / 1.x 롤백 가능” in `ROADMAP.md`. Adding `overrides.candidates.json`, `repair-images --review`, caption proposal logic, and optional ingest hooks is a new repair workflow, not just migration support.

Caption “탐지+제안” in `.claude/phases/phase-8e-6/plan.md` is too much for this phase. The existing `repair_seeds/doc1.json` and `repair_seeds/doc5.json` path already handles human-reviewed caption correction. For F2, automate only degraded-image candidate discovery and keep caption repair as seed validation until book2 proves the pattern at scale.

The plan leaves `ingest_mineru_output()` integration undecided while making it part of Scope. That ambiguity is dangerous: touching `src/ht_lens/ingest_mineru/pipeline.py` risks violating its current atomic contract, while a separate `ht-lens detect-repairs` command would satisfy the need without contaminating ingest.

`overrides.candidates.json` duplicates the durable source-of-truth model already established by `tests/unit/test_repair_seeds.py`: committed `repair_seeds/*.json` are the reviewed inputs; live `overrides.json` is generated. A pending manifest introduces another state to validate, clean up, and keep stale-safe.

## 2. Hidden assumptions

The C′ coordinate decision assumes `Document.markdown_path` reliably points beside exactly one `*_origin.pdf`. `src/ht_lens/cli.py` only discovers markdown by a loose `*.md` glob when ingesting a content_list file; if `markdown_path` is `None`, wrong, or from a copied output dir, default repair discovery fails.

The plan assumes all relevant MinerU bboxes are 1000-normalized. `src/ht_lens/ingest_mineru/content_list.py` preserves malformed bbox as `"[]"`, and `clip_render_figure()` silently skips invalid/rotated pages. The DoD “자동 페이지-클립” is weaker than stated unless missing/invalid bbox counts are explicitly reported and fail the gate.

The black-background threshold `>0.6` is treated as stable from a 5-doc sample. Book2 may contain legitimate dark diagrams, screenshots, microscopy, heatmaps, or inverted-color plots. “후보 only” prevents serving damage, but it does not prevent review overload, which is the whole reason this phase exists.

Caption detection assumes the defect appears as same-page sibling images with empty captions plus a merged caption containing `(a)/(b)`. MinerU may emit captions as text chunks, chart captions, table captions, OCR text, “Figure 1(a)”, uppercase labels, Unicode full-width parentheses, or Korean/English mixed labels. The plan does not state the supported grammar.

## 3. Edge cases

Same basename collision on the same page is still exposed. `run_image_backfill()` currently writes `p{page_idx}_{stem}.png`; two chunks on page 0 with basename `image.jpg` overwrite each other. Phase 8e-6’s candidate/preview generation must not inherit this bug for `overrides.candidates.json`.

Rotated pages are explicitly skipped by `clip_render_figure()`. The plan mentions rotation skip but still maps DoD to “자동 페이지-클립”; a rotated page with a degraded figure becomes a silent non-repair unless the candidate manifest records `skip_reason` and the CLI exits non-zero or warns loudly.

Nested multi-panel extraction interacts with `src/ht_lens/api/routers/reflow.py` `_drop_captionless_images_contained_by_captioned()`. If caption override makes a previously captionless standalone image captioned, dedup behavior changes; if a candidate is generated for a nested panel that serving will drop, the review queue contains irrelevant work.

Caption label parsing will break on `(a) ...; (b) ...` inside prose, ranges like `(a)-(c)`, sublabels `(i)/(ii)`, labels embedded after “Figure 28.20”, or captions where `(a)` describes a panel not ordered top-to-bottom. The plan says “spatial 순서 추정” but does not define failure behavior.

Candidate files can go stale after `ingest-mineru --overwrite` changes `doc_id`, `img_path`, or bbox. The existing override matcher is stale-safe at serve time; the new pending manifest also needs stale detection before promotion, or `repair-images --review` can approve dead candidates.

## 4. Alternative approaches

Use a separate audit command only: `ht-lens detect-repairs --doc-id --pdf optional` emits a machine-generated report and a draft `repair_seeds/<doc>.json`, then existing `repair-images --seed --apply` remains the only writer of `overrides.json`. This preserves the current seed-as-source-of-truth contract and avoids a second manifest lifecycle.

For caption defects, prefer a deterministic report over proposal assignment: list same-page image chunks, bbox thumbnails, current captions, and suspected merged-caption text. Let the human edit `repair_seeds/*.json`. That is less automatic, but it avoids encoding a brittle spatial assignment heuristic in `src/ht_lens/image_repair.py`.

For origin PDF discovery, add an explicit `--pdf` requirement to `detect-repairs` for now, with markdown-path autodiscovery as a convenience only. This is better than relying on `Document.markdown_path` quality from Phase 8a ingestion paths.

If C′ proves fragile on book2, migration 0008 is still not the only fallback. A lighter option is storing `origin_pdf_path` or `source_pdf_sha256` in a repair seed/report, not adding page-size columns to the main schema.

## 5. Missing tests

Add `test_detect_repairs_cli_missing_origin_pdf_exits_2`: a MinerU doc with `markdown_path=None` or no `*_origin.pdf` must fail loudly, not emit an empty candidate report.

Add `test_candidate_manifest_not_served_by_reflow_or_chunk_image`: writing `overrides.candidates.json` under `HT_LENS_EXTRACTS_V2_DIR/<doc_id>` must not affect `/v2/documents/{doc_id}/reflow` or `/v2/chunks/{chunk_id}/image`.

Add `test_review_rejects_stale_candidate_after_reingest`: create a candidate, change the chunk bbox or basename, then attempt promotion; it must refuse the candidate instead of writing a matching-looking `overrides.json`.

Add `test_detect_caption_mispair_text_caption_chunk_not_image_caption`: same-page caption text emitted as a `text` chunk should either be detected intentionally or documented as unsupported with zero candidates.

Add `test_detect_caption_mispair_no_false_positive_parenthetical_prose`: a normal caption containing `(a)` and `(b)` as prose, not panel labels, must not produce a caption repair candidate.

Add `test_candidate_preview_same_basename_same_page_no_collision`: two image chunks on one page with the same basename must generate distinct preview/fixed filenames.

Add `test_detect_repairs_reports_rotated_page_skip_reason`: degraded image on a rotated PDF page should produce a candidate with explicit skip reason, not a silent missing preview.
