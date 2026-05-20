## 1. Over-engineering

- `plan.md` Approach 11-14 piles migrations, LLM health checks, logging policy, CORS, cache headers, Swagger exposure, and static mounting into the first API slice. `ROADMAP.md` Phase 3 only requires REST endpoints, async consistency, schema separation, and `/static`; startup-side DB mutation and provider pings should be deferred or reduced to a schema check.

- The file plan adds both `src/ht_lens/cli.py` `serve` and `src/ht_lens/api/__main__.py` for the same server. That doubles option parsing, subprocess coverage, and failure modes for no DoD gain. One entrypoint is enough this phase.

- `uvicorn[standard]`, `LLM_CHAT_CONCURRENCY`, `HT_LENS_DATA_ROOT`, `/docs`, and serving `/static/.gitkeep` are extra moving parts. None are needed to prove “문서 조회 → 스레드 생성 → AI 응답”; they expand scope before the core API contract is even stable.

## 2. Hidden assumptions

- `src/ht_lens/ingest/pipeline.py:104-113` stores `Page.bg_image_path` as the original extract path. Approach 9 in `plan.md` assumes every valid image lives under `HT_LENS_DATA_ROOT` defaulting to `data/`. That is false for normal `ht-lens extract -o /tmp/out` then ingest flows, so legitimate pages will 500.

- `plan.md` line 80 says `MessageRead.model` comes from `llm_client.model`. The actual implementations expose `model_name` in `src/ht_lens/llm/mock.py:20` and `src/ht_lens/llm/openai_compat.py:49-65`, while the `LLMClient` Protocol in `src/ht_lens/llm/client.py:19-49` exposes no model attribute at all. The plan is assuming an interface that does not exist.

- File-level changes define only `POST /threads/{id}/messages` in `src/ht_lens/api/routers/messages.py`. `ROADMAP.md` explicitly lists `/threads/{id}/messages` as a Phase 3 deliverable, and the plan itself admits “messages list endpoint 부재”. It is assuming `GET /threads/{id}` can substitute for message-history retrieval, which is not the same contract.

## 3. Edge cases

- The transaction semantics for `/explain` and `/messages` are underspecified. `plan.md` lines 68-70 say one request equals one transaction, but do not say whether the user row is written before or after the LLM call. On `LLMTransientError`, a half-written history breaks `_should_prepend_block_context(...)=count==0` forever.

- Concurrent calls on the same thread are not addressed. Because `/explain` is intentionally non-idempotent, two overlapping requests can interleave as user-user-assistant-assistant unless you serialize per-thread writes or explicitly accept broken conversational order.

- `build_block_context` is page-local by construction. At the first or last block on a page, “±2 block” may need to cross into adjacent pages to preserve reading order; the current algorithm silently downgrades context quality exactly at page boundaries.

- Only empty image blocks get a fallback label. The schema already includes `header` and `table` block types in `ROADMAP.md`; empty headers, OCR-noisy tables, or multi-line tabular text will produce garbage context unless you define formatting or exclusion rules.

## 4. Alternative approaches

- Use `LLMClient.chat(..., system=...)` for the block context instead of prepending markdown to the first user message. `src/ht_lens/llm/client.py` already supports it, and `src/ht_lens/llm/openai_compat.py` already implements it. That keeps persisted user input clean and removes the count-based prepend hack.

- Keep startup side-effect free. A schema-version check is enough for Phase 3; running Alembic inside FastAPI lifespan is operational policy, not API behavior, and it creates reload-time races and harder test setup.

- Use `httpx.AsyncClient` with `ASGITransport` for integration tests instead of sync `TestClient`. The DoD requires async consistency; `TestClient` masks the exact async boundaries and lifecycle behavior this phase is supposed to validate.

## 5. Missing tests

- There are no startup-path tests for the most failure-prone logic in `api/app.py`. Add `test_app_startup_fails_on_llm_health_check`, `test_app_startup_skips_llm_check_with_flag`, and `test_app_rejects_schema_mismatch_or_runs_upgrade`.

- Add `test_page_image_serves_ingested_absolute_path`. The current strategy only tests the synthetic failure branch “bg_image_path outside data root => 500” and never proves that a normal Phase 2 ingest output is actually servable.

- Add history-atomicity tests: `test_messages_does_not_persist_partial_user_row_on_llm_failure` and `test_explain_retry_still_includes_block_context_after_failed_first_attempt`. These cover the exact corruption risk created by the count-based prepend rule.

- Add CLI coverage for the new entrypoints: `test_ht_lens_serve_respects_db_option` and `test_python_m_ht_lens_api_starts`. `src/ht_lens/cli.py` and `src/ht_lens/api/__main__.py` are in scope, but the plan does not test either.

- If `/threads/{id}/messages` is meant to satisfy the roadmap literally, add `test_get_thread_messages_returns_history_in_order`. The current test strategy never asserts that route because the plan never cleanly defines it.
