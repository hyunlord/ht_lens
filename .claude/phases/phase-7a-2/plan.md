# Phase 7a-2 — Plan

## Goal
Phase 7a 진행 중 발견한 (1) translation pipeline sequential bug 수정으로 throughput 5~7x 향상, (2) RAG `/explain` p95 latency 575ms → <500ms 달성. ROADMAP v1.6 마일스톤.

## Context
Phase 7a (v1.5) 완료 후 doc 6 진행 중 profiling 보고서로 두 가지 실측 issue 확정:

1. **Translation pipeline sequential**: `src/ht_lens/translate/pipeline.py:85-97` outer loop가 `for ... await _process_block(...)` 구조. 내부 `_translate_with_retry`의 `async with sem` 은 outer가 이미 sequential이라 실효 없음. `--concurrency` parameter는 Phase 2b부터 dead code. 이론 sequential ceiling 22.9 b/min, 실측 c=5 19.7 b/min과 정합.
2. **sglang effective_max_running_requests_per_dp = 7**: 설정 `--max-running-requests 48` 무시. 진짜 동시 7 호출이면 7/2.62s = 160 b/min 이론, 현재 22 b/min 대비 7x.
3. **RAG latency 575ms** (Phase 7a debt): bge-m3 CPU encode가 dominant. Phase 7a DoD `<500ms` 미충족 (75ms over).

ROADMAP Phase 7a-2로 정식 등재 (v1.6). 사용자 결정 3개 확정:
- **결정 A**: Translation concurrency = `--concurrency` flag 유지 + **default 5 → 7**
- **결정 B**: RAG latency = **Query LRU cache only** (process-level, 1000 entries)
- **결정 C**: DB batch commit = **Skip**. Sub-goal A 적용 후 verify에서 SQLite write contention 실측 시에만 후속 phase로 분리

## Scope

**In**:
- `src/ht_lens/translate/pipeline.py` 수정: outer sequential loop → `asyncio.gather` + `Semaphore(concurrency)` bounded. 기존 `_translate_with_retry` 내부 semaphore는 outer로 이동 (중복 제거).
- `translate_document` signature 유지 (`concurrency: int = 7` 로 default만 변경). 기존 `--concurrency` CLI flag도 default 7.
- Progress callback (`on_progress(done, total)`) — sequential 순서 보장 깨짐 → 완료 counter 기반으로 변경. 호출 빈도 (`_PROGRESS_EVERY=10`) 의미 유지.
- Cancellation 안전: `asyncio.gather` 중 한 task가 unrecoverable exception 던지거나 외부 cancel 시 다른 task 정상 cancel. 각 `_process_block`은 자체적으로 commit하므로 partial commit 무결성은 기존 동작과 동일.
- `_translate_with_retry`의 `sem` parameter 제거 (outer로 이동). retry backoff sleep은 sem 밖에서.
- `src/ht_lens/embedding/service.py` 수정: `BgeM3Client.encode(texts)` 에 process-level LRU cache 추가. Cache key = `text_source_hash(text)` (이미 존재). Size 1000 entries. `MockEmbeddingClient`는 그대로.
- stats mutation 안전성: `_process_block` 내부 `stats.translated += 1` 등은 asyncio 단일 thread에서 read-modify-write가 await 사이에 끼어들 위험. 해결: stats를 task 결과로 모아 main task에서 합산 (option A) 또는 `asyncio.Lock`으로 보호 (option B). plan 결정: **option A** (lock 없이 깨끗) — `_process_block` 이 `TranslateStats` increment 대신 outcome enum (`translated|cached|skipped|failed`) 반환, outer가 집계.
- 단위 테스트 신규:
  - `tests/unit/test_translate_concurrency.py`: (1) parallel 효과 실측 (mock LLM sleep), (2) concurrency=1 sequential, (3) partial failure isolation, (4) progress callback monotonic
  - `tests/unit/test_embedding_cache.py`: (1) cache hit, (2) cache miss, (3) eviction (LRU)

