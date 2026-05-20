## 1. Over-engineering

- The plan adds both `src/ht_lens/translate/__main__.py` and root registration in `src/ht_lens/cli.py`. `ROADMAP.md` Phase 2b only requires `python -m ht_lens.translate --doc-id <id>`; widening the root CLI now adds wiring and test surface without satisfying any extra DoD item.

- `src/ht_lens/llm/errors.py` proposes five exception types plus SDK-specific mapping rules. For this phase, `translate/pipeline.py` only needs three behaviors: retryable, non-retryable, and the empty-response guard required by the Phase 2b DoD. The finer taxonomy is speculative until Phase 3 introduces another real caller.

- `--dry-run` and the `tqdm`/logging integration are not in `ROADMAP.md` or the DoD mapping. Phase 2b’s actual risk is correctness under cache/retry/live-sglang behavior; progress UX should be deferred until the pipeline semantics are stable.

## 2. Hidden assumptions

- The transaction story in `.claude/phases/phase-2b/plan.md` is internally contradictory. Approach 5 says “single commit… partial failure => overall rollback,” then the transaction note says failed blocks are marked and the run is not rolled back. That is not cosmetic; it changes how `src/ht_lens/translate/pipeline.py` must be written and what tests are valid.

- `src/ht_lens/llm/client.py` currently returns only `str` from `translate()` and `bool` from `health_check()`. The plan assumes `translate/pipeline.py` can still populate `translations.model`, inspect `finish_reason`, and enforce the reasoning-token regression check without widening the protocol or passing side-channel metadata.

- The cache design assumes DB lookup is enough. With end-of-batch commit, repeated text blocks within the same run will not see `translations.cache_key` until after commit unless there is an unstated in-memory dedupe layer.

- `llm/openai_compat.py` is named like a generic provider, but the planned `extra_body={"chat_template_kwargs": {"enable_thinking": False}}` is sglang-specific. If `src/ht_lens/llm/factory.py` later routes Ollama or OpenRouter through the same class, the default request shape becomes a built-in 4xx path.

- `translations.cache_key` is planned as `NOT NULL DEFAULT ''` with no uniqueness rule. That assumes every lookup will always filter on `status='translated'` and `cache_key != ''`; the plan never states that invariant.

## 3. Edge cases

- Two concurrent `python -m ht_lens.translate --doc-id X` runs against the same SQLite DB are not addressed. `src/ht_lens/db/models.py` has no document-level in-progress guard beyond a free-form `documents.status`, so duplicate LLM calls and last-write-wins updates are likely.

- The long-block decision is weak. “2000 chars” is not a proxy for `max_tokens=2048`, especially with mixed CJK+Latin input and target-language expansion. A provider can return truncated non-empty content with `finish_reason="length"`, and `_extract_safe` as described only rejects the empty-content case.

- OpenAI-compatible responses are not guaranteed to be `message.content: str`. Some providers return `None` or segmented content lists. The planned `_extract_safe(response)` discussion only covers the empty-string path.

- If the batch commits once at the end, a timeout, SIGINT, or final `session.commit()` failure discards every successful translation. That is a bad fit for the shared-GPU instability already called out in `ROADMAP.md`.

- `--retry-failed` is underspecified when a block already has a `translations` row from a previous model or target language. With `translations.block_id` still the PK in `src/ht_lens/db/models.py`, there is no versioning story.

## 4. Alternative approaches

- Use a dedicated cache table instead of overloading `translations`. A `translation_cache` keyed by `cache_key` plus source/target/model matches the Phase 2b cache requirement directly and avoids scanning other blocks’ rows or stuffing provenance into `translations.model` as `"cache-hit:..."`.

- Narrow the provider now. A `SGLangClient` is more honest than a prematurely generic `OpenAICompatibleClient`, because the Phase 2b deliverable and DoD are explicitly about real sglang behavior, including `reasoning_tokens == 0`.

- If partial success is intended, commit per block or in small chunks in `src/ht_lens/translate/pipeline.py`. That aligns with the retry model and makes `--retry-failed` useful after interruptions.

## 5. Missing tests

- `tests/integration/test_translate_pipeline_mock.py::test_translate_deduplicates_duplicate_blocks_within_single_run` should exist. Right now the plan never proves that identical text in one batch results in one LLM call, not many.

- `tests/integration/test_translate_pipeline_mock.py::test_translate_skips_existing_translated_rows_by_default` and `::test_retry_failed_only_requeues_failed_rows` are missing. The overwrite policy for existing `translations` rows is central and currently unspecified.

- `tests/integration/test_translate_cli.py::test_python_m_ht_lens_translate_exit_codes` is missing entirely. Phase 2b’s user-facing deliverable is the module CLI, so it needs subprocess coverage parallel to `tests/integration/test_module_cli.py`.

- `tests/integration/test_alembic.py::test_upgrade_0001_to_0002_preserves_existing_documents_and_indexes_cache_key` is missing. The plan adds `src/ht_lens/db/migrations/versions/0002_phase_2b_cache_and_sha.py`, but there is no stated upgrade-path test from a real Phase 2a DB.

- `tests/unit/test_safe_extract.py::test_safe_extract_rejects_truncated_nonempty_content` and `::test_safe_extract_handles_none_or_list_content` are missing. The current unit list only covers the simplest empty-string response path.
