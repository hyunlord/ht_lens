## 1. Over-engineering

- `.claude/phases/phase-1/plan.md` adds too much architecture for the Phase 1 DoD. `extract/_fitz.py` with `FitzDoc = NewType("FitzDoc", object)`, manual `open_pdf`/`close`, and a “type ignore only here” rule is heavier than needed for a first extractor. A small context-managed adapter around PyMuPDF would satisfy mypy strict without designing a long-term abstraction before seeing actual extraction pain.

- `doc_meta.json` with `sha256`, `extracted_at`, `extractor_version`, document language aggregation, and `save_images` is outside the ROADMAP Phase 1 deliverable, which only requires page PNG plus block JSON. `save_images` in particular should be deferred; Phase 4 can use the page PNG, and Phase 1 says image blocks only need bbox.

- The `reading_order.py` plan tries to solve 1-3 column detection with custom agglomerative clustering immediately. ROADMAP flags reading order as a risk with “80% 잡고 진행,” not as a mandate to implement a bespoke layout engine. Start with PyMuPDF ordering plus narrow corrections; custom column detection should be justified by fixture failures.

- `models.py` as Pydantic schema for local JSON is premature. FastAPI/Pydantic matters in Phase 3; Phase 1 can use dataclasses/TypedDict plus explicit JSON serialization. Pydantic adds validation surface without improving the roadmap DoD.

## 2. Hidden assumptions

- The block grouping plan says “line-by-line,” but the proposed `RawBlock` only exposes `spans: tuple[RawSpan, ...]`; it does not expose PyMuPDF line objects, line bbox, line direction, or span order within lines. If `_fitz.py` flattens spans, `extract/blocks.py` cannot reliably compute y-gap between lines.

- The plan does not define coordinate units. PyMuPDF text bbox values are page-space points, while `render_page_png` emits 200dpi pixels. If `pages/page_NNNN.json` stores point bboxes without page dimensions and scale metadata, Phase 4 overlays will be wrong or require undocumented conversion.

- `langdetect` is assumed to be sufficient for `en|ko|mixed|unknown`, but mixed Korean/English detection is not equivalent to language classification. A mostly Korean technical PDF with English identifiers may be labeled inconsistently page-by-page, making the “30% mixed” rule brittle.

- The plan assumes `fitz.FileDataError`, `doc.needs_pass`, and `page.get_pixmap(dpi=dpi)` behavior are stable across the installed PyMuPDF version. That should be verified before encoding exit-code contracts in `cli.py`.

- The test plan assumes the three fixture PDFs in `tests/fixtures/` are representative. ROADMAP specifically names captions/footnotes, Korean font recognition, and multi-column order as risks; three samples are not enough unless their properties are documented in `tests/fixtures/README.md`.

## 3. Edge cases

- Rotated pages, non-default CropBox/MediaBox, and landscape pages can desynchronize rendered PNG dimensions from extracted bboxes. The plan has no rotation normalization rule in `render_page_png` or `pipeline.extract_pdf`.

- Multi-column clustering by x0 will misclassify indented bullets, block quotes, sidebars, marginal notes, and table cells as separate columns. The `bbox width > 0.7 * page_width` header exception does not handle footers, page numbers, section titles inside a column, or wide captions.

- Scanned/image-only PDFs are declared unsupported, but the integration test still asserts every page has at least one block except one mixed cover-page special case. Any image-only page in `sample_en.pdf` or `sample_ko.pdf` would fail despite being a valid unsupported-but-processed state.

- CJK-specific extraction issues are under-specified: missing ToUnicode maps, decomposed Hangul, vertical text, ruby annotations, and mixed full-width/half-width punctuation can all produce broken text or bbox fragmentation.

- Partial output failure is not handled. `extract_pdf` writes page PNG/JSON incrementally, but the plan does not define whether a failed run leaves a resumable directory, deletes partial files, or blocks rerun because `--overwrite` defaults to false.

## 4. Alternative approaches

- Use PyMuPDF’s structured extraction more directly first: `page.get_text("dict", sort=True)` or `page.get_text("rawdict")` preserves blocks, lines, spans, and directions. That is a better Phase 1 baseline than flattening into custom `RawSpan` and reconstructing paragraphs from y-gaps.

- Store explicit page metadata per JSON: page width/height in points, rendered PNG width/height in pixels, dpi, and rotation. This is a small architectural choice that directly protects Phase 4 overlay work better than `doc_meta.json` language aggregation.

- Replace custom column clustering with semantic assertions against fixture PDFs first. If PyMuPDF `sort=True` fails on `sample_mixed.pdf`, then add a targeted correction for that failure. This keeps ROADMAP’s “80%” target grounded in observed evidence.

- If table/layout fidelity becomes a real Phase 6 requirement, evaluate `pdfplumber` or `layoutparser` later with explicit dependency approval. They are not appropriate Phase 1 dependencies under the ROADMAP dependency limit.

## 5. Missing tests

- Add `test_fixture_pdfs_exist_and_are_nonempty` so `tests/conftest.py` skip behavior cannot let Phase 1 pass without real PDFs.

- Add `test_page_json_records_coordinate_space_and_render_scale` to lock the bbox unit contract before Phase 4 depends on overlays.

- Add `test_rotated_page_bbox_matches_rendered_png_dimensions` using a synthetic rotated PDF.

- Add `test_reading_order_indented_bullets_do_not_create_columns`; the x0 clustering heuristic is likely to fail here.

- Add `test_reading_order_spanning_header_then_two_columns` for the explicit rule in `extract/reading_order.py`.

- Add `test_scanned_page_writes_empty_blocks_json` to confirm unsupported OCR still produces valid page PNG and JSON.

- Add `test_cli_rejects_existing_non_empty_out_dir_without_overwrite` and `test_cli_overwrite_replaces_previous_output`.

- Add `test_encrypted_pdf_exit_code_2` and `test_corrupted_pdf_exit_code_3` for the promised CLI error contract.

- Add `test_pipeline_closes_document_on_page_failure`; the manual `open_pdf`/`close` design makes resource cleanup easy to miss.

- Add a human-review artifact for the DoD item “block JSON이 사람이 봐도 합리적”; block count plus first 50 chars in `verify.md` is not enough evidence.