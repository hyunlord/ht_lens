# Phase 7a-3 — Verify (self)

Pre-flight: `git status` clean ✅. HEAD = `2ddc59b feat(phase-7a-3): CLI translate auto-embed chain`.

## 5-A. Automated checks

| Check    | Command | Result |
| -------- | ------- | ------ |
| Lint     | `uv run ruff check src/ tests/` | `All checks passed!` (0 errors) |
| Format   | `uv run ruff format --check src/ tests/` | `141 files already formatted` (after `ruff format` applied) |
| Type     | `uv run mypy --config-file pyproject.toml src/` | `Success: no issues found in 68 source files` (was 67 — +1 for `embedding/factory.py`) |
| Test     | `uv run pytest -m "not llm and not slow" -q --no-cov` (WORKFLOW.md §143 spec) | **529 passed, 1 skipped, 7 deselected, 9 warnings in 351.42s** (baseline 521 → 529, +8 new) |
| Coverage | (policy: not measured) | n/a |
| CI       | post-push verification (Stage 6) | pending |

### 신규 테스트 (총 +8)

#### Subprocess (`tests/integration/test_translate_cli_auto_embed.py`, 6 tests)
1. `test_translate_cli_auto_embeds_with_mock_provider` — default path. `LLM_PROVIDER=mock EMBEDDING_PROVIDER=mock` → `embed: embedded=3`, DB rows=3, exit 0.
2. `test_translate_cli_no_embed_flag_skips_embedding` — `--no-embed` opt-out. stdout `embed: skipped (--no-embed)`, embeddings=0.
3. `test_translate_cli_rag_disabled_env_skips_embedding` — `RAG_DISABLED=1`. stdout `embed: skipped (RAG_DISABLED)`, embeddings=0.
4. `test_translate_console_script_auto_embeds` — `ht-lens` console script (not `python -m`). Codex debate §3.4. `shutil.which` skip-guard.
5. `test_translate_cli_rerun_clean_output` — idempotent rerun. 2nd call: `embed: embedded=0 skipped=3` (Codex §3.3).
6. `test_embed_command_refuses_when_rag_disabled` — `ht-lens embed` with `RAG_DISABLED=1` → exit 5 + stderr "RAG_DISABLED". Locks factory wire-up in `cli.py::embed_command`.

#### Unit (`tests/unit/test_translate_command_unit.py`, 2 tests)
7. `test_translate_command_partial_failure_still_embeds_successful_blocks` — Codex §5c. `_PartialFailLLM` fails first block, succeeds on rest. Verified: exit 1, `stats.failed==1`, `stats.translated==2`, `block_embeddings` rows=2.
8. `test_translate_command_handles_factory_raise` — Codex §5a + V1 critical bug fix. `from_env_embedding` monkeypatched to raise. Verified: exit 0, stdout `embed: failed (see stderr)`, stderr `auto-embed failed: ...` with original exception text, embeddings=0.

### Codex debate critical bug — direct lock

V1 plan called `from_env_embedding()` outside the `try/except`. A `BgeM3Client()` init failure (offline, bad HF cache, missing torch) would have aborted the CLI. **Test 8** locks this regression: with the factory raising `RuntimeError`, the CLI still returns exit 0 with translate's stats and only logs a stderr warning.

### Backward compat (existing tests)

기존 `test_translate_cli.py` 17 tests, `test_pipeline_auto_embed.py`, RAG tests 모두 통과. stdout 변경은 **새 줄 추가만** (기존 `ok:` / `warning:` lines 그대로) → 기존 substring 검증 (line 119, 457 `"ok:" in proc.stdout`) 영향 없음.

## 5-B. Functional checks

### 5-B-1. Sub-goal 1 — CLI auto-embed chain

| Contract | Test | Status |
| -------- | ---- | ------ |
| Default auto-embed runs | 1 | ✅ stdout `embed: embedded=3`, DB rows=3 |
| `--no-embed` opt-out | 2 | ✅ stdout `embed: skipped (--no-embed)` |
| `RAG_DISABLED=1` skip at factory | 3 | ✅ stdout `embed: skipped (RAG_DISABLED)` |
| Console script `ht-lens translate` equivalence | 4 | ✅ identical output |
| Idempotent rerun | 5 | ✅ 2nd call: `embed: embedded=0 skipped=3` |

