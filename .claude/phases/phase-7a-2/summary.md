# Phase 7a-2 — Summary

## Status
**ESCALATE TO PLANNER** — Codex cross-verify Round 2 cap (CLAUDE.md 규칙) DOWNGRADE → push 보류, Planner-directed fix or override 필요.

코드 product는 견고 (5.66x speedup, 0.18ms stored-vector p95, 521 tests passed, lint/mypy clean). 그러나 verify.md V2의 process 위반 (self-score 87 → PASS_CANDIDATE 라벨, WORKFLOW.md는 ≥95 요구) + 일부 verify rigor 부족 (workflow-spec format/test 명령 미실행, RAG latency benchmark가 helper만 측정) 으로 Codex가 CONFIRM_PASS 거부.

## Score

| | Self (V2) | Codex Round 2 |
| --- | --- | --- |
| 독창성 | 13/15 | 13/15 (confirm) |
| 완결성 | 28/35 | 25/35 (deduct: ROADMAP §C unimplemented + latency at helper level) |
| 안정성 | 27/30 | 25/30 (deduct: CI pending + future-leak test 약함 + route latency 간접) |
| 확장성 | 19/20 | 18/20 (deduct: single locked AsyncSession is pragmatic, not extensible) |
| **Total** | **87/100** | **~81/100** |

Codex verdict: DOWNGRADE (not CONFIRM_PASS, not REJECT). Round 2가 cross-verify 상한이라 추가 round 호출 안 함.

## What was built

### Sub-goal A — Translation concurrency fix ✅
- `src/ht_lens/translate/pipeline.py`: sequential outer loop → `asyncio.as_completed` + `Semaphore(concurrency)`.
- 단일 `AsyncSession` 위에서 `db_lock`으로 mutual exclusion (SQLAlchemy 동시 사용 회피).
- Dedup safety: `pending_futures: dict[str, asyncio.Future]` — 동일 cache_key에 대한 in-flight LLM call 공유.
- Retry backoff sleep을 sem 밖에서 (slot 양보).
- Future exception consume (R1 fix): `own_future.exception()` after `set_exception()`로 unretrieved 경고 방지.
- Cancellation 정책: `Document.status` 변경 없음, 부분 commit된 `Translation` rows 보존.
- Default `concurrency: 5 → 7` (sglang `effective_max_running_requests_per_dp` 정합).

### Sub-goal B — RAG latency via stored vector reuse ✅
- `src/ht_lens/embedding/lookup.py` (NEW): `get_or_encode_block_vector`.
- `block_embeddings.vector` lookup → `source_hash` 검증 → 신선하면 reuse (~0.2ms), stale/miss면 encode() fallback (~575ms).
- `chat_context._build_cross_doc_refs` + `routers/blocks.related_blocks` 두 경로에 적용.

### Sub-goal C — DB batch commit
- **Skip per 사용자 결정 C**. Sub-goal A 적용 후 verify에서 SQLITE_BUSY / OperationalError 부재 확인 → skip 정당화.
- ROADMAP §C DoD 항목과는 tension (Codex 2회 지적). Planner 결정 필요.

### Test coverage
- 신규 13 tests:
  - `test_translate_concurrency.py` (6 tests): parallel, sequential c=1, partial failure, dedup-c2, future-leak (R1), retry slot-release (R1)
  - `test_translate_cancel.py` (1 test): cancellation policy
  - `test_translate_progress.py` (+1): concurrency=4 variant
  - `test_api_related.py` (+3): stored vector hit / miss / stale
  - `test_chat_context_rag.py` (+1): stored vector hit
  - `test_api_messages.py` (+1, R1): `/threads/explain` stored vector reuse
- 회귀 0: 508 → 521 passed.

## Files changed
```
.claude/phases/phase-7a-2/benchmarks/rag_latency_benchmark.py |  206 ++++
.claude/phases/phase-7a-2/benchmarks/throughput_benchmark.py  |  117 ++++
.claude/phases/phase-7a-2/{plan,debate,challenge,verify,verify-cross,summary}.md
src/ht_lens/api/chat_context.py                               |    5 +
src/ht_lens/api/routers/blocks.py                             |    5 +
src/ht_lens/embedding/lookup.py                               |   46 +
src/ht_lens/translate/cli.py                                  |   11 +
src/ht_lens/translate/pipeline.py                             |  262 ++/-
tests/integration/test_api_messages.py                        |  102 +
tests/integration/test_api_related.py                         |  106 +
tests/integration/test_translate_progress.py                  |   32 +
tests/unit/test_chat_context_rag.py                           |   33 +
tests/unit/test_translate_cancel.py                           |  175 +
tests/unit/test_translate_concurrency.py                      |  359 +
```
Total: 19 files changed, 2233 insertions(+), 66 deletions(-).

## Deviations from plan

1. **Plan V1 → V2 (after Codex debate)**: AsyncSession concurrent share unsafe → `db_lock` + `pending_futures`. LRU cache → stored vector reuse. WAL claim 제거. Retry sleep outside sem. Cancellation 정책 명시.
2. **RE-CODE R1 (after Codex verify-cross Round 1)**: Future exception never retrieved 보강 (`own_future.exception()`). Retry slot-release concurrency test. `/explain` stored vector integration test. Benchmarks committed under `.claude/phases/phase-7a-2/benchmarks/`.
3. **Sub-goal C 미구현**: 사용자 prompt에서 "Skip — measure first" 결정. 사후 verify에서 SQLITE_BUSY 부재 확인하여 skip 정당성 확보. **단 ROADMAP DoD §C와 충돌** (Codex 2회 지적). Planner 판단 필요.

