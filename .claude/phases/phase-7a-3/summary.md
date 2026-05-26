# Phase 7a-3 — Summary

## Status
**ESCALATE TO PLANNER** — Codex cross-verify Round 2 cap (CLAUDE.md 규칙) DOWNGRADE → push 보류, Planner-directed micro-fix or override 필요. 단 Codex 자체가 "not grounds for more RE-CODE"라 명시 — product는 견고.

코드 product 견고:
- CLI translate auto-embed chain (Sub-goal 1) ✅
- Embedding factory 3 caller wire-up (Sub-goal 2) ✅
- Graceful degradation incl. V1 critical bug fix (Sub-goal 3) ✅
- 521 → 533 tests passed (+12, 0 regression)
- lint / format / mypy clean (WORKFLOW.md spec 명령)

잔여 항목 (Codex R2):
- verify.md V2 text 오류: "default BgeM3Client() branch covered"는 사실 아님 (test 4도 `EMBEDDING_PROVIDER=mock` 설정). docstring/text-only fix.
- CI 결과 미확인 (post-push verification).
- `ruff check .` (repo-wide) 미실행 — WORKFLOW.md §140-141 spec과 micro-mismatch.

## Score

| | Self V2 | Codex R2 audit |
| --- | --- | --- |
| 독창성 | 12/15 | 12/15 (confirm) |
| 완결성 | 30/35 | 29/35 (-1: default-branch overclaim) |
| 안정성 | 25/30 | 24/30 (-1: default branch + CI pending) |
| 확장성 | 17/20 | 17/20 (confirm) |
| **Total** | **84/100** | **82/100** |

Codex R2 verdict: DOWNGRADE (very minor — score gap 2 points, "not grounds for more RE-CODE"). CLAUDE.md Round 2 cap.

## What was built

### Sub-goal 1 — CLI translate auto-embed chain ✅
- `src/ht_lens/translate/cli.py::translate_command`:
  - 새 `--no-embed/--embed` flag (default False = auto-embed on).
  - translate 완료 후 `from_env_embedding()` + `backfill(...)` 호출 (factory call + backfill 모두 outer try/except 안 — V1 critical bug fix).
  - dry_run / `--no-embed` / `RAG_DISABLED` / embed failure 모두 graceful skip.
  - 새 output line `embed: ...` (기존 ok/warning lines 그대로).

### Sub-goal 2 — Embedding factory ✅
- 새 파일 `src/ht_lens/embedding/factory.py`:
  - `from_env_embedding()` — RAG_DISABLED → None, EMBEDDING_PROVIDER=mock → `MockEmbeddingClient(dim=32)`, default → `BgeM3Client()`.
- 3 caller 모두 wire-up: `translate/cli.py`, `cli.py::embed_command`, `api/app.py::_lifespan`.

### Sub-goal 3 — Tests (+12)
- 8 R0 tests: subprocess (auto, --no-embed, RAG_DISABLED, console-script, rerun, embed_command RAG_DISABLED) + unit (partial-failure, factory-raise-graceful)
- 4 R1 tests (post-Codex R1 DOWNGRADE): dry-run silence, embed_command normal path, lifespan factory hit, lifespan factory raise

### CLI surface
- `ht-lens translate --doc-id N` (default): translate → backfill → exit 0
- `ht-lens translate --doc-id N --no-embed`: translate only
- `RAG_DISABLED=1 ht-lens translate ...`: translate → skip embed → exit 0
- `EMBEDDING_PROVIDER=mock`: test/dev only (dim=32, factory docstring warns about prod DB mixing)
- `ht-lens embed --doc-id N` (RAG_DISABLED=1): exit 5 + stderr

## Files changed

```
.claude/phases/phase-7a-3/{plan,debate,challenge,verify,verify-cross,summary}.md
src/ht_lens/api/app.py                             |  19 ++-
src/ht_lens/cli.py                                 |  11 +-
src/ht_lens/embedding/factory.py                   |  53 +++ (NEW)
src/ht_lens/translate/cli.py                       |  56 ++-
tests/integration/test_api_startup.py              |  63 +++
tests/integration/test_translate_cli_auto_embed.py | 355 +++ (NEW)
tests/unit/test_translate_command_unit.py          | 229 +++ (NEW)
```
Total: 13 files changed, 1457 insertions(+), 10 deletions(-).

## Deviations from plan

### V1 → V2 (after Codex debate)
1. **CRITICAL fix**: `from_env_embedding()` 호출도 outer try/except 안에 (V1 critical bug, Codex §2.1).
2. `_FailingMockEmbeddingClient` 제거 (production code pollution 회피, Codex §1.2). Failure injection은 unit-level monkeypatch.
3. Factory를 3 caller 모두 wire-up (Codex §1.1, §4.2).
4. CLI output 최소화: 기존 ok/warning lines 그대로, 새 줄 `embed: ...` 만 추가 (Codex §1.3).
5. subprocess env 격리 강화 (`EMBEDDING_*`/`RAG_*`/`HF_*` filter, Codex §2.2).
6. Tests 4 → 8개 (console-script + partial-fail + rerun + init-failure unit).