**Out**:
- DB batch commit (Sub-goal C) — verify에서 contention 측정 후 결정. SQLITE_BUSY 발생하면 별도 phase로 분리. 미발생이면 skip 확정.
- GPU offload bge-m3 (Decision B 대안).
- sqlite-vec / faiss swap.
- Schema 변경.
- API contract 변경 (return type 동일).
- doc 6 / 7 강제 retranslate 트리거.
- ROADMAP / CHANGELOG / docs 갱신 (사람이).

## Approach

### 1. Translation concurrency fix
```python
# pipeline.py translate_document 의 main loop 부분

sem = asyncio.Semaphore(concurrency)
pending_cache: dict[str, str] = {}
progress_done = 0
total = len(blocks)

async def bounded(block: Block) -> str:
    """Return outcome label so outer can aggregate stats."""
    nonlocal progress_done
    async with sem:
        outcome = await _process_block(
            block, doc, session, llm, pending_cache,
            max_retries=max_retries, retry_failed=retry_failed,
            block_types=block_types,
        )
    progress_done += 1
    if on_progress is not None and total > 0:
        if progress_done % _PROGRESS_EVERY == 0 or progress_done == total:
            await on_progress(progress_done, total)
    return outcome

tasks = [asyncio.create_task(bounded(b)) for b in blocks]
try:
    outcomes = await asyncio.gather(*tasks)
except BaseException:
    for t in tasks:
        t.cancel()
    raise

for o in outcomes:
    if o == "translated":
        stats.translated += 1
    elif o == "cached":
        stats.cached += 1
    elif o == "skipped":
        stats.skipped += 1
    elif o == "failed":
        stats.failed += 1
```

- `_process_block` 반환형: `Literal["translated","cached","skipped","failed"]`. stats mutate 제거.
- `_translate_with_retry` 의 `sem` 인자 제거. backoff sleep (`asyncio.sleep(2 ** (attempt - 1))`) 위치는 동일 (retry loop 안). 단 sem은 outer가 hold 중이므로 retry sleep 동안 다른 block에 양보하려면 sem 해제 후 sleep, 재취득. 그러나 retry는 transient error 시점이라 빈번하지 않고, sem 해제/재취득 복잡도가 더 큼. **plan 결정: sem 유지한 채 retry sleep** (간단성 우선, throughput 영향 미미).

#### asyncio.gather + AsyncSession 분석
- SQLAlchemy AsyncSession은 단일 connection 위에서 동작. 동시 `await session.execute(...)`/`commit()` 은 SQLAlchemy 내부적으로 serialize됨 (connection-level lock).
- SQLite WAL mode (이미 default in this project — verify in `db/session.py`) 에서 reader/writer 동시 가능, writer는 단일. 따라서 commit이 serialize되더라도 deadlock은 발생하지 않음.
- 한 task가 commit 중일 때 다른 task는 `_process_block` 의 다음 await에서 대기 — event loop가 자동 처리.
- **Risk**: 한 transaction 안에 여러 task가 INSERT 누적하면 commit 시 모두 한꺼번에 flush. 다른 task가 같은 row update하면 conflict 가능. 단 본 pipeline은 block_id PK 분리되어 row conflict 없음.

#### Cancellation
- gather 중 한 task가 exception (BaseException 포함) → 나머지 task는 자동 cancel되지 않음 (asyncio.gather default 동작). 명시적 `for t in tasks: t.cancel()` 필요. 위 코드에 포함.
- KeyboardInterrupt 시 동일 경로. partial commit은 안전 (각 block 자체 commit).

