## 1. Over-engineering

- The new `src/ht_lens/embedding/factory.py` is too much abstraction for this phase. Only `src/ht_lens/translate/cli.py::translate_command` would use it, while `src/ht_lens/cli.py::embed_command` and `src/ht_lens/api/app.py::_lifespan` still construct `BgeM3Client()` directly. Either refactor all embedding entry points together or keep the helper local to the CLI change.

- Shipping `_FailingMockEmbeddingClient` behind `EMBEDDING_PROVIDER=mock_fail` is test scaffolding leaking into runtime surface area. ROADMAP Phase 7a-3 only asks for auto-embed persistence and graceful degradation; it does not justify adding fake production providers.

- The plan also redesigns CLI output (`embedded=...`, `embed_skipped=...`, new `partial:` line). That is more churn than the DoD requires. A minimal suffix or warning is enough; inventing new output modes increases regression risk in `tests/integration/test_translate_cli.py` for little value.

## 2. Hidden assumptions

- The plan assumes “graceful degradation” covers embedding client construction failure, but the sketch does not. In `.claude/phases/phase-7a-3/plan.md` Approach §2, `from_env_embedding()` is called before the `try/except` around `backfill()`, so a `BgeM3Client()` init/download/import failure will still abort `translate_command`. That does not match the fail-soft behavior in `src/ht_lens/api/app.py::_lifespan`.

- The subprocess test strategy assumes a clean host environment. `tests/integration/test_translate_cli.py::_run_translate` strips `LLM_*` keys but not `EMBEDDING_PROVIDER` or `RAG_DISABLED`, and `src/ht_lens/dotenv_loader.py::load_repo_dotenv` uses `override=False`. A developer shell export can silently flip the new tests or the default runtime path.

- The plan assumes embedding after `stats.failed > 0` is always desirable. But `src/ht_lens/translate/pipeline.py::_finalize_document_status` marks the document `partial_translated`, and `src/ht_lens/embedding/search.py::search` does not filter by translation status. If that assumption is wrong, cross-doc RAG can surface partially valid or stale documents.

- `EMBEDDING_PROVIDER=mock` is treated as harmless test config, but it writes 32-dim rows into `block_embeddings`. In a real DB with existing 1024-dim `bge-m3` rows, that can create mixed-dim behavior that later depends on `src/ht_lens/embedding/store.py::load_all` majority-dim heuristics.

## 3. Edge cases

- Constructor-time failure is the real ops edge case, not `encode()` failure. Fresh machine, missing `sentence_transformers`, bad HF cache, or download failure all happen before `backfill()` starts; the plan only simulates failure inside `encode()`.

- Partial retry is underspecified. With `--retry-failed`, `backfill()` only upserts candidates with `Translation.status='translated'` (`src/ht_lens/embedding/backfill.py::_candidate_blocks`), but it never deletes old embeddings for blocks that remain failed. That can leave stale RAG-visible rows behind.

- Re-running `ht-lens translate --doc-id N` on an already translated document will still run `backfill()`. The plan does not say whether `embedded=0 skipped=N` is acceptable UX or noisy behavior, even though the phase’s stated value is operational cleanliness for long-running CLI jobs.

- The user-facing command in ROADMAP is `ht-lens translate --doc-id N`, but the plan’s tests target `python -m ht_lens translate`. Phase 6e-2 already showed those launcher paths are not interchangeable.

## 4. Alternative approaches

- Reuse the existing embed path instead of inventing a new provider factory. Factor a small internal helper from `src/ht_lens/cli.py::embed_command` and call it from `translate_command`; that keeps one embedding execution path and avoids a one-off `embedding/factory.py`.

- If a factory is truly needed, apply it everywhere in one phase: `translate/cli.py`, `cli.py::embed_command`, and `api/app.py::_lifespan`. A single-caller factory plus direct constructors elsewhere is the worst middle ground.

- For failure injection, use the existing subprocess monkeypatch pattern from `tests/integration/test_translate_cli.py` rather than adding `EMBEDDING_PROVIDER=mock_fail` to production config. That keeps fake providers out of runtime semantics.

## 5. Missing tests

- Add `test_translate_cli_auto_embed_init_failure_is_non_fatal`. Force `BgeM3Client()` construction to raise and assert the CLI still exits per translate result, because this is the branch the plan currently gets wrong.

- Add `test_ht_lens_console_script_translate_auto_embeds_with_mock_provider`. `tests/integration/test_translate_cli.py` already distinguishes module entrypoint from installed `ht-lens`; this phase should too.

- Add `test_translate_cli_partial_failure_still_embeds_successful_blocks`. The plan explicitly promises “embed 시도 + exit code 1 유지” when `stats.failed > 0`, but no proposed test proves that mixed-success contract.

- Add a deterministic env-isolation test for `EMBEDDING_PROVIDER` and `RAG_DISABLED`. Without that, the new subprocess tests remain host-env dependent.

- Add `test_translate_cli_existing_translations_skip_auto_embed_cleanly` if the success line changes. The plan is changing normal-path output, so it needs a regression test for the common rerun path, not only the fresh-doc path.
