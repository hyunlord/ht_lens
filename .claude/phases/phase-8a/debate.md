## 1. Over-engineering

The plan creates `ChunkTranslation` and `ChunkEmbedding` schemas in `.claude/phases/phase-8a/plan.md:43-46`, but ROADMAP Phase 8a only requires MinerU extraction, chunk ingest, figure paths, and 1.x DB preservation. Translation and embeddings are explicitly Phase 8b in `ROADMAP.md`; adding those tables now expands the migration blast radius without proving the Phase 8a ingest path.

The same-DB additive migration decision in `.claude/phases/phase-8a/plan.md:67-70` over-corrects for implementation simplicity while contradicting the Phase 8 master plan’s “병행 DB + clean 재추출” direction. For Phase 8a, a separate `ht_lens_v2.db` would better isolate experimental MinerU schema from production 1.x data and make “1.x DB 무손상” trivial.

`src/ht_lens/cli.py` changes for both `extract-mineru` and `ingest-mineru` are reasonable, but the `extract-mineru` wrapper defaulting to `~/mineru_test/venv/bin/mineru` in `.claude/phases/phase-8a/plan.md:24` bakes a sandbox path into product CLI behavior. Phase 8a can accept an explicit binary path/env and fail clearly; standard install discovery should be deferred.

## 2. Hidden assumptions

The plan assumes `Page` can be reused while creating only “page_idx 메타” (`.claude/phases/phase-8a/plan.md:65`). That is false against the current model: `Page.width`, `height`, `bg_image_path`, `pixel_width`, and `pixel_height` are non-null in `src/ht_lens/db/models.py:49-56` and migration `0001_initial_schema.py:41-48`. The plan must either populate real values in 8a or not create `pages` rows.

It assumes MinerU’s output layout is always `<out>/<stem>/auto/<stem>_content_list.json` plus `images/` (`.claude/phases/phase-8a/plan.md:25`). If MinerU changes naming, sanitizes stems, or emits nested image paths, `MineruResult` discovery breaks. The runner needs path discovery tests against actual fixture structure, not just hard-coded construction.

It assumes body headings are exactly `type=text` with `text_level` set (`.claude/phases/phase-8a/plan.md:55-56`). The master plan describes MinerU types as `text / header / equation / image / table`; if MinerU emits `header` directly, the planned mapping drops or misclassifies headings.

It assumes fixed production row counts for “1.x 무손상” (`blocks=49850`, `translations=44607`, `block_embeddings=17257`) in `.claude/phases/phase-8a/plan.md:124`. That makes verification environment-dependent. The test should snapshot pre/post counts from the target DB, not assert global magic numbers.

## 3. Edge cases

Malformed or partial `content_list.json` is under-specified. Missing `bbox`, `page_idx`, `text`, `text_level`, `img_path`, or caption fields should have explicit behavior: reject the document, skip the item, or preserve a degraded chunk. “키 부재 graceful” in `.claude/phases/phase-8a/plan.md:127` is too vague for ingest correctness.

Figure handling will break on multiple captions, missing images, duplicated image basenames, chart/table images, and captions stored separately from the image item. The plan only preserves `image_caption[0]` and `chart_caption[0]` (`.claude/phases/phase-8a/plan.md:58-59`), which loses data and can mis-anchor captions in academic PDFs.

Filtering `page_number / header / footer / page_footnote` (`.claude/phases/phase-8a/plan.md:61`) assumes MinerU labels chrome perfectly. Academic papers often encode running headers, footnotes, copyright notices, author affiliations, and equation notes as ordinary text. Blind filtering and blind retention are both risky; the parser needs fixture cases for mislabelled chrome.

The plan defers coordinate-system validation to Phase 8c (`.claude/phases/phase-8a/plan.md:17,128`), but Phase 8a DoD says chunks preserve `bbox/page/type/latex/caption`. Rotated pages, crop boxes, multi-column order, negative bbox values, polygons instead of boxes, and scanned/OCR pages can make “preserved” meaningless unless raw coordinate provenance is stored.

Subprocess failure modes are missing: timeout, nonzero exit, stderr-only warnings, partial output, corrupted PDFs, encrypted PDFs, and user cancellation. `extract-mineru` must not leave output that `ingest-mineru` later treats as complete.

## 4. Alternative approaches

Use a separate v2 SQLite database for Phase 8a, as the master plan recommends, and migrate to a unified DB only after 8c/8d proves the reflow path. This better satisfies ROADMAP’s rollback intent and avoids changing `documents` in the production DB just to test MinerU ingest.

Limit 8a schema to `chunks` plus minimal document metadata. Defer `chunk_translations` and `chunk_embeddings` until Phase 8b, where cache keys, status semantics, vector source text, and caption translation behavior can be designed against actual translation code.

If `Page` reuse is required, render page images in Phase 8a with PyMuPDF or extract dimensions from `origin.pdf` immediately, so non-null `pages` invariants remain true. Otherwise, make `chunks.doc_id + page_idx` independent of `pages` until 8c.

Use a typed parser boundary, preferably Pydantic models or dataclasses in `src/ht_lens/ingest_mineru/content_list.py`, to normalize MinerU variants before DB insert. Direct dict parsing will spread schema-version assumptions across pipeline code.

## 5. Missing tests

Add `test_mineru_ingest_does_not_create_invalid_page_rows`: ingest a fixture and assert every created `Page` row satisfies current non-null model columns, or assert no `Page` rows are created by design.

Add `test_content_list_parser_preserves_unknown_types_as_error_or_raw`: feed an item with an unrecognized MinerU type and verify the chosen behavior is explicit, not silent data loss.

Add `test_content_list_parser_handles_missing_bbox_and_caption_fields`: cover missing `bbox`, empty caption list, absent `image_caption`, and `None` text without crashing or inserting misleading chunks.

Add `test_mineru_runner_discovers_actual_output_paths`: create a fake MinerU output tree with sanitized stem/nested images and verify `MineruResult.content_list_path` and `images_dir` are discovered, not guessed.

Add `test_ingest_mineru_rolls_back_on_missing_image_file`: if a chunk references an image that cannot be copied, the DB should not commit a half-ingested document.

Add `test_migration_0005_only_adds_allowed_objects`: inspect Alembic operations or compare schema pre/post and fail on any changes beyond new v2 tables plus the explicitly approved `documents` columns.