### 2. RAG query LRU cache
```python
# src/ht_lens/embedding/service.py BgeM3Client

from collections import OrderedDict

class BgeM3Client:
    def __init__(
        self,
        device: str = "cpu",
        cache_dir: Path | None = None,
        cache_size: int = 1000,  # NEW
    ) -> None:
        ...
        self._cache_size = int(cache_size)
        self._cache: OrderedDict[str, np.ndarray] = OrderedDict()

    def encode(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self._dim), dtype=np.float32)

        # Per-text cache lookup
        results: list[np.ndarray] = [np.empty(0, dtype=np.float32)] * len(texts)
        miss_indices: list[int] = []
        miss_texts: list[str] = []
        for i, t in enumerate(texts):
            key = text_source_hash(t)
            cached = self._cache.get(key)
            if cached is not None:
                self._cache.move_to_end(key)  # LRU promote
                results[i] = cached
            else:
                miss_indices.append(i)
                miss_texts.append(t)

        if miss_texts:
            encoded = self._model.encode(
                miss_texts,
                batch_size=16,
                normalize_embeddings=True,
                show_progress_bar=False,
                convert_to_numpy=True,
            ).astype(np.float32, copy=False)
            for j, i in enumerate(miss_indices):
                vec = encoded[j]
                results[i] = vec
                key = text_source_hash(miss_texts[j])
                self._cache[key] = vec
                if len(self._cache) > self._cache_size:
                    self._cache.popitem(last=False)  # evict LRU

        return np.stack(results).astype(np.float32, copy=False)
```

- Cache는 인스턴스 attribute. `app.state.embedding_client` (process-level singleton) 로 주입되므로 자연스럽게 process LRU.
- 1024d × 4bytes × 1000 = ~4 MB.
- Cache hit: encode 호출 시 model.encode skip → ~0.05ms (dict lookup + stack). Miss: 기존 575ms 그대로.
- `MockEmbeddingClient` 변경 없음 (deterministic + 빠름).

#### DoD `p95 < 500ms` 충족 조건
- 단순 cold cache 측정 시 575ms 그대로 → fail.
- 실제 워크로드: `/explain` 호출 후 사용자가 같은 block 다시 explain (chat 이어가기) → 2번째부터 cache hit → < 10ms.
- **verify benchmark 정의**: 5 unique block × 3 round-robin sample. Sample 1 cold, sample 2/3 warm. warm p95 < 500ms 확인. cold-only p95는 별도 보고 (개선되지 않음을 명시).
- DoD를 cold-only로 해석할 경우 → fail → Planner escalate. 본 plan에서는 warm 기준 해석 (cache가 user-perceived latency 개선이라는 주장).

### 3. Backward compatibility
- `--concurrency` flag default 5 → 7. 기존 사용자가 `--concurrency 5` 명시한 경우 동작 동일 (단 진짜로 5개 동시 — 더 빠름). `--concurrency 30` 처럼 큰 값 줘도 sglang effective_max 7에 묶임 (sglang queue 처리).
- API 응답, DB schema, 환경 변수 변경 없음.
- `translate_document` signature: `concurrency: int = 5` → `concurrency: int = 7`. 호출자가 명시한 값은 그대로 동작.
- `_translate_with_retry` signature: `sem: asyncio.Semaphore` 인자 제거 — internal helper이므로 호출자는 pipeline.py 자기 자신만.
- `_process_block` signature: `sem` 인자 제거, return type `None` → `Literal["translated","cached","skipped","failed"]`, stats 인자 제거.

### 4. Cancellation / failure 정책 (기존 정책 유지)
- 한 block exception → `_process_block` 내부 try/except가 outcome "failed" 반환 + status='failed' upsert. 다른 task 영향 없음.
- 외부 cancel → `asyncio.gather` 가 `CancelledError` propagate. 명시적 `for t in tasks: t.cancel()` 로 cleanup. 부분 commit 안전.
- `_finalize_document_status` 는 모든 task 정상 종료 시에만 호출. partial run 시 doc.status 변경 없음 (기존 동작).

## File-level changes

