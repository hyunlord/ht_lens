## 1. Over-engineering

- `POST /documents/{id}/summarize`, `src/ht_lens/api/static/js/components/document_card.js`, and the “재요약” button are scope creep. `ROADMAP.md` Phase 6d asks for automatic summary generation, not manual summary lifecycle management. This also misses the actual DoD surface: “문서 첫 페이지에 thread로 자동 attach (또는 별도 영역)”.

- The plan spends UI budget on index-card summary preview while leaving `src/ht_lens/api/static/js/viewer.js` untouched. A summary on `index.html` is not “first page thread” and is not obviously the “별도 영역” the roadmap describes. That is the wrong place to add complexity.

- “10 screenshots + Playwright scenario (가능한 만큼)” should be deferred. `ROADMAP.md` Phase 6e explicitly carries Playwright automation as debt, and `WORKFLOW.md` requires concrete evidence, not “가능한 만큼”. Pulling this into 6d inflates verification without improving the upload pipeline itself.

- `src/ht_lens/jobs/background.py::BackgroundTaskPool` is a new abstraction for exactly one background workflow. Until there is more than upload processing, a small task registry inside `src/ht_lens/api/app.py::_lifespan` is simpler and easier to audit.

## 2. Hidden assumptions

- The plan treats `process_upload_job()` as async-friendly, but `src/ht_lens/extract/pipeline.py::extract_pdf` is synchronous PyMuPDF/Pillow work. If you call it inside an `asyncio.Task` without `to_thread`, the event loop blocks and `/jobs` polling can freeze during the longest phase.

- The plan says `documents.filename` preserves the user filename, but `extract_pdf()` writes `DocMeta.filename = pdf_path.name`. Since the upload is stored as `data/uploads/{sha256}.pdf`, `src/ht_lens/ingest/pipeline.py::ingest_extract_dir` will ingest the hash name unless you add an explicit override path. That override is not designed here.

- Session boundaries are not specified. `ingest_extract_dir()` rolls back its caller session on failure, while `translate_document()` commits per block. If job progress updates share the same `AsyncSession`, progress rows can be rolled back or interleaved in surprising ways.

- The DoD mapping assumes “5~10페이지 실측 + extrapolation” proves the roadmap’s “200 페이지 PDF 처리 1~2시간”. That is not evidence. Phase 2b already documents shared-LLM latency variability, so linear extrapolation is a weak assumption, not a validation plan.

## 3. Edge cases

- Concurrent same-file uploads are still broken as written. The migration sketch for `0003_jobs_and_summary.py` adds no unique index on `documents.src_pdf_sha256`, and `POST /uploads` does a racy read-before-write dedup query. Two clients can both miss and create duplicate jobs/documents.

- `Path(tmp_path).rename(final)` assumes temp storage and `data/uploads/` are on the same filesystem. If `_stream_to_tmp()` uses the system temp dir, cross-device rename raises `EXDEV` after the entire file has already uploaded.

- Scanned/image-only PDFs or docs with only failed translations will hit `summarize_document()`’s empty-body path. The plan names `SummarizeEmptyError` but never defines the HTTP/API contract for auto-summary or `POST /documents/{id}/summarize` in that case.

- Restart recovery is underspecified. `_lifespan` marks active jobs `failed`, but the plan does not say what happens to partially created `documents/pages/blocks/translations`, orphan extract dirs, or re-upload of the same SHA after a mid-pipeline crash.

## 4. Alternative approaches

- Reuse the existing `threads`/`messages` model instead of adding `documents.summary` now. Auto-create a summary thread on the first text block of page 1 using the existing viewer surfaces in `src/ht_lens/api/routers/threads.py`. That matches the roadmap DoD more directly.

- If `documents.summary` stays, defer manual re-summary to Phase 6e. Phase 6d only needs automatic summary generation plus display. Dropping `POST /documents/{id}/summarize` and the index-card retry UI would materially reduce API, frontend, and test surface.

- The real architectural fix is not a custom pool; it is offloading blocking work. Wrap `extract_pdf` and file hashing with `asyncio.to_thread()` or `anyio.to_thread.run_sync()`, then keep a minimal task set on `app.state`. That solves the event-loop risk with less machinery.

## 5. Missing tests

- `tests/integration/test_api_uploads.py::test_upload_same_sha_race_returns_single_job_or_existing_doc` should exist. The plan’s dedup guarantee is worthless without a concurrent upload test.

- `tests/integration/test_jobs_pipeline.py::test_process_upload_job_preserves_original_filename_in_document` should exist. Current `extract_pdf()` derives `doc_meta.json` from the stored path name, which conflicts with the intended UX.

- `tests/integration/test_jobs_pipeline.py::test_process_upload_job_does_not_block_jobs_polling_during_extract` should exist. Monkeypatch `extract_pdf` to sleep and assert `GET /jobs` still responds while the job is active.

- `tests/integration/test_api_summarize.py::test_summarize_image_only_document_returns_clear_error` and `test_upload_pipeline_skips_auto_summary_when_no_translated_text` should exist. The proposed tests cover mock/404/empty body, not the empty-source conditions this phase will actually create.

- `tests/integration/test_api_startup.py::test_startup_marks_active_jobs_failed_without_leaving_orphan_partial_document_state` should exist. Restart recovery is part of the plan in `src/ht_lens/api/app.py::_lifespan`; it needs a regression test, not a comment.
