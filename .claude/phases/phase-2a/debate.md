## 1. Over-engineering

- `.claude/phases/phase-2a/plan.md` adds both `ht-lens db migrate` and a runtime schema gate via `current_schema_version()` / `SchemaVersionMismatch` in `src/ht_lens/db/session.py`. That is more lifecycle machinery than Phase 2a needs. ROADMAP only requires “Alembic migration 1개 생성, 적용 가능”; verifying `uv run alembic upgrade head` is enough. App-level schema enforcement can wait until Phase 3 owns startup lifecycle.

- The WAL / `synchronous=NORMAL` PRAGMA work in `make_engine()` is premature. Phase 2a is a serial ingest CLI, not a concurrent reader/writer workload. You are optimizing for Phase 2b before measuring it, while also adding SQLite-mode behavior that can complicate temp DB tests and portability.

- `src/ht_lens/llm/factory.py` with `from_env()`, provider branching, `chat()`, and `health_check()` is too much API surface for a phase whose DoD only says “`LLMClient` interface 정의 + `MockLLMClient`”. `tests/conftest.py` currently has a minimal placeholder; locking in a multi-method protocol now risks freezing the wrong abstraction before Phase 2b translation and Phase 5 chat requirements are concrete.

## 2. Hidden assumptions

- The plan never resolves primary key strategy for `documents/pages/blocks`. That is a major omission. `src/ht_lens/extract/pipeline.py` generates block IDs like `p1_b001`; those are not globally unique across documents. If the ORM uses extractor IDs as `blocks.id`, the second ingested document collides immediately.

- The “prompt-fixed” schema `translations(block_id PK, model, ...)` assumes exactly one translation row per block. That conflicts with ROADMAP Phase 2b cache key `hash(text + src + tgt + model)` and Phase 6 “모델 빠른 토글” / “block 단위 재번역”. Phase 2a is explicitly where the data model is supposed to be finalized; freezing the wrong key shape here guarantees a migration later.

- Reusing `ht_lens.extract.models.PageDoc` and `DocMeta` does not “자동 보장” ingest integrity. Those models only validate JSON shape in `src/ht_lens/extract/models.py`. They do not prove `doc_meta.num_pages` matches actual files, page numbers are contiguous, or each page PNG exists.

- `--src` / `--tgt` semantics are undefined. The plan introduces the flags but does not say whether they are required, defaulted, or derived. That matters because `DocMeta.lang_guess` can be `mixed` or `unknown`, which are not usable translation source languages. The DoD explicitly includes ingesting the mixed fixture.

- The schema choice for `pages` silently assumes `rotation` and `render.*` can be discarded. `tests/integration/test_rotated_page.py` proves they matter for PNG geometry. If ingest drops them now, Phase 4 must reopen raw JSON files or reconstruct geometry indirectly, which defeats the point of normalizing extractor output into DB rows.

## 3. Edge cases

- Filename-based overwrite is unsafe. Two different PDFs named `paper.pdf` from different directories will be treated as the same document because the plan keys re-ingest on `documents.filename`. `doc_meta.json` already carries `src_pdf_sha256`; ignoring it invites destructive collisions.

- Corrupt extract directories are under-specified: missing `page_0003.json`, extra stale `page_0053.json`, mismatched `doc_meta.num_pages`, or a missing `pages/page_0001.png`. Pydantic parse errors only catch one class of failure.

- Empty-text image blocks are already present in the real fixtures. `tests/integration/__snapshots__/test_extract_snapshot.ambr` contains `type: 'image'` with `text: ''` (for example `p4_b006`). Any ingest assertion or DB constraint that expects non-empty `original_text` is wrong.

- The overwrite rollback path is not proven. The plan says one transaction per document, but if `--overwrite` deletes old rows and then a later page fails validation after intermediate `flush()` calls, the old document must still survive. That is easy to get wrong and currently untested.

## 4. Alternative approaches

- Use surrogate integer PKs for `documents/pages/blocks` and store extractor IDs separately (`source_block_id`, or a unique `(page_id, order_idx)`). That avoids Phase 1 ID collisions while keeping joins straightforward.

- Do not lock `translations` to `block_id PK`. A better Phase 2a schema is `translations.id` plus a unique composite on `(block_id, src_lang, tgt_lang, model)`, or a separate cache table. That aligns with ROADMAP Phase 2b caching and Phase 6 model switching.

- Either persist `rotation`, `pixel_width`, `pixel_height`, and `scale` on `pages`, or persist a stable path back to the raw page JSON. Throwing away already-extracted geometry now only pushes mandatory Phase 4 state recovery into ad hoc file reads.

- If migration convenience is desired, a thin Python wrapper around Alembic is enough. The extra `db migrate` command plus runtime version enforcement is not the best tradeoff for this phase.

## 5. Missing tests

- `test_ingest_rejects_or_disambiguates_duplicate_filenames_with_different_sha256`: ingest two extract dirs with the same `doc_meta.filename` but different `src_pdf_sha256`.

- `test_ingest_detects_manifest_mismatch`: `doc_meta.num_pages` disagrees with discovered `pages/page_*.json`, or a page number in the sequence is missing.

- `test_ingest_accepts_empty_text_image_blocks`: persist `type == "image"` with `text == ""` cleanly. The current plan’s “first block `original_text` 비어있지 않음” check is brittle.

- `test_overwrite_rollback_preserves_existing_document_on_failure`: start from a valid DB, rerun with `--overwrite` against a tampered extract dir, and confirm the original rows remain.

- `test_ht_lens_console_script_ingest_and_db_migrate`: Phase 1 already distinguishes `python -m ...` from the installed `ht-lens` entry point in `tests/integration/test_module_cli.py`. The new `ingest` and `db migrate` commands need the same coverage.