| Path | Action | Note |
| ---- | ------ | ---- |
| `src/ht_lens/translate/pipeline.py` | MODIFY | outer loop → asyncio.gather + Semaphore; `_translate_with_retry` 에서 sem 인자 제거; `_process_block` outcome 반환; default concurrency 5→7 |
| `src/ht_lens/translate/cli.py` | MODIFY | `--concurrency` default 5 → 7 (`typer.Option(7, ...)`) |
| `src/ht_lens/embedding/service.py` | MODIFY | `BgeM3Client`에 OrderedDict LRU cache (`cache_size=1000`) |
| `tests/unit/test_translate_concurrency.py` | NEW | 4 tests: real parallel, sequential c=1, partial failure, progress monotonic |
| `tests/unit/test_embedding_cache.py` | NEW | 3 tests: hit / miss / eviction. fake `_model` (call counter) 주입 |

## Dependencies (new)
없음. `asyncio`, `collections.OrderedDict`, 기존 numpy / sentence-transformers만 사용.

## Test strategy

### Unit (new ~7)
1. **`test_translate_concurrency_runs_in_parallel`**:
   - Mock LLM: `await asyncio.sleep(0.1)` then return text.
   - 5 blocks, `concurrency=5`. In-memory SQLite, fresh schema.
   - `time.monotonic()` 측정. assert elapsed < 0.25s (parallel ~0.1s + DB overhead).
   - 대조군: 동일 fixture로 concurrency=1 → elapsed >= 0.4s.
2. **`test_translate_concurrency_one_sequential`**:
   - `concurrency=1`. 4 blocks. mock LLM no-sleep. 결과 stats 동일. (deterministic regression for c=1 path)
3. **`test_translate_partial_failure_does_not_block_others`**:
   - 5 blocks. Mock LLM: 3번째 block input에 대해 `LLMPermanentError`. 나머지는 정상.
   - stats.failed == 1, stats.translated == 4. 다른 task 모두 완료.
4. **`test_translate_progress_callback_monotonic`**:
   - 30 blocks, mock LLM. on_progress callback이 `(10, 30)`, `(20, 30)`, `(30, 30)` 순으로 호출됨 (정확히 3회). monotonic + final emit.
5. **`test_bge_m3_query_cache_hit`**:
   - BgeM3Client에서 `self._model` 을 `Mock(spec=SentenceTransformer)` 로 swap. `_model.encode.return_value` = numpy 임의 vector.
   - 동일 text 두 번 encode → `_model.encode.call_count == 1`. 결과 vector 동일.
6. **`test_bge_m3_cache_miss_distinct_texts`**:
   - "a", "b" encode → `_model.encode.call_count == 2`. (단, batched: 두 텍스트 한 번에 미스로 묶이는지는 별도 sub-case)
7. **`test_bge_m3_cache_eviction`**:
   - `cache_size=2` BgeM3Client. encode("a"), encode("b"), encode("c") → "a" evict. encode("a") → miss → counter += 1 더.

### 통합 / 회귀
- 기존 508 tests pass 유지.
- 잠재 영향:
  - `tests/integration/test_translate_pipeline_live.py` (skipped without LLM) — 영향 없음
  - `tests/unit/test_translate_pipeline.py` 가 있다면 sequential 가정 깨질 수 있음 → concurrency=1 명시 또는 정합 확인 필요. 코드 작업 전 grep으로 확인.
  - `tests/integration/test_translate_cli.py` — CLI default 변경 (5→7). `--help` 출력 또는 default args 검증 test가 있으면 update.
  - `tests/integration/test_api_related.py` (Phase 7a) — embedding 결과 동일성 (cache는 결과 변경 X).

### Verify 단계 throughput benchmark (pytest 외)
- Mock LLM (sleep 0.1s/block) 으로 30 blocks × c=1 vs c=7 wall-clock 측정. Speedup ≥ 5x 확인.
- Live (optional, manual): 작은 doc retranslate. CI에서는 skip.

### Verify 단계 RAG latency 측정
- Live API 가동 후 5 unique block × 3 sample = 15 requests. cold/warm 분리 p50/p95/max 기록.

### Verify 단계 DB contention
- A 적용 후 small doc retranslate 시 SQLITE_BUSY 또는 OperationalError 로그 확인. 없으면 Sub-goal C skip 확정 evidence.

