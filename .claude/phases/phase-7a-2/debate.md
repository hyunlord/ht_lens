## 1. Over-engineering

- The plan rewrites `_process_block()` and `_translate_with_retry()` around outcome enums and “stats race” avoidance, but the current increments in `src/ht_lens/translate/pipeline.py` do not yield between read and write. That is contract churn across multiple helpers for a race the code does not actually have.
- The service-wide LRU in `src/ht_lens/embedding/service.py` is broader than the measured hotspot. Only `src/ht_lens/api/chat_context.py::_build_cross_doc_refs` and `src/ht_lens/api/routers/blocks.py::related_blocks` need faster query vectors. Generic cache policy, eviction, and model-test seams should be deferred unless you first prove the service layer is the right abstraction.
- The plan adds verification machinery for “warm p95” while pushing `ROADMAP.md` Sub-goal C out of scope. That is complexity in the wrong place: optional cache semantics are being added while the actual Phase 7a-2 DoD still includes `DB batch commit 안전 (실패 시 rollback)`.

## 2. Hidden assumptions

- The translation design assumes one `AsyncSession` can be shared across `asyncio.gather()` tasks. SQLAlchemy’s asyncio docs explicitly say concurrent tasks should use a separate `AsyncSession` per task because the session is mutable transaction state: https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html#using-asyncsession-with-concurrent-tasks. If that assumption is wrong, the core plan is wrong.
- The plan claims “SQLite WAL mode (already default in this project — verify in `db/session.py`)”. That is false. `src/ht_lens/db/session.py` only enables `PRAGMA foreign_keys=ON`, and its docstring says WAL tuning was deferred. The write-contention argument is built on a DB mode the repo does not enable.
- The RAG fix assumes the Roadmap DoD `/explain latency p95 < 500ms` can be interpreted as warm-cache-only. Neither `ROADMAP.md` nor the existing API paths define it that way. For first-click traffic on new blocks, `chat_context.py` and `blocks.py` still cold-encode.
- The planned `test_bge_m3_cache_miss_distinct_texts` appears to assume one `_model.encode()` call per text. `BgeM3Client.encode()` is batch-oriented today, so two distinct misses in one call should usually be one backend encode, not two. The test strategy is already modeling the wrong behavior.

## 3. Edge cases

- Duplicate-text blocks are the biggest regression risk. `pending_cache: dict[str, str]` only deduplicates sequentially; under parallel scheduling two identical blocks can both miss, both call the LLM, and break `tests/integration/test_translate_pipeline_mock.py::test_translate_deduplicates_duplicate_blocks_in_memory`.
- Cancellation mid-run is not resolved. The plan keeps per-block commits but still only calls `_finalize_document_status()` on clean completion. A cancelled run can leave translated rows in `translations` while `documents.status` stays pre-run, which affects retries and UI state.
- Retry storms at `concurrency=7` are hand-waved away. Holding the semaphore during `_translate_with_retry()` backoff means a burst of transient 429/503/timeouts can occupy all 7 slots and destroy throughput precisely under load.
- The LRU cache does not deduplicate duplicates inside a single `encode(texts)` call. That matters for `src/ht_lens/embedding/backfill.py`, which batches many blocks and can include repeated text; first-use batches still pay full encode cost.

## 4. Alternative approaches

- For RAG latency, stop re-encoding blocks you already embedded. `src/ht_lens/api/chat_context.py::_build_cross_doc_refs` and `src/ht_lens/api/routers/blocks.py::related_blocks` both start from a `block_id`, and Phase 7a already added `block_embeddings`. Fetch the stored vector for the target block and use it as `query_vector`; fall back to `encode()` only if the row is missing. That fixes cold latency too.
- For translation, separate LLM concurrency from DB writes. A queue with N translate workers and one writer session, or one session per worker plus a dedicated batch writer, matches the Roadmap’s batch-commit DoD and avoids the shared-`AsyncSession` hazard entirely.
- If task fan-out remains, prefer `asyncio.TaskGroup` over manual `create_task`/`gather`/cancel loops. Python 3.11 is already the project baseline, and the asyncio docs give `TaskGroup` stronger failure-cancellation guarantees than `gather`: https://docs.python.org/3/library/asyncio-task.html#task-groups

## 5. Missing tests

- Add `test_translate_deduplicates_duplicate_blocks_in_memory_with_concurrency_2`: two identical text blocks, `concurrency=2`, assert exactly one LLM call and `stats.cached == 1`. This is the main untested regression introduced by parallelism.
- Add `test_translate_progress_keeps_exact_ticks_under_concurrency`: preserve the existing contract from `tests/integration/test_translate_progress.py` (`[(10, 23), (20, 23), (23, 23)]`). The plan weakens it to “monotonic” based on a race that is not real.
- Add a file-backed SQLite concurrency test, not an in-memory timing toy: `test_translate_concurrent_run_no_session_state_error` or equivalent. If the implementation switches to per-task sessions, `:memory:` will hide connection-visibility problems.
- Add `test_related_or_explain_reuses_query_vector_on_repeat` at the API layer with a counting embedding client. Unit-testing `BgeM3Client` alone does not prove `POST /threads/{id}/explain` or `GET /blocks/{id}/related` actually hit the optimization path.
- Add `test_bge_m3_cache_batches_distinct_misses_once` and `test_bge_m3_cache_deduplicates_duplicate_texts_within_one_batch`. The proposed cache tests do not cover the real batch semantics of `BgeM3Client.encode()`.
- Add `test_translate_cancel_mid_run_leaves_explicit_state`: cancel a long-running translation, then assert no leaked tasks and a defined post-cancel `Document.status` / `Translation.status` story. The plan currently preserves ambiguous behavior without locking it down.
