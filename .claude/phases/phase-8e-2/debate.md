## 1. Over-engineering

The plan adds “cross-doc RAG live 활성화” to 8e-2 even though `ROADMAP.md` Phase 8e DoD only says “7 docs 2.0 DB 완료”, “reflow viewer에서 전체 읽기”, and “1.x 롤백 가능”. Real cross-doc behavior should stay in 8e-3 verification or 8d territory; 8e-2 should prove the migrated data is complete and queryable, not expand acceptance criteria.

Running `translate-chunks --short-only` on every migrated document is also a quality-repair pass, not core migration. Since `src/ht_lens/translate/short_retranslate.py` is already an 8d-2c feature, 8e-2 should first establish baseline full translation counts and failed rows. Apply short-only only to documents where verification shows short-fragment quality defects.

The “Aggarwal(518p, 백그라운드)” target makes this phase too broad for a “smallest-first” batch. A large textbook PDF should have a clear go/no-go checkpoint after the three small papers; otherwise one long CPU extraction can dominate the phase and obscure whether the migration workflow itself is sound.

## 2. Hidden assumptions

The plan assumes “book2 = ch28(doc7, 이미 적재)” counts toward Phase 8e’s “7 docs 2.0 DB 완료”. That is not stated in `ROADMAP.md`; the roadmap says 7 docs migration, while this plan yields 5 migrated entries and defers full book2 plus skips `phase6d_demo×2`. If that reinterpretation is intentional, `ROADMAP.md` DoD is stale and should be explicitly challenged.

It assumes source identity is recoverable, but `src/ht_lens/ingest_mineru/pipeline.py::ingest_mineru_output` creates `Document` without setting `src_pdf_sha256`. Collision handling is by `Document.filename` plus `extractor`, so two different PDFs with the same display filename are ambiguous, and the verify plan cannot prove the intended source was migrated.

It assumes `extract-mineru` can run long PDFs “시간 단위”. `src/ht_lens/extract_mineru/runner.py::run_mineru` defaults to `_DEFAULT_TIMEOUT_S = 3600`, and `src/ht_lens/cli.py::extract_mineru_command` exposes no `--timeout`. A 518-page CPU extraction can fail by design unless the plan includes a timeout change or a split strategy.

It assumes `tr 카운트=chunks` is the right completeness metric. `src/ht_lens/api/routers/reflow.py::get_reflow` only surfaces translations with `status == "translated"`, so a row count can pass while failed rows render untranslated or blank.

## 3. Edge cases

Reruns are under-specified. `ingest-mineru` rejects duplicate MinerU filenames unless `--overwrite` is used, but the plan does not say whether failed partial runs are resumed, overwritten, or abandoned. This matters for doc IDs used by `translate-chunks --doc-id N` and `embed-chunks --doc-id N`.

Large output directories can contain multiple `*_content_list.json` files; `src/ht_lens/extract_mineru/runner.py::_discover_outputs` sorts matches and uses the first. Reusing an output directory across retries or documents can silently ingest the wrong content list.

The plan does not cover scanned pages, encrypted PDFs, rotated pages, or PDFs whose MinerU output is mostly image chunks. “chunks>0” is too weak for the ROADMAP goal of readable academic translation; a scanned chapter can pass that while yielding almost no translated text.

`--lang` is left at the default `"en"` in `extract_mineru_command`, but the project vision explicitly includes Korean/English PDFs and the batch includes `sample_mixed`. Mixed CJK+Latin OCR should be verified with the correct language hint, or the ingest may preserve layout but lose Korean text quality.

`src/ht_lens/embedding/chunk_backfill.py` embeds only translated `text`/`heading` chunks with source length `>= 30`. The plan’s “emb>0” check can pass while most short but important chunks are intentionally unembedded, weakening the proposed cross-doc RAG evidence.

## 4. Alternative approaches

Use a disposable copy of `data/ht_lens_v2.db` for the whole batch, then promote it only after all doc-level checks pass. That is safer than mutating the existing cutover candidate in place, especially because the DB is gitignored and the plan has no rollback snapshot beyond “1.x prod 무손상”.

Create a migration manifest before running commands: exact PDF path, intended display filename, SHA256, output directory, expected page count, command, exit code, chunk count, translated count, failed count, embedding count. This can be a phase artifact, not a new `scripts/` file, and it closes the current source-identity gap.

For Aggarwal, split extraction into smaller page ranges using an existing PDF tool such as `qpdf`, `mutool`, or PyMuPDF before MinerU. Smaller units make timeout, retry, disk, and verification failures local instead of turning one 518-page extraction into an all-or-nothing background job.

## 5. Missing tests

Add `test_extract_mineru_cli_supports_large_timeout` if Aggarwal remains in scope. The current CLI has no timeout option, so the plan’s large-PDF path is not testable against `run_mineru`’s 3600-second default.

Add `test_ingest_mineru_records_src_pdf_sha256` or explicitly remove SHA-based source claims from the verify plan. Without this, the migration cannot prove that `2503.09642v2` or `2603.03482v1` in the DB corresponds to the intended PDF file.

Add `test_ingest_mineru_duplicate_filename_different_pdf_is_rejected_or_disambiguated`. Current duplicate detection is filename-based, which is fragile for batch migration.

Add `test_phase_8e2_reflow_doc_has_no_failed_text_translations`. The planned API 200 check does not catch `ChunkTranslation.status == "failed"` rows that `get_reflow` suppresses.

Add `test_phase_8e2_cross_doc_rag_returns_ref_with_different_doc_id`. The current “related_chunks 등장” criterion can be satisfied by same-document retrieval and would not prove cross-document RAG is live.
