# Phase 2b — Verify (v3, post Planner-directed fix)

> v2 superseded after Planner-directed targeted fix (Round 2 REJECT new issues).
> All checks re-run on current HEAD after two fix commits.

## 5-A. Automated checks

| Check | Command | Result |
|-------|---------|--------|
| Type (mypy strict) | `uv run --extra dev mypy src/` | **Success: no issues found in 39 source files** |
| Lint + Format (ruff) | `uv run --extra dev ruff check src/ tests/` | **All checks passed!** |
| Tests (not llm) | `uv run --extra dev pytest -m "not llm" -q` | **147 passed, 4 deselected, 0 failed** |
| Phase 2a 무회귀 | 위 동일 (97 Phase 2a 테스트 포함) | **0 failed** |
| git status clean | `git status` | **커밋할 사항 없음, 작업 폴더 깨끗함** |

## 5-B. Functional checks

### Files delivered

| Path | Action | Status |
|------|--------|--------|
| `src/ht_lens/llm/errors.py` | NEW | ✅ |
| `src/ht_lens/llm/openai_compat.py` | NEW | ✅ |
| `src/ht_lens/llm/mock.py` | MODIFY (FailMockLLMClient added) | ✅ |
| `src/ht_lens/llm/factory.py` | MODIFY (mock_fail provider added) | ✅ |
| `src/ht_lens/db/migrations/versions/0002_phase_2b_cache_and_sha.py` | NEW | ✅ |
| `src/ht_lens/db/models.py` | MODIFY | ✅ |
| `src/ht_lens/db/session.py` | MODIFY (ALEMBIC_HEAD=0002) | ✅ |
| `src/ht_lens/ingest/pipeline.py` | MODIFY (sha256 저장) | ✅ |
| `src/ht_lens/translate/__init__.py` | NEW | ✅ |
| `src/ht_lens/translate/__main__.py` | NEW | ✅ |
| `src/ht_lens/translate/cache.py` | NEW | ✅ |
| `src/ht_lens/translate/pipeline.py` | NEW | ✅ |
| `src/ht_lens/translate/cli.py` | NEW | ✅ |
| `src/ht_lens/cli.py` | MODIFY (translate 등록) | ✅ |

### Tests delivered (50 new, 4 @llm deselected in fast run)

| Test file | Count | Notes |
|-----------|-------|-------|
| `tests/unit/test_cache_key.py` | 7 | sha256 determinism, nul separator |
| `tests/unit/test_safe_extract.py` | 12 | length→Transient, None/list content |
| `tests/unit/test_llm_errors.py` | 6 | hierarchy, isinstance |
| `tests/integration/test_translate_pipeline_mock.py` | 16 | e2e, cache, retry, skip, dry_run |
| `tests/integration/test_translate_cli.py` | 7 | subprocess exit codes (exit 0/1/2/3/4, dry-run bypass) |
| `tests/integration/test_alembic.py` | +1 | 0001→0002 upgrade path |
| `tests/unit/test_llm_mock.py` | +1 | from_env openai_compat |
| `tests/integration/test_translate_pipeline_live.py` | 2 (@llm) | skipped without endpoint |
| `tests/integration/test_health_check_live.py` | 2 (@llm) | skipped without endpoint |

### Planner-directed fixes applied (post Round 2 REJECT)

| Round 2 issue | Fix |
|---------------|-----|
| Dry-run regression: health_check() runs even for --dry-run | ✅ Moved inside `if not dry_run:` — dry-run now works offline |
| Untested CLI branches: stats.failed → exit 1, LLMHealthCheckFailed → exit 1 | ✅ Added 3 subprocess tests; exit code for LLMHealthCheckFailed changed to 4 |

### CLI exit code scheme (final)

| Exit | Condition |
|------|-----------|
| 0 | success (or dry-run) |
| 1 | `stats.failed > 0` after translation |
| 2 | document not found (`ValueError`) |
| 3 | `SchemaVersionMismatch` |
| 4 | `LLMHealthCheckFailed` |

### DoD mapping

| DoD item | 결과 |
|----------|------|
| short fixture 번역 가능 | ✅ test_translate_two_text_blocks, CLI exit 0 (mock) |
| 재실행 캐시 hit 100% | ✅ test_translate_skips_already_translated, test_translate_db_cache_hit_on_second_doc |
| 실패 block 재시도 | ✅ test_retry_failed_reprocesses_failed_blocks |
| reasoning_tokens == 0 회귀 체크 | ✅ health_check() CLI에서 연결 (non-dry-run); @llm test 설계 완료 |
| finish_reason='length' + empty 가드 | ✅ test_safe_extract_raises_transient_on_length_{empty,nonempty} |
| CLI exit 1 on block failure | ✅ test_translate_exit_1_on_block_failure (mock_fail subprocess) |
| CLI exit 4 on health_check failure | ✅ test_translate_exit_4_on_health_check_failed (unreachable endpoint) |
| dry-run offline | ✅ test_translate_dry_run_bypasses_health_check (unreachable endpoint + --dry-run → exit 0) |
| mypy strict 0 | ✅ 39 files, 0 issues |
| ruff clean | ✅ 0 errors |
| Phase 2a 테스트 무회귀 | ✅ 147 passed (0 regressions) |

## 5-C. Scoring (v3)

| Item | Score / Max | Evidence |
|------|-------------|---------|
| 독창성 (correctness, design) | 13 / 15 | All Round 2 new bugs fixed. health_check properly scoped to non-dry-run. FailMockLLMClient clean. 감점: sequential loop |
| 완결성 (scope delivery) | 32 / 35 | All plan files, 9 plan revisions, 2 Planner fixes. CLI exit scheme complete. 감점: live @llm 실측값 없음, default provider still mock |
| 안정성 (test coverage, zero failures) | 28 / 30 | 147/147 passing, mypy/ruff 0, 3 new CLI failure branch tests. 감점: pipeline.py 일부 branch 미커버 |
| 확장성 (design future-proofing) | 15 / 20 | block_types, concurrency param, dry_run, cache 2-tier, mock_fail for test injection. 감점: sequential loop, sglang-specific chat_template baked in |
| **Total** | **88 / 100** | |

## 5-D. Self verdict

- [ ] PASS_CANDIDATE (>=95)
- [x] **PASS (88)** — Planner-directed fix complete. Both Round 2 new bugs fixed with tests. cross-verify 재호출 금지 per Planner instruction. Submit for Planner PASS confirmation.
- [ ] FAIL → RE-CODE
- [ ] FAIL → RE-PLAN

> Note: 88 is below the >=95 PASS_CANDIDATE threshold. Per Planner directive, cross-verify is not re-run. Planner decides PASS/FAIL directly.
