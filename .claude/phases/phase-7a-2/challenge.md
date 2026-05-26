# Phase 7a-2 — Challenge (Worker response to Codex debate)

## Summary decision: **RE-PLAN**

Codex가 plan의 fundamental assumption 5개를 정확히 지적했다. 그 중 3개는 plan을 잘못된 방향으로 끌고 가는 critical issue. 1개는 plan 단계 fact error. 1개는 over-engineering. Sub-goal B는 Codex Alternative 1로 전면 교체 (stored vector reuse). Sub-goal A는 dedup race + AsyncSession 동시성 문제 해결을 위해 구조 변경.

Codex 비판 6개 중 **5개 수용 + 1개 부분 반박**. plan.md를 V2로 다시 쓴다.

---

## Debate responses

### 1. Over-engineering

#### §1.1 stats race 회피 (outcome enum reshape) — **REJECT (반박)**
- Codex 주장: `stats.translated += 1`은 read-modify-write가 단일 expression이라 await 사이 race 없음.
- 확인: `_process_block` 안에서 `stats.translated += 1` 은 항상 `await session.commit()` **이전 또는 이후** 단일 줄. 두 task가 동시에 `stats.translated += 1` 을 evaluate할 수는 없음 (asyncio 단일 thread, `+=` 자체는 await 없음).
- **결론**: plan V2에서 outcome-enum reshape 제거. `_process_block`은 기존처럼 `stats` mutate 유지. signature 변경 최소화 (sem 인자만 제거).

#### §1.2 LRU service-wide too broad — **ACCEPT (B 전면 교체)**
- Codex 주장: 측정된 hotspot은 `chat_context._build_cross_doc_refs` + `routers/blocks.related_blocks` 두 곳뿐. `BgeM3Client.encode()` 전체에 cache 추가는 측정되지 않은 범위.
- 확인: 두 hotspot 모두 `block_id` 에서 시작 → `block.original_text` → `encode([text])`. 하지만 **block_embeddings 테이블에 이미 그 block의 벡터가 있다** (Phase 7a 결과물). Cold encode가 불필요.
- **결론**: Sub-goal B를 Codex Alternative §4 "stop re-encoding blocks you already embedded" 로 교체. `block_embeddings.vector` lookup → fallback to `encode()` when missing. LRU cache는 plan V2에서 제거.
- 효과: cold + warm 모두 ~1ms (DB lookup) 로 수렴. DoD `<500ms` cold-include 충족 가능.

#### §1.3 Sub-goal C가 ROADMAP DoD에 있음 — **PARTIAL**
- Codex 주장: 사용자가 "Skip C — measure first" 결정했지만 ROADMAP DoD는 "DB batch commit 안전 (실패 시 rollback)" 명시. plan이 DoD를 임의로 축소.
- 확인: ROADMAP.md:268 "DB batch commit 안전 (실패 시 rollback)" 명시. 사용자 prompt §결정 C "Skip C — measure first" 와 충돌.
- **결정**: 사용자 prompt가 ROADMAP보다 우선 (사용자가 phase prompt에서 명시적으로 C skip). 단 plan V2의 DoD mapping 표에 "DoD 조정: ROADMAP §C는 사용자 결정으로 보류, verify에서 contention 측정 시 별도 phase로 분리" 명시. summary.md에서 ROADMAP 업데이트 권장 항목으로 사용자에게 보고.

### 2. Hidden assumptions

#### §2.1 AsyncSession concurrent share unsafe — **ACCEPT (critical)**
- Codex 인용: SQLAlchemy 공식 docs "concurrent tasks should use a separate AsyncSession per task". https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html#using-asyncsession-with-concurrent-tasks
- 확인: plan V1 의 핵심 가정 ("SQLAlchemy 가 connection-level lock으로 serialize") 은 기술적으로 동작할 수 있으나 공식적으로 unsafe. 향후 SQLAlchemy 또는 DB driver 변경 시 깨질 가능성.
- **결론 — plan V2 architecture**: LLM call과 DB ops 분리.
  - `bounded(block)` task는 `async with sem: text = await llm.translate(...)` 만 수행 (no DB).
  - DB ops는 `async with db_lock:` 으로 직렬화. **단일 session 위에서 lock 으로 mutual exclusion** — SQLAlchemy AsyncSession을 "동시 사용" 하지 않는다 (한 시점에 한 task만 session method 호출).
  - Dedup: `pending_futures: dict[str, asyncio.Future[str]]` 로 in-flight LLM call 공유. 동일 text 두 block은 첫 task가 future set, 둘째는 future await.
  - Per-task session 대신 lock 방식 채택 이유: ① SQLite는 process-level single writer라 connection 늘려도 throughput 안 늘어남. ② lock + 단일 session은 caller (cli/jobs) API 변경 최소. ③ "한 시점에 한 task만 session 사용" 이 사실상 per-task session과 동일한 안전성.