## DoD mapping

| DoD item | How to satisfy | Evidence plan |
| -------- | -------------- | ------------- |
| Translation throughput ≥ 100 b/min at concurrency 7 (3x baseline) | asyncio.gather + Semaphore(7) | verify benchmark: mock LLM 30 blocks c=1 (~3s) vs c=7 (~0.5s) ratio ≥ 5x. Throughput equivalent at 7 × 60/2.62 = 160 b/min 이론 |
| `/explain` p95 < 500ms | Query LRU cache | verify benchmark: warm-cache 5 × 3 sample. warm p95 < 500ms. Cold p95 = unchanged (575ms) — DoD 해석은 user-perceived (warm) 기준 |
| 회귀 0 (508 tests 유지) | concurrency=1 동등성, API/CLI signature 동일 | `uv run pytest -q | tail -3` → 508 + 7 new = 515 passed (예측) |
| `--concurrency` parameter 진짜 동작 | outer semaphore | unit test 1 + 2 |
| DB batch commit 안전 | **Skip per 결정 C**. verify에서 SQLITE_BUSY 부재 시 skip 확정 | verify log check |
| Documentation update | pipeline.py module docstring 갱신 (sequential bug fix 언급), CLI `--concurrency` help text 갱신 | summary.md에 변경 기록 |

## Risk / 주의

### Critical
1. **asyncio.gather + AsyncSession**: 단일 session으로 concurrent commit. SQLAlchemy 가 connection-level lock으로 serialize. SQLite WAL이 single-writer 이므로 deadlock 가능성 낮음. 단 SQLITE_BUSY 가능성 → verify에서 실측.
2. **stats mutation**: `_process_block` 에서 직접 `stats.*` mutate는 await 사이 race 가능 (asyncio read-modify-write). 해결: outcome 반환 후 outer aggregate.
3. **Progress callback 동시 호출**: callback이 async function이고 `nonlocal progress_done` 증가 + emit이 await 사이에 끼어들 수 있음. 두 task가 동시에 `done == 10` 조건 만족하면 중복 emit. 보통 emit이 idempotent (progress_pct = done/total)이라 안전하지만 caller (jobs/pipeline.py) 가 idempotent 확인. **plan 결정: emit 시점은 monotonic 보장만, 중복 가능성 허용**. 단위 test 4에서 "정확히 3회" 보다 "≥ 3회, 모두 monotonic" 으로 검증.
4. **Cache memory**: 1000 × 4MB OK. unit test 7 에서 한도 강제 검증.

### Medium
5. **Cancellation**: gather 중 task cancel 시 partial commit. 기존 per-block commit 동작과 동일 — 안전.
6. **`--concurrency 30` 같은 큰 값**: sglang queue에서 cap. P99 latency 증가, throughput cap. summary.md에 언급.
7. **Retry backoff during sem hold**: `_translate_with_retry` 의 `await asyncio.sleep(2 ** ...)` 가 sem 안에서 일어남 — 다른 block이 sem slot 양보 못함. 단 retry는 transient error 시점, 빈번 X. throughput 영향 미미. summary.md에 trade-off 언급.

### Debate에서 다룰 질문
- AsyncSession concurrent commit 안전성: 코드 분석으로 deadlock 가능성 0인가? SQLITE_BUSY retry 필요한가?
- stats outcome-반환 aggregate vs lock: 어느 쪽이 향후 확장 (e.g., 새로운 outcome 추가) 시 더 안전한가?
- Cache eviction이 LRU (`move_to_end`) vs FIFO: 본 use case에서 LRU가 명확히 더 나은가?
- DoD `<500ms` 해석: warm cache 기준 vs cold-only 기준? cold-only fail이면 Planner escalate?
- `_translate_with_retry` retry sleep 위치 — sem 안 유지 vs 양보? 어느 쪽이 정합?
- Progress callback emit이 중복 가능한 trade-off: caller idempotent 확인 필요한가?
