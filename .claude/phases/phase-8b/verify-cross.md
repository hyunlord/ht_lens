## 1. Verification of automated checks

Lint/format/type/test evidence is credible on timing: `verify.md` was committed at `79328b5` after the code/test commits `3f948fc` and `6d36e31`, and there are no later code commits. Current untracked files are `.claude/phases/phase-8b/summary.md` and `verify-cross.md` stubs, not source changes, so I do not consider the report stale.

The test evidence is plausible but thinly documented: `648 passed, 1 skipped, 7 deselected` is reported, but no raw log artifact or command output is committed beyond `verify.md`. Coverage is explicitly not run (`--no-cov`), despite the workflow table carrying a coverage row. CI is also `n/a`; that is honest, but it means the 5-A table does not have a true CI signal.

One check they should have run but did not: a chunk-specific concurrency test. The debate required `test_chunk_translate_peak_concurrency_is_bounded_and_parallel`; `rg` finds no such test under `tests/integration/test_chunk_translate.py`, and the self-report admits only dedup was tested.

## 2. Verification of functional checks

The math preservation path is meaningfully exercised for common `$...$` / `$$...$$` cases via `tests/unit/test_math_protect.py` and `tests/integration/test_chunk_translate.py::test_text_translated_with_math_preserved`. Equation passthrough is also covered at `tests/integration/test_chunk_translate.py:80`.

Embedding generation is reasonably covered by `tests/integration/test_chunk_embed.py`, including type filtering, idempotency, model-change refresh, and cascade delete. That satisfies the “embedding 생성” DoD at pipeline level.

The “Phase 7a-2 5.66x 적용” DoD is not functionally exercised. `test_cache_dedup_one_llm_call_for_identical_content` proves duplicate content triggers fewer LLM calls, but it does not prove parallel execution, bounded peak concurrency, retry behavior under chunk concurrency, or cache-hit accounting. The self-report acknowledges this gap, so its own 5-B should not be read as full DoD evidence.

CLI functional coverage is incomplete. Phase 8b added `translate-chunks` and `embed-chunks` in `src/ht_lens/cli.py:372` and `src/ht_lens/cli.py:424`, but tests only cover `ingest-mineru` / `extract-mineru` in `tests/integration/test_cli_mineru.py`. There is no realistic CLI invocation for schema mismatch, missing LLM config, retry-failed, or disabled embedding.

## 3. Score audit

독창성 / 15: `12/15` is justified. The design is conservative reuse of existing block translation/embedding ideas with chunk dispatch and math protection. It is not especially novel, but it is appropriate and avoids a large new dependency.

완결성 / 35: `32/35` is too high. Translation and embedding basics are present, but the Phase 7a-2 concurrency claim is unproven, table behavior is untested, live qwen is not run, and new Phase 8b CLI commands have no tests. I would score `27/35`.

안정성 / 30: `27/30` is too high. There is good migration and 1.x preservation coverage, but new error/CLI paths are loose, `ChunkTranslateStats.cached` is dead accounting, and the placeholder-collision guard can bypass math protection entirely. I would score `23/30`.

확장성 / 20: `18/20` is slightly high. The tables are additive and the embedding helper reuse is clean, but chunk translation cache semantics are weaker than 1.x and may complicate 8e/8d reuse. I would score `16/20`.

Fair total: `78/100`, not because the core work is absent, but because several claimed Phase 7a-2/CLI contracts are only partially implemented or untested.

## 4. Issues missed (new this round)

`ChunkTranslateStats.cached` is never incremented. The field exists at `src/ht_lens/translate/chunk_pipeline.py:51` and is printed by the CLI at `src/ht_lens/cli.py:407`, but `_cached_translate()` only returns from `pending_cache` / `pending_futures` without touching stats (`chunk_pipeline.py:99-137`). There is no chunk test asserting `stats.cached`. This makes CLI output misleading and weakens the 5.66x evidence.

The chunk pipeline dropped 1.x persistent DB cache behavior. `src/ht_lens/translate/pipeline.py:227-242` looks up prior translations by `cache_key`; `src/ht_lens/translate/chunk_pipeline.py` has no equivalent `_db_cache_lookup`. Identical chunk content translated in an earlier document/run will call the LLM again, despite `chunk_translations.cache_key` and index existing in migration `0006`. That is a real divergence from the “Phase 7a-2 machine reuse” claim.

`translate-chunks` has weaker CLI error handling than the existing `translate` command. `src/ht_lens/cli.py:395-421` does not catch `LLMConfigurationError`, `LLMHealthCheckFailed`, or `ValueError(document not found)`, while `src/ht_lens/translate/cli.py:95-190` maps those cases to clean exit codes/messages. Since Phase 8b adds this command, the lack of CLI tests is not just a coverage nicety.

The placeholder collision guard is unsafe when collision text and real math coexist. `src/ht_lens/translate/chunk_pipeline.py:209-212` skips protection entirely if source contains a `⟦MATH0⟧`-shaped token, so `$...$` in the same chunk is sent raw to the LLM. `tests/unit/test_math_protect.py:89-91` only checks collision detection, not pipeline behavior. This is rare, but it is a direct hole in the “math byte-identical” contract for adversarial or copied text.

## 5. Verdict

**DOWNGRADE** — The self-report is honest about several limitations and the core translation/embedding paths are real, but the score is still generous. The main downgrade drivers are unproven chunk parallelism, missing Phase 8b CLI coverage, dead cache-hit accounting, and loss of persistent cache reuse compared with the 1.x Phase 7a-2 pipeline. I would treat this as about `78/100` and require a focused RE-CODE if the phase is expected to claim the Phase 7a-2 reuse DoD rather than merely a first chunk translation/embedding prototype.