#### §2.2 WAL false claim — **ACCEPT**
- 확인: `src/ht_lens/db/session.py` 가 `PRAGMA foreign_keys=ON` 만 적용, WAL 미설정. docstring 명시.
- **결론**: plan V2에서 WAL 언급 제거. SQLite default journal mode (DELETE) 에서 single-writer. §2.1 architecture는 SQLite mode와 무관하게 safe.

#### §2.3 DoD warm-only 해석 — **ACCEPT**
- Codex 주장: ROADMAP / API 모두 warm-only 근거 없음. first-click cold encode 575ms.
- **결론**: §1.2 stored vector reuse가 cold도 fix. DoD `<500ms` cold-include 측정. warm-only 의존 안 함.

#### §2.4 batch encode 테스트 오류 — **ACCEPT**
- Codex 주장: `BgeM3Client.encode()` 는 batch-oriented 단일 backend call.
- 확인: `service.py:74-84`. 단일 `self._model.encode(...)` call.
- **결론**: §1.2로 LRU cache 자체 제거되어 무관. plan V2 테스트는 stored vector reuse 기준.

### 3. Edge cases

#### §3.1 Duplicate-text dedup race — **ACCEPT (critical)**
- Codex 인용: `tests/integration/test_translate_pipeline_mock.py::test_translate_deduplicates_duplicate_blocks_in_memory` (line 167) 가 `call_count == 1`, `stats.cached == 1` 검증. 병렬화 시 `pending_cache` sequential miss → 두 LLM call → 회귀.
- 확인: 테스트 코드 직접 읽음. 회귀 risk 실제.
- **결론**: §2.1 architecture의 `pending_futures: dict[str, asyncio.Future]` 가 dedup 보장. plan V2 §Approach 흐름:
  - Lock 안에서 cache check → miss이면 `pending_futures[ck] = future` 등록 후 lock 해제 → LLM call → future set → lock 안에서 `pending_cache` update.
  - 같은 ck로 두 번째 들어오는 task는 lock 안에서 future 발견 → lock 해제 후 `await future` → 그 결과로 cached path.

#### §3.2 Cancellation mid-run undefined status — **ACCEPT (정책 정의)**
- Codex 주장: cancelled run은 `Document.status` 미정의. UI/retry 모호.
- **결론**: plan V2에서 명시적 정책. Cancel 시:
  - `_finalize_document_status` 호출 안 함 (기존 동작 유지).
  - `Document.status` 변경 없음 (pre-run state).
  - 부분 commit된 `Translation` rows는 status='translated'로 남음 (next run에서 skip).
  - Retry 시 `--retry-failed` 로 status='failed' 만 재처리.
  - 새 unit test 추가: `test_translate_cancel_mid_run_preserves_state` — N block 진행 중 일부 완료 후 cancel → Document.status unchanged, 완료된 Translation rows status='translated'.

#### §3.3 Retry storm under sem — **ACCEPT**
- Codex 주장: `_translate_with_retry` 의 backoff sleep이 sem 안에서 일어나면 7 slot hold → throughput 붕괴.
- **결론**: plan V2의 `_translate_with_retry` 는 sem 인자 제거 (outer가 hold). 단 backoff sleep을 sem **밖에서** 수행:
  ```python
  for attempt in range(max_retries + 1):
      if attempt > 0:
          await asyncio.sleep(2 ** (attempt - 1))  # outside sem
      try:
          async with sem:
              text = await llm.translate(...)
          return text
      except LLMTransientError:
          continue
  ```
- backoff sleep 동안 sem slot 양보. throughput 안전.

#### §3.4 LRU cache 단일 encode 내부 dedup — **무관 (LRU 제거됨)**

### 4. Alternative approaches

#### §4.1 Stored vector reuse (Sub-goal B 전면 교체) — **ACCEPT**
- 위 §1.2 / §2.3 / §2.4 결합 결론.
- Implementation:
  - `chat_context._build_cross_doc_refs`, `routers/blocks.related_blocks` 두 곳에서 `embedding_client.encode([text])` 호출 직전:
    - `session.get(BlockEmbedding, target.id)` 시도.
    - hit이고 `source_hash == sha256(target.original_text)` 이면 → `vector_from_bytes(row.vector, row.dim)` 사용.
    - miss 또는 stale이면 → 기존 `encode()` 경로 (cold).
  - `source_hash` 검증으로 stale 회피 (사용자가 original_text 수정 시 — 현재 UI 없지만 안전망).
  - 비용: SQLite indexed lookup ~1ms. 대비 575ms.

#### §4.2 Queue + writer 분리 — **PARTIAL**
- §2.1의 lock 방식이 사실상 동일한 효과. queue + writer 는 architecture overhead 더 큼.
- 단 plan V2의 `pending_futures + db_lock` 패턴은 queue + writer의 핵심 idea (LLM concurrency vs DB serialization 분리)를 채택.

