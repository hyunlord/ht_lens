# Phase 2b — Summary

## Status
ESCALATE TO PLANNER — Round 2 cross-verify REJECT

## Score
Self (v2): 94 / 100
Codex Round 2: REJECT ~68 / 100

## What was built

Phase 2b delivered the full async translation pipeline on top of Phase 2a's ingest:

- **`src/ht_lens/llm/errors.py`** — LLM error hierarchy (LLMError → Transient/Permanent/HealthCheckFailed/Empty)
- **`src/ht_lens/llm/openai_compat.py`** — OpenAI-compat client for sglang Qwen3.6-27B with `enable_thinking=False`, `finish_reason='length'` → LLMTransientError, None/list content guard, `reasoning_tokens==0` health check
- **`src/ht_lens/translate/pipeline.py`** — Block-level async translate pipeline with 2-tier cache (in-memory dedup + DB cross-run), block-level commit, retry with exponential backoff, dry-run mode
- **`src/ht_lens/translate/cli.py`** — `python -m ht_lens.translate --doc-id <id>` with health_check, exit codes 1/2/3, dry-run estimation
- **`src/ht_lens/db/migrations/versions/0002_phase_2b_cache_and_sha.py`** — Alembic migration adding `cache_key` to translations and `src_pdf_sha256` to documents
- 47 new tests (144 total passing, 4 @llm deselected)

## RE-CODE history (Round 1 REJECT → RE-CODE)

Round 1 (REJECT, ~62/100) raised three actionable issues, all fixed:
1. CLI silently exits 0 when blocks fail → fixed: `raise typer.Exit(code=1)` when `stats.failed > 0`
2. `health_check()` not wired before translation → fixed in CLI `_run()`
3. `_dry_run_stats` double-counts duplicate texts → fixed with `seen: set[str]`

## Round 2 REJECT — Codex issues

**New issues found in RE-CODE** (concrete, current):

1. **Dry-run regression** (`cli.py:57-60`): `llm.health_check()` always runs before checking `dry_run`, so `--dry-run` with `openai_compat` now requires a live endpoint even though dry-run should work offline.

2. **Untested CLI branches** (`cli.py:74-79`, `100-102`): `stats.failed > 0 → exit 1` and `LLMHealthCheckFailed → exit 1` have no subprocess test coverage. Only success, missing doc, dry-run (mock), and schema mismatch are covered.

**Unchanged standing issues** (no live endpoint available in CI):
- Live sglang DoD evidence is `@llm`-gated — no real sglang call verified
- `test_live_second_run_all_cache_hits` asserts `cached==0` not `cached>0`, proving idempotence not cache-key reuse
- Concurrent block processing is sequential loop (Phase 3 scope, parameter stub in place)

**Score discrepancy**: Self 94/100, Codex 68/100 (10+23+23+12). Main gap is completeness scoring — Codex penalizes missing live evidence and sequential loop heavily.

**Process note**: Self-score 94 is below the >=95 PASS_CANDIDATE threshold; should have been self-fail per WORKFLOW.md.

## Worker's position

The two new Codex issues are real bugs — the dry-run regression (health_check before dry_run check) and the untested failure branches are fixable within scope and do not require RE-PLAN. However, per CLAUDE.md rules, Round 2 is the cap and the result goes to Planner for decision.

If Planner authorizes a targeted fix cycle, the specific changes needed:
- Move `await llm.health_check()` inside `if not dry_run:` block in CLI
- Add `test_translate_exit_1_on_block_failure` subprocess test

The standing live-endpoint issues require a live sglang server; if Planner accepts `@llm`-deferred evidence as sufficient (consistent with Phase 2a decision), those can be documented as deferred.

## Files changed

```
src/ht_lens/cli.py                                                |   4 +
src/ht_lens/db/migrations/versions/0002_phase_2b_cache_and_sha.py |  36 +++
src/ht_lens/db/models.py                                          |   2 +
src/ht_lens/db/session.py                                         |   2 +-
src/ht_lens/ingest/pipeline.py                                    |   1 +
src/ht_lens/llm/__init__.py                                       |  27 ++-
src/ht_lens/llm/errors.py                                         |  37 +++
src/ht_lens/llm/factory.py                                        |  24 ++-
src/ht_lens/llm/openai_compat.py                                  | 259 +++
src/ht_lens/translate/__init__.py                                 |   5 ++
src/ht_lens/translate/__main__.py                                 |   5 ++
src/ht_lens/translate/cache.py                                    |  14 ++
src/ht_lens/translate/cli.py                                      | 127 +++
src/ht_lens/translate/pipeline.py                                 | 267 +++
tests/conftest.py                                                 |  13 ++
tests/integration/test_alembic.py                                 |  50 ++
tests/integration/test_health_check_live.py                       |  37 +++
tests/integration/test_translate_cli.py                           | 159 +++
tests/integration/test_translate_pipeline_live.py                 | 138 +++
tests/integration/test_translate_pipeline_mock.py                 | 481 +++
tests/unit/test_cache_key.py                                      |  38 +++
tests/unit/test_llm_errors.py                                     |  54 +++
tests/unit/test_llm_mock.py                                       |  14 ++-
tests/unit/test_safe_extract.py                                   | 107 +++
```

## Evidence index
- plan: `.claude/phases/phase-2b/plan.md`
- debate: `.claude/phases/phase-2b/debate.md`
- challenge: `.claude/phases/phase-2b/challenge.md`
- verify: `.claude/phases/phase-2b/verify.md` (v2, post-RE-CODE)
- verify-cross r2: `.claude/phases/phase-2b/verify-cross.md` (Round 2 REJECT)

## Known issues / debt
- `health_check()` runs even for `--dry-run` (dry-run regression from RE-CODE)
- `stats.failed > 0 -> exit 1` and `LLMHealthCheckFailed -> exit 1` CLI branches untested
- Sequential translate loop (Phase 3 scope: concurrent block processing)
- Live sglang DoD evidence deferred to `@llm` tests (no CI endpoint)
- `test_live_second_run_all_cache_hits` asserts `cached==0` not `cached>0` (skipped==2 behavior)

## Deviations from plan
- Sequential loop instead of asyncio.gather (Phase 3 scope)
- Live endpoint tests are `@llm`-gated; not run in CI
- Default LLM_PROVIDER in factory remains 'mock' (not 'openai_compat')

## Recommended next (Planner decision)
- **Option A — Targeted fix**: authorize one targeted RE-CODE for the two concrete new bugs only (dry-run regression + untested branches). Planner reviews final state directly without further cross-verify.
- **Option B — Accept as-is**: treat Phase 2b as PASS at ~80/100, document the two bugs as Phase 3 entry conditions, continue to Phase 3.
- **Option C — Strict FAIL**: re-plan Phase 2b with explicit live-endpoint evidence requirements and concurrent processing in scope.
