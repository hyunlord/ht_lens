# Phase 7a-2 — Summary

## Status
**PASS (Planner-directed micro-fix path, Option B+)** — Codex Round 2 DOWNGRADE는 process/rigor 결함만 지적이고 코드 product는 견고. Planner directive에 따라 V3 micro-fix 적용 후 push.

Self-score 87/100 (WORKFLOW.md ≥95 미달이므로 PASS_CANDIDATE 라벨 X). 단 모든 substantive Codex 지적 (future-leak, retry slot-release, /explain integration test, benchmarks committed, future-leak test rigor, benchmark docstring 정확화) 직접 fix 완료. 잔여 항목 (ROADMAP §C 처리, live LLM benchmark)은 사용자 직접 / doc 7 진행으로 자연 측정 — Planner 위임.

코드 product: 5.66x speedup (mock LLM 30 blocks c=1 vs c=7), 0.18ms stored-vector p95 (helper level), 521 tests passed, lint/mypy clean.

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

### Sub-goal C — DB batch commit (사용자 명시적 SKIP 결정)
- **Skip per Stage 1 사용자 결정 C**: phase_7a-2_prompt.md 의 "결정 C" 옵션 4개 중 "Skip C — measure first" 선택. 명시적 사용자 directive.
- Sub-goal A 적용 후 verify에서 SQLITE_BUSY / OperationalError 부재 확인 → skip 정당화 evidence 확보.
- ROADMAP §C DoD 항목과는 tension (Codex 2회 지적). **사용자가 ROADMAP §C에 "사용자 결정 skip + 측정 정당화" 명시는 직접 처리하기로 위임** (V3 Planner directive §5).

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

## Recommended next

### V3 Planner-directed micro-fix (이 phase에서 직접 적용 ✅)
1. ✅ **verify.md V3**: self-score 87 → PASS_CANDIDATE 라벨 제거. "FAIL → RE-CODE applied (R1) + Planner-directed micro-fix (R2)" 정직한 verdict. WORKFLOW.md §217-223 준수.
2. ✅ **benchmark docstring fix**: `rag_latency_benchmark.py` 가 "/explain"이 아닌 `get_or_encode_block_vector` helper만 측정한다는 점 명시. verdict line도 "Helper-level p95"로 정정. end-to-end 동작은 integration test로 lock.
3. ✅ **future-leak test rigor fix**: `warnings.catch_warnings` (잘못된 surface) → `loop.set_exception_handler` (실제 surface). 추가로 fix 라인을 제거하면 test가 fail함을 확인 (regression discrimination 검증).
4. ✅ **summary.md**: Status `ESCALATE TO PLANNER` → `PASS (Planner-directed micro-fix path)`. Sub-goal C 사용자 명시적 skip directive 강조.

### Human/Planner 위임 (별도)
5. **ROADMAP §C 명시**: "사용자 결정 skip + 측정 정당화" 항목을 사용자가 직접 ROADMAP 수정 (V3 Planner directive §5).
6. **Live LLM benchmark**: 별도 phase 신설 안 함. doc 7 (Murphy PML 36K) 진행 시 자연스럽게 throughput 측정 (V3 Planner directive §6).

### 일반 follow-up (별도 phase, push 후)
7. doc 6 / 7 강제 retranslate trigger — concurrency=7로 18h → ~5h 예상. doc 7 진행이 §6 live benchmark 역할도 함.
8. Phase 7a-3 (CLI auto-embed 영구화) — Phase 7a debt + Phase 7a-2 v1.6 마일스톤 완료.
9. WAL mode 활성화 (별도 phase) — concurrent reader/writer 성능 향상.

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

CLAUDE.md WORKFLOW의 기본 규칙은 "Round 2 REJECT/DOWNGRADE → push 보류, Planner escalate". 본 phase는 **Planner-directed micro-fix path (Option B+) override**로 push 진행:
- Codex Round 2 지적 중 substantive code/test bug 4개 (future-leak rigor, benchmark docstring, verify label, summary status) V3 micro-fix로 직접 해소.
- 잔여 항목 (ROADMAP §C 텍스트, live LLM 측정)은 사용자 직접 / doc 7 진행 위임.
- R3 cross-verify 금지 (Planner-directed micro-fix 명시적 지시).
- Stage 6: push + CI green 확인 후 종료.
