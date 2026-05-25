## 1. Over-engineering
- `plan.md:22,62-65` adds a process-global matrix cache with invalidation before proving a plain brute-force pass is too slow. For the stated `478`-block corpus (`plan.md:14`), this is needless statefulness. Defer cache/dirty-flag logic until a latency check shows `load-all + dot-product` is the bottleneck.

- The scope keeps growing sideways: `source_hash`, `source_kind`, `delete_for_block`, `--source`, and `GET /blocks/{id}/related` (`plan.md:19,21,25,49-50,78,95`) are not required by `ROADMAP.md:280-292`. The phase goal is chat-time cross-doc context, not a generic embeddings platform plus debug surface. Cut the endpoint and dual-source plumbing unless they are tied to a DoD.

- The dependency plan is overbuilt and still undecided. `plan.md:122` says `sentence-transformers` or `transformers + torch`, but `plan.md:58` already commits to `AutoTokenizer`/`AutoModel`. Pick one stack. Leaving both options in the plan violates the workflow rule against vague design choices.

## 2. Hidden assumptions
- The plan assumes `BAAI/bge-m3` works with generic mean-pooling of `last_hidden_state` (`plan.md:58`). That is a major unstated quality assumption. If that embedding recipe is wrong, retrieval quality collapses while all DB/API tests still pass.

- `plan.md:84-86` is inconsistent with the current upload pipeline. `src/ht_lens/jobs/pipeline.py:42-58` only knows job statuses `pending/extracting/ingesting/translating/summarizing/done/failed`. Saying embed failure leaves job status `"translated"` confuses `Job.status` with `Document.status` and means the failure contract is not actually designed.

- `plan.md:162` assumes “SQLite WAL mode” makes backfill safe during chat traffic, but `src/ht_lens/db/session.py:1-4` explicitly says WAL tuning is deferred and only `foreign_keys=ON` is configured. That concurrency story is currently imaginary.

- The plan openly leaves key decisions unresolved in its own “debate questions” (`plan.md:158-162`): singleton placement, prompt format, default rollout flag, and runtime safety. Those are core design decisions, not follow-up questions. `WORKFLOW.md` Stage 1 expects them to be settled in the plan.

## 3. Edge cases
- Empty and non-text blocks are not handled. `Block.type` includes `image` and `table` (`src/ht_lens/db/models.py:61-80`), and `build_block_context` already has blank-block fallbacks (`src/ht_lens/api/chat_context.py:28-37`). `plan.md:14,76` still talks like all blocks are embeddable. You need explicit skip/filter rules for empty, image, table, and ultra-short fragment blocks.

- Fragment-heavy extraction is already a known risk in `ROADMAP.md:350-354,431-432`. Excluding only same-doc (`plan.md:72,94`) is not enough; other documents can still flood top-K with 1-30 character fragments, headers, or duplicated boilerplate. That will degrade chat quality faster than it helps.

- Prompt size is ignored. `src/ht_lens/api/routers/messages.py:99-105,151-156` sends full thread history plus `system=build_block_context(...)` on every turn. Adding five related blocks with original+translation content needs a truncation budget, or long threads will hit model limits unpredictably.

- Auto-embed on upload (`plan.md:84-86`) assumes first-run model availability. `plan.md:154` admits a 2GB model download, but there is no plan for offline/cold-start failure. That turns a working Phase 6d upload pipeline into a new failure mode on fresh machines.

## 4. Alternative approaches
- If Phase 7a is meant to establish the long-term vector layer, use `sqlite-vec` now. `ROADMAP.md:283` already recommends it. That removes the custom mutable cache, keeps filtering/querying in one place, and aligns better with the roadmap’s `~50K block` target than a temporary in-memory side path.

- If you keep brute-force, make it simpler: one internal retriever, no `search.py` cache, no `/blocks/{id}/related`, no `source_kind`/`--source`. Get chat-time retrieval working first, measure it, then decide whether the extra surfaces are justified.

- The backfill command should follow the existing CLI pattern in `src/ht_lens/cli.py`, not a new `python -m ht_lens.embedding.backfill` island. The repo already has standardized DB/env loading for CLI paths; bypassing that repeats the class of issues fixed in Phase 6e-2.

## 5. Missing tests
- The roadmap DoD requires a UI indicator for “다른 책의 관련 부분” (`ROADMAP.md:292`), but `plan.md:97-117` changes no frontend files and the test strategy has zero frontend coverage. Without a viewer/chat-panel test for that indicator, this phase cannot honestly claim PASS.

- There is no latency verification for the explicit DoD `< +500ms` (`ROADMAP.md:291`). `plan.md:146` only proposes mock tests plus manual relevance checks. Add a verify-time benchmark around `build_block_context` or `/threads/{id}/explain` with embeddings populated; otherwise latency is unmeasured.

- The upload pipeline needs a failure-path test. Add something like `test_process_upload_job_embed_failure_preserves_document_translation_state` near `tests/integration/test_api_jobs.py` and `tests/integration/test_phase6e_routing.py` to lock down job status, `error_message`, and restart-recovery behavior after embed failure.

- Backfill coverage is underspecified. `plan.md:135` says “real embedding OR mock embedding”, which is exactly the ambiguity the workflow forbids. Add explicit tests for idempotent rerun, stale `source_hash` refresh, skipping empty/non-text blocks, and an Alembic test extending `tests/integration/test_alembic.py` for the `block_embeddings` table/index. Also extend `tests/integration/test_api_messages.py` with a `RecordingMockLLM` assertion that the cross-doc section is actually passed via `system`, not inferred from response drift.
