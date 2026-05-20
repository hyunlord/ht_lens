# Phase 2b — Summary

## Status
PASS (88/100, self) — awaiting Planner PASS confirmation. cross-verify 미재호출 per Planner directive.

## Score
Self (v3): 88 / 100
Codex Round 1: REJECT ~62/100
Codex Round 2: REJECT ~68/100
cross-verify Round 3: 미호출 (Planner 지시)

## What was built

Phase 2b delivered the full async translation pipeline on top of Phase 2a's ingest:

- **`src/ht_lens/llm/errors.py`** — LLM error hierarchy (LLMError → Transient/Permanent/HealthCheckFailed/Empty)
- **`src/ht_lens/llm/openai_compat.py`** — OpenAI-compat client for sglang Qwen3.6-27B: `enable_thinking=False`, `finish_reason='length'` → LLMTransientError, None/list content guard, `reasoning_tokens==0` health check
- **`src/ht_lens/llm/mock.py`** — Added `FailMockLLMClient` for deterministic failure injection in subprocess tests
- **`src/ht_lens/translate/pipeline.py`** — Block-level async translate pipeline: 2-tier cache (in-memory dedup + DB cross-run), block-level commit, exponential backoff retry, dry-run mode
- **`src/ht_lens/translate/cli.py`** — `python -m ht_lens.translate --doc-id <id>` with health_check (skipped in dry-run), exit codes 0/1/2/3/4
- **`src/ht_lens/db/migrations/versions/0002_phase_2b_cache_and_sha.py`** — Alembic migration: `cache_key` on translations, `src_pdf_sha256` on documents
- 50 new tests (147 total passing, 4 @llm deselected)

## RE-CODE history

**Round 1 REJECT (~62/100) → RE-CODE:**
1. CLI silently exits 0 when blocks fail → `raise typer.Exit(code=1)` when `stats.failed > 0`
2. `health_check()` not wired → added to CLI `_run()`
3. `_dry_run_stats` double-counts duplicate texts → fixed with `seen: set[str]`

**Round 2 REJECT (~68/100) → Planner-directed fix (cross-verify 미재호출):**
1. Dry-run regression: `health_check()` ran even for `--dry-run` → moved inside `if not dry_run:`
2. Untested CLI failure branches → added `FailMockLLMClient` + `mock_fail` provider + 3 subprocess tests; `LLMHealthCheckFailed` exit code changed from 1 to 4

## CLI exit code scheme (final)

| Exit | Condition |
|------|-----------|
| 0 | success or dry-run |
| 1 | `stats.failed > 0` |
| 2 | document not found |
| 3 | `SchemaVersionMismatch` |
| 4 | `LLMHealthCheckFailed` |

## Files changed (Phase 2b total)

```
src/ht_lens/cli.py                                                 |   4 +
src/ht_lens/db/migrations/versions/0002_phase_2b_cache_and_sha.py |  36 +++
src/ht_lens/db/models.py                                           |   2 +
src/ht_lens/db/session.py                                          |   2 +-
src/ht_lens/ingest/pipeline.py                                     |   1 +
src/ht_lens/llm/__init__.py                                        |  27 ++-
src/ht_lens/llm/errors.py                                          |  37 +++
src/ht_lens/llm/factory.py                                         |  28 ++-
src/ht_lens/llm/mock.py                                            |  18 +-
src/ht_lens/llm/openai_compat.py                                   | 259 +++
src/ht_lens/translate/__init__.py                                  |   5 ++
src/ht_lens/translate/__main__.py                                  |   5 ++
src/ht_lens/translate/cache.py                                     |  14 ++
src/ht_lens/translate/cli.py                                       | 130 +++
src/ht_lens/translate/pipeline.py                                  | 267 +++
tests/conftest.py                                                  |  13 ++
tests/integration/test_alembic.py                                  |  50 ++
tests/integration/test_health_check_live.py                        |  37 +++
tests/integration/test_translate_cli.py                            | 219 +++
tests/integration/test_translate_pipeline_live.py                  | 138 +++
tests/integration/test_translate_pipeline_mock.py                  | 481 +++
tests/unit/test_cache_key.py                                       |  38 +++
tests/unit/test_llm_errors.py                                      |  54 +++
tests/unit/test_llm_mock.py                                        |  14 ++-
tests/unit/test_safe_extract.py                                    | 107 +++
```

## Evidence index
- plan: `.claude/phases/phase-2b/plan.md`
- debate: `.claude/phases/phase-2b/debate.md`
- challenge: `.claude/phases/phase-2b/challenge.md`
- verify: `.claude/phases/phase-2b/verify.md` (v3, post Planner fix)
- verify-cross r1: overwritten by r2
- verify-cross r2: `.claude/phases/phase-2b/verify-cross.md`

## Known issues / debt (remaining)
- Sequential translate loop (Phase 3 scope: `asyncio.gather` concurrency)
- Live sglang DoD evidence deferred to `@llm` tests (no CI endpoint)
- `test_live_second_run_all_cache_hits` asserts `cached==0` not `cached>0` (idempotence, not cache-key reuse)
- Default `LLM_PROVIDER` in factory is `mock` not `openai_compat`

## Deviations from plan
- Sequential loop instead of asyncio.gather (Phase 3 scope)
- Live endpoint tests are `@llm`-gated; not run in CI
- Default LLM_PROVIDER in factory remains `mock`

## Planner-directed fix summary
- cross-verify 재호출 금지 (Planner 명시 지시)
- Fix 1: dry-run bypasses health_check (`fix(phase-2b): dry-run bypasses health_check`)
- Fix 2: subprocess exit code coverage (`test(phase-2b): subprocess coverage for CLI failure exit codes`)
- Two additional commits for verify v3 + summary update

## Recommended next
Planner confirms PASS at current state (88/100) → proceed to Phase 3 (concurrent block processing, PDF overlay rendering).