### V2 → R1 RE-CODE (after Codex verify-cross R1 DOWNGRADE)
7. dry-run silence test 추가 (Codex R1 §2).
8. embed_command normal path test 추가 (Codex R1 §2).
9. lifespan factory hit + raise tests 추가 (Codex R1 §4).
Total tests 8 → 12.

## Codex Round 2 잔여 항목 (Planner 검토)

### A. verify.md text 오류 (즉시 fix 가능)
- A1. V2 verify.md §5-A에서 test 4가 "default BgeM3Client() branch covered"라고 claim — 사실 아님. test 4도 `EMBEDDING_PROVIDER=mock`. 해결: verify.md V3에서 default branch는 "untested in CI (real BgeM3 download out of scope per `not llm` mark policy)" 명시.

### B. 5-A workflow-spec compliance
- B1. `ruff check src/ tests/` vs WORKFLOW.md §140-141 `ruff check .`. micro-mismatch. .claude/ 및 documentation md는 ruff 검사 대상 아니므로 사실상 동일. 단 spec 준수 차원에서 `ruff check .` 명령으로 재실행 가능.
- B2. CI pending — Stage 6 push 후 결과로 close.
- B3. Coverage `n/a` — 본 phase scope에서 정직 라벨.

### C. 기능적 잔여
- C1. Default `BgeM3Client()` branch live test 부재. 본 phase scope (mock-based CI) 외. 실 BgeM3 다운로드 + encode test는 `not llm` mark로 분리되어 있음.

## Recommended next

### V3 Planner-directed micro-fix candidate (Phase 7a-2 Option B+ precedent)
1. **verify.md V3** (A1): default-branch overclaim 제거 + honest 82/100 (Codex R2 audit 반영). text-only fix.
2. **`ruff check .`** (B1): full-repo lint 명령 한 번 더 실행 + verify에 결과 추가. command-only, code 변경 없음.
3. **summary.md** Status 갱신: ESCALATE → PASS (Option B+).
4. **push**: 9 commits → origin/main + CI 결과 확인.

### Human/Planner 위임 (별도)
5. ROADMAP v8 업데이트: Phase 7a-3 ✅ + v1.6 마일스톤 (Phase 7a-2 + 7a-3) 완료 라벨. 사용자 직접 (Phase 7a-2 V3 패턴).
6. Default BgeM3Client live integration test: doc 7 (Murphy PML 36K) 진행 시 자연 검증 (별도 phase 신설 안 함).

### Follow-up (별도 작업)
7. doc 7 강제 retranslate trigger — concurrency=7 + auto-embed chain 검증의 사실상 live test.
8. `--retry-failed` stale embedding GC (Codex debate §3.2 defer).
9. WAL mode 활성화 (별도 phase).
10. Phase 7b (User Profile + Persona) 진입.

## Evidence index

- plan: `.claude/phases/phase-7a-3/plan.md` (V1 → V2)
- debate: `.claude/phases/phase-7a-3/debate.md` (Codex 14 issues)
- challenge: `.claude/phases/phase-7a-3/challenge.md` (8 ACCEPT, 2 PARTIAL, 4 REJECT/DEFER, decision RE-PLAN)
- verify: `.claude/phases/phase-7a-3/verify.md` (V1 89 → V2 84)
- verify-cross: `.claude/phases/phase-7a-3/verify-cross.md` (R1 DOWNGRADE → RE-CODE → R2 DOWNGRADE → escalate)
- git log: `d897fe1 → 1823771` (10 commits in this phase)

## Known issues / debt

- `--retry-failed` stale embedding GC (Codex §3.2 defer, summary §C1)
- ROADMAP §C (DB batch commit, Phase 7a-2 user-deferred)
- Default `BgeM3Client()` factory branch live test 부재 (`not llm` mark scope)
- Mock dim=32 vs prod 1024-dim mixing risk (factory docstring + dev-only env guard)

## Push 정책

CLAUDE.md WORKFLOW 기본: "Round 2 REJECT/DOWNGRADE → push 보류, Planner escalate". 본 phase는 **Codex R2가 "not grounds for more RE-CODE"라 명시한 minor DOWNGRADE** (82 vs 84, 2점 차). Phase 7a-2 Option B+ precedent 가용.

- Option A (보수): push 보류 → Planner directive 대기.
- Option B+ (Planner-directed micro-fix, 7a-2 precedent): verify.md V3 + `ruff check .` 추가 evidence → push.
- Option C: 사용자가 직접 push override 결정.

Stage 6 push는 Planner directive 대기.