### 5-B-2. Sub-goal 2 — Factory 3 caller wire-up

| Caller | Wire-up evidence |
| ------ | ---------------- |
| `src/ht_lens/translate/cli.py::translate_command` | Tests 1/2/3 (factory BgeM3 / mock / None) |
| `src/ht_lens/cli.py::embed_command` | Test 6 (factory None → exit 5) |
| `src/ht_lens/api/app.py::_lifespan` | All API tests pass (behavior-preserving) |

`test_pipeline_auto_embed.py::test_process_upload_job_auto_embeds_after_translate` 계속 통과 → lifespan refactor가 동작 보존.

### 5-B-3. Sub-goal 3 — Graceful degradation

| Failure mode | Test | Behavior |
| ------------ | ---- | -------- |
| Embed factory `RuntimeError` (V1 critical bug) | 8 | stderr warning, exit 0 |
| Partial translate failure | 7 | exit 1, embed runs on succeeded blocks only |
| `RAG_DISABLED=1` | 3, 6 | factory returns None, caller short-circuits |

### 5-B-4. RE-CODE regression check (CLAUDE.md 규칙)

본 phase는 단일 implementation round (RE-CODE 없음). 모든 변경 영역을 신규 테스트로 직접 lock:

| Production change | Locking test |
| ----------------- | ------------ |
| `embedding/factory.py::from_env_embedding` (new) | Tests 1, 3, 6, 8 (모든 분기) |
| `translate/cli.py` `--no-embed` flag | Test 2 |
| `translate/cli.py` auto-embed chain inside try/except | Tests 1, 7, 8 |
| `translate/cli.py` `embed: ...` output line (5 distinct strings) | Tests 1, 2, 3, 5, 8 |
| `cli.py::embed_command` factory wire-up | Test 6 |
| `api/app.py::_lifespan` factory wire-up | Existing API tests (behavior-preserving) |

새 식별자 grep 검증:
- `from_env_embedding` → 1 production module + 3 caller files + 2 test files
- `--no-embed` flag → CLI help + 1 test reference
- `embed:` output prefix → 1 production + 5 test substring assertions

### 5-B-5. CI status

push 후 측정 (Stage 6). 별도 보고.

## 5-C. Scoring (100, self-assessment)

| Item       | Score / Max | Evidence |
| ---------- | ----------- | -------- |
| 독창성     | 12 / 15     | Factory pattern은 standard. `EMBEDDING_PROVIDER=mock` test infrastructure가 minor invention. -3: novelty 낮음 (Phase 7a Fix c 패턴 그대로). |
| 완결성     | 32 / 35     | DoD 8 items 모두 충족. -3: ROADMAP §C (Phase 7a-2 user-deferred) + `--retry-failed` stale embedding GC (Codex §3.2 defer) 잔존. |
| 안정성     | 27 / 30     | 회귀 0 (521→529), Codex critical bug (init failure) test 8로 직접 lock, partial failure semantics test 7로 lock. -3: CI pending + live BgeM3Client 동작 test 부재 (mock 의존). |
| 확장성     | 18 / 20     | Factory가 향후 다른 embedding 모델 / 다른 caller 추가 용이. -2: lifespan의 init failure 처리가 factory가 아닌 caller side. |
| **Total**  | **89 / 100** | WORKFLOW.md §217-223 ≥95 미달 → PASS_CANDIDATE 라벨 X (Phase 7a-2 V3 학습한 정직 라벨링). |

V1 plan의 critical bug (Codex §2.1: init failure 처리)를 plan V2에서 직접 fix + test 8로 lock. 본 phase는 single-round implementation 후 verify (RE-CODE 없음).

## 5-D. Self verdict

- [ ] PASS_CANDIDATE (≥95) — **불가**. self-score 89 < 95 (WORKFLOW.md §217-223 정직 라벨링).
- [x] **PASS_LOW** — DoD 충족 + critical 항목 fix. Cross-verify Round 1 후 판단:
  - CONFIRM_PASS → Stage 6 push.
  - DOWNGRADE/REJECT (minor) → Planner-directed micro-fix (Phase 7a-2 Option B+ 패턴) 가능.
  - DOWNGRADE/REJECT (critical) → RE-CODE 또는 RE-PLAN.
- [ ] FAIL → RE-PLAN

5-B Round 1 cross-verify (`bash scripts/run_verify_cross.sh 7a-3`) 실행.