## Codex Round 2 raised issues (Planner 검토 대상)

### A. Process / workflow 위반
- A1. verify.md V2가 self-score 87을 PASS_CANDIDATE으로 라벨 — WORKFLOW.md는 ≥95만 허용. **Worker 인정**: V2 작성 시 정직한 87로 깎되 라벨링을 잘못함. Planner 판단: (a) 87 → RE-CODE (workflow 엄격) 또는 (b) 87은 사실상 PASS이고 라벨링 버그만 fix로 충분.
- A2. `5-A`에서 `ruff format --check` 미실행 (pre-commit hook이 auto-fix하지만 explicit check 별도 evidence 필요). Worker fix 가능: 한 줄 명령 추가.
- A3. `5-A`에서 `pytest -m "not llm and not slow"` (WORKFLOW spec) 대신 `pytest -q --no-cov` 사용. Worker fix 가능: 명령 재실행.

### B. Test / evidence rigor
- B1. RAG latency benchmark 가 `/explain`을 라벨에 쓰지만 실제는 `get_or_encode_block_vector()` helper만 측정. Worker 인정: docstring + 라벨 부정확. 단 `tests/integration/test_api_messages.py::test_explain_reuses_stored_vector_no_encode_call` (R1)이 end-to-end 동작 (encode 호출 부재) 검증. Planner 판단: (a) benchmark를 end-to-end로 다시 작성 또는 (b) docstring 수정 + integration test로 충분.
- B2. Future-leak test가 `warnings.catch_warnings`만 캡처. 실제는 event loop exception handler 경로. Worker fix 가능: custom event loop handler attach 또는 caplog 사용.

### C. Product / scope
- C1. ROADMAP DoD §C (DB batch commit safety) 미구현. 사용자 prompt가 명시적으로 skip 결정 + verify에서 contention 부재 evidence. Planner 판단: ROADMAP §C 항목 (a) 본 phase 외 별도 phase 분리, (b) ROADMAP V7에서 §C 삭제, (c) RE-CODE로 구현.
- C2. RAG latency benchmark가 mock LLM 기반. 실 sglang 환경 throughput 측정 부재. ROADMAP "≥ 100 b/min at concurrency 7"는 이론 정합 (7 / 2.62s × 60 = 160 b/min)으로 추정. Planner 판단: live LLM 측정 필요 여부.

## Recommended next (Planner 결정 항목)

### 즉시 (push 전)
1. **process 위반 정리** (A1/A2/A3): verify.md V2 V3로 정정 (87을 PASS_CANDIDATE 라벨 제거 + 별도 정직한 verdict 형식 + workflow-spec 명령 결과 추가). 가능하면 verify.md V3 후 push.
2. **benchmark docstring fix** (B1): `rag_latency_benchmark.py:1-7` "/blocks/{id}/related" → "get_or_encode_block_vector helper" 수정. 라벨/주석만 변경.

### Planner 결정
3. **ROADMAP §C 처리** (C1): 별도 phase 분리 vs 본 phase RE-CODE vs ROADMAP V7 수정.
4. **`/explain` end-to-end latency benchmark** (B1 보강): live API + counting client로 실제 route latency 측정 여부.
5. **future-leak test 강화** (B2): event loop handler 기반으로 다시 작성 여부.

### 일반 follow-up (push 후 또는 별도)
6. doc 6 / 7 (Murphy PML 36K) 강제 retranslate trigger — concurrency=7로 18h → ~5h 예상.
7. Phase 7a-3 (CLI auto-embed 영구화) — Phase 7a debt + Phase 7a-2 v1.6 마일스톤 완료.
8. WAL mode 활성화 (별도 phase) — concurrent reader/writer 성능 향상.

## Evidence index

- plan: `.claude/phases/phase-7a-2/plan.md` (V1 → V2)
- debate: `.claude/phases/phase-7a-2/debate.md` (Codex 6 critiques)
- challenge: `.claude/phases/phase-7a-2/challenge.md` (5/6 ACCEPT, 1/6 REJECT, decision RE-PLAN)
- verify: `.claude/phases/phase-7a-2/verify.md` (V2, self 87/100, process 위반 인정)
- verify-cross: `.claude/phases/phase-7a-2/verify-cross.md` (R1 DOWNGRADE → RE-CODE → R2 DOWNGRADE → escalate)
- benchmarks: `.claude/phases/phase-7a-2/benchmarks/{throughput,rag_latency}_benchmark.py`
- git log: `1856b6f → 06e5085` (12 commits in this phase)

## Known issues / debt

- ROADMAP §C tension (Planner 판단 대기).
- Live LLM throughput 측정 부재 (mock 기반 5.66x speedup만 측정).
- benchmark docstring labeling fix 필요 (B1).
- future-leak test 강화 가능 (B2).

## Push 정책

CLAUDE.md WORKFLOW: "Round 2 REJECT/DOWNGRADE → push 보류, Planner escalate". **Push 보류 ✅**. Human이 위 결정 항목 (1-5) 정리 후 진행.
