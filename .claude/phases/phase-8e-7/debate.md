## 1. Over-engineering

The optional `split-pdf` CLI in `.claude/phases/phase-8e-7/plan.md` is too much for this phase. The actual blocker is ingesting already-produced split MinerU outputs; splitting `book2.pdf` can remain an ops script until repeated use is proven. ROADMAP Phase 8e DoD is “7 docs 2.0 DB 완료 / reflow viewer에서 전체 읽기 / 1.x 롤백 가능,” not a general PDF-splitting product surface.

Adding both `src/ht_lens/ingest_mineru/merge.py` and a new `ingest_mineru_multi(...)` pipeline risks duplicating `ingest_mineru_output()` behavior from `src/ht_lens/ingest_mineru/pipeline.py`. Existing ingest already handles schema head checks, filename collision scoped to `Document.extractor == "mineru"`, overwrite, image cleanup, and rollback. A parallel path must replicate all of that exactly or it will create a subtle 8a regression.

The “same basename means same sha256 content” image policy is more complex than the phase needs and is not true for current fixtures (`tests/fixtures/mineru/content_list_sample.json` uses names like `fig1.jpg`). Namespacing images by part index would be simpler and safer than relying on MinerU basename semantics.

## 2. Hidden assumptions

The plan assumes every split output has a discoverable `*_origin.pdf` and that this is the correct source for future repair tooling. But `repair-images` and `detect-repairs` in `src/ht_lens/cli.py` infer the source PDF from `Document.markdown_path` by globbing `*_origin.pdf` in the same directory. A merged document cannot safely point `markdown_path` at part 1’s markdown, because page 900 repairs would use the wrong origin PDF.

It assumes part order is the CLI argument order and that users will never pass part2 before part1. `merge_parsed_parts(parts: list[(ParsedChunk목록, page_count)])` needs an explicit ordering contract or validation against part metadata; otherwise page offsets can be internally monotonic but mapped to the wrong original pages.

It assumes split PDFs preserve all original page attributes relevant to `bbox_json` and compare-mode sync. PyMuPDF `select()` may preserve page count, but the plan does not state whether rotations, crop boxes, media boxes, and page labels are preserved or irrelevant. ROADMAP explicitly lists side-by-side bbox sync as dependent on MinerU page/bbox correctness.

It assumes `content_list` page ranges are dense and start at zero per split. That is true only if extraction runs on physical split PDFs. If someone later uses MinerU `-s/-e`, the same CLI could produce double-offset pages unless the page-base is validated.

## 3. Edge cases

A part with only blank/chrome pages can legitimately have `page_count > 0` and zero parsed chunks. Current `ingest_mineru_output()` rejects zero chunks with `IngestError("content_list.json yielded zero chunks...")`. Multi-part merge must allow an empty middle or trailing part for offset math while still rejecting an all-empty merged document.

Duplicate image basenames with different bytes will be silently dangerous if the implementation reuses `_copy_image()` from `src/ht_lens/ingest_mineru/pipeline.py`; that function copies to `dest_dir / basename` and overwrites without content comparison. The plan says “same basename = same content,” but the code does not enforce it.

Malformed or non-monotonic `page_idx` inside a part is not covered. `parse_content_list()` in `src/ht_lens/ingest_mineru/content_list.py` only requires integer `page_idx`; it does not assert bounds against `origin.pdf.page_count` or monotonicity. A content item on page 685 of a 685-page split should be rejected before offsetting.

Overwrite behavior is under-specified. Existing MinerU ingest replaces only `Document.filename == filename AND extractor == "mineru"` and leaves 1.x rows untouched. The multi ingest path must preserve that exact contract, including cascade removal of old chunks/translations/embeddings and managed image cleanup.

## 4. Alternative approaches

A simpler approach is to merge raw MinerU JSON into one temporary `content_list.json`: offset each raw item’s `page_idx`, concatenate raw lists, assemble/copy images into a temporary `images/` directory, then call existing `ingest_mineru_output()`. This reuses the battle-tested schema, overwrite, rollback, and 1.x coexistence logic in `src/ht_lens/ingest_mineru/pipeline.py`.

Another option is exposing MinerU `-s/-e` in `extract-mineru` with explicit output metadata for original page offset, then teaching ingest to accept `--page-offset`. That avoids physically splitting PDFs and preserves one original source PDF path for repair tooling, but it departs from the Planner’s “verified path” decision.

If a dedicated multi CLI remains, prefer part image namespacing (`part001/<basename>` or `part001__basename`) over basename collision inference. It is more robust and avoids depending on undocumented MinerU filename hashing.

## 5. Missing tests

Add `test_multi_ingest_preserves_full_origin_pdf_for_repair_tools`: after multi ingest, `Document.markdown_path` or equivalent provenance must not cause `repair-images` / `detect-repairs` to use part1 origin for page-offset chunks.

Add `test_merge_rejects_part_page_idx_out_of_bounds`: given `page_count=3` and a parsed chunk with `page_idx=3`, merge must fail before writing DB rows.

Add `test_multi_ingest_allows_empty_part_but_rejects_all_empty`: offset math must handle a blank split part with no chunks, while an all-chrome multi ingest still fails.

Add `test_multi_ingest_duplicate_basename_different_bytes_fails_or_namespaces`: prove two `fig1.jpg` files from different parts cannot silently overwrite each other.

Add `test_multi_ingest_overwrite_replaces_only_mineru_doc_and_removes_old_assets`: mirror `tests/integration/test_mineru_ingest.py::test_same_filename_1x_and_mineru_coexist` for the new multi path, including old managed image directory cleanup.