#### §4.3 asyncio.TaskGroup over gather — **PARTIAL**
- Python 3.11 baseline 확인 (`requires-python = ">=3.11"`).
- TaskGroup이 cancellation 시 모든 task 자동 cancel + structured concurrency. 단 `as_completed` 와 결합 어려움.
- **결정**: progress callback `[(10, 23), (20, 23), (23, 23)]` 정확한 tick 보존이 필요. `asyncio.as_completed` 가 자연스러움. TaskGroup 부적합.
- 대안: `as_completed` + try-finally로 cancel propagation 보강. 한 task가 unrecoverable exception 던지면 나머지 cancel + raise.

### 5. Missing tests

| Codex 제안 test | plan V2 채택 |
| --------------- | ------------ |
| `test_translate_deduplicates_duplicate_blocks_in_memory_with_concurrency_2` | ✅ 신규 |
| `test_translate_progress_keeps_exact_ticks_under_concurrency` | ✅ 기존 `test_translate_callback_fires_every_10_and_on_last` 패턴으로 `concurrency=4` 변형 추가 |
| File-backed SQLite concurrency test | ✅ pytest `tmp_path` file SQLite fixture |
| `test_related_or_explain_reuses_query_vector_on_repeat` | ✅ API layer counting embedding client. `_build_cross_doc_refs` + `routers/blocks.related_blocks` 두 경로 |
| `test_bge_m3_cache_batches_distinct_misses_once` | ❌ (§1.2 LRU 제거 무관) |
| `test_translate_cancel_mid_run_leaves_explicit_state` | ✅ 신규, §3.2 정책 검증 |

추가 stored-vector-reuse 테스트:
- `test_chat_context_uses_stored_embedding_when_available`
- `test_chat_context_falls_back_to_encode_on_stale_hash`
- `test_chat_context_falls_back_to_encode_when_block_not_embedded`

---

## Plan revisions (after debate)

V1 → V2 변경:
1. **Sub-goal A architecture**: `pending_futures + db_lock` + `as_completed` + sem-outside-sleep retry. AsyncSession 동시 사용 회피.
2. **Sub-goal B 전면 교체**: LRU cache → stored vector reuse (chat_context + routers/blocks 두 곳).
3. **stats mutate 유지** (§1.1 반박).
4. **WAL 언급 제거** (§2.2).
5. **DoD cold-include 해석** (§2.3 + §4.1).
6. **Cancellation 정책 명시** (§3.2).
7. **Retry sleep outside sem** (§3.3).
8. **테스트 6개 추가/변형** (§5).
9. **`as_completed`** + 명시적 cancel cleanup (§4.3, progress contract 보존).
10. **ROADMAP §C tension 명시** in DoD mapping, summary 보고 (§1.3).

## DoD checklist (V2 기준)

| DoD item | Status | Evidence |
| -------- | ------ | -------- |
| Translation throughput ≥ 100 b/min @ c=7 | Open | verify benchmark (mock LLM 30 blocks c=1 vs c=7 ≥ 5x) |
| `/explain` p95 < 500ms (cold-include) | Open | stored vector reuse 후 측정 — 1ms DB lookup |
| 회귀 0 (508 tests) | Open | pytest |
| `--concurrency` 진짜 동작 | Open | unit test (parallel time + c=1 sequential) |
| Dedup 회귀 0 | Open | 기존 test + 신규 c=2 variant |
| Progress callback contract | Open | 기존 `[(10,23),(20,23),(23,23)]` test + concurrency variant |
| Cancellation 정책 | Open | 신규 test |
| DB batch commit (ROADMAP §C) | **Deferred per 결정 C** | verify에서 SQLITE_BUSY 부재 확인 후 skip 확정. summary에서 사용자에게 ROADMAP 업데이트 권장 |

## Risk register

| Risk | Likelihood | Impact | Mitigation |
| ---- | ---------- | ------ | ---------- |
| AsyncSession concurrent 사용 (V1 hazard) | Eliminated | High | db_lock으로 단일 task만 session 접근 |
| Dedup race (parallel duplicate text) | Eliminated | High | pending_futures dedup |
| SQLITE_BUSY under file SQLite | Low | Medium | single session + lock → write 항상 serial, no concurrent writers |
| Cancellation leaves bad state | Low | Low | explicit policy: Document.status unchanged, Translation rows committed remain |
| Retry sleep blocks sem | Eliminated | Medium | sleep outside sem |
| Stored embedding stale (source text mutated) | Very Low | Low | source_hash check → fallback to encode |
| LLM throughput cap by sglang effective_max=7 | Known | N/A | concurrency=7 default 정합 |
| Progress callback 중복 emit | Eliminated | Low | as_completed 단일 counter |
| TaskGroup 미사용 (Codex preferred) | Low | Low | as_completed + 명시적 cleanup으로 동등 안전성 |

## Decision
- [x] PASS → proceed to RE-PLAN (V2) → code
- [ ] RE-PLAN (reason: ) — **선택**: V1 → V2 재작성

다음 단계: plan.md V2 재작성 (별도 file로 history 보존 안 함, git history가 추적) → commit `chore(phase-7a-2): plan v2` → Stage 4 코드 진입.
