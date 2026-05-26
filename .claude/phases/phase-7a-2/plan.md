# Phase 7a-2 — Plan (V2, post Codex debate)

> **V1 → V2 changelog**: AsyncSession concurrent-share hazard (db_lock + pending_futures), dedup race fix, retry sleep outside sem, Sub-goal B 전면 교체 (LRU cache → stored vector reuse), cancellation 정책 명시, WAL false claim 제거, `as_completed`로 progress tick 보존. 자세한 근거는 `challenge.md` 참조. V1 commit history는 git에 보존.

## Goal
Phase 7a 진행 중 발견한 (1) translation pipeline sequential bug 수정으로 throughput 5~7x 향상, (2) RAG `/explain` p95 latency 575ms → <500ms 달성 (cold-include 해석). ROADMAP v1.6 마일스톤.

## Context
Phase 7a (v1.5) 완료 후 doc 6 진행 중 profiling 보고서로 두 가지 issue 확정:

1. **Translation pipeline sequential**: `src/ht_lens/translate/pipeline.py:85-97` outer loop `for ... await _process_block(...)` 구조 → `--concurrency` parameter는 Phase 2b부터 dead code. 실측 sequential ceiling 22.9 b/min.
2. **sglang `effective_max_running_requests_per_dp = 7`**: 진짜 동시 7 호출이면 160 b/min 이론, 현재 22 b/min 대비 7x.
3. **RAG latency 575ms** (Phase 7a debt): bge-m3 CPU encode가 dominant. DoD `<500ms` 미충족.

사용자 결정 3개 (phase prompt):
- **A**: `--concurrency` flag 유지 + default 5 → 7
- **B**: ~~Query LRU cache only~~ → **stored vector reuse** (Codex Alt 1, challenge §1.2 채택)
- **C**: DB batch commit Skip — verify에서 contention 측정 후 결정. ROADMAP DoD §C와 tension은 summary에서 사용자 보고.

## Scope

**In**:

### Sub-goal A — Translation concurrency fix
- `src/ht_lens/translate/pipeline.py`:
  - outer `for ... await` sequential loop → `asyncio.as_completed(tasks)` 기반 fan-out + `Semaphore(concurrency)` LLM-call bounded.
  - **DB ops 직렬화**: `asyncio.Lock()` (`db_lock`) 으로 단일 session 사용을 한 시점에 한 task로 제한. SQLAlchemy 공식 권고 "AsyncSession 동시 사용 금지" 우회 (Codex debate §2.1).
  - **Dedup safety**: `pending_futures: dict[str, asyncio.Future[str]]` — 동일 cache_key에 대한 in-flight LLM call 공유. 동일 text 두 block은 첫 task가 LLM call + future set, 둘째는 future await (Codex debate §3.1).
  - `_translate_with_retry`: `sem` 인자 제거. backoff sleep을 sem **밖에서** (sem slot 양보, Codex debate §3.3).
  - `_process_block`: signature에서 `sem` 제거. `stats` mutate 유지 (Codex debate §1.1 반박 — `+=`는 race 없음).
  - default `concurrency: int = 5 → 7`.
- `src/ht_lens/translate/cli.py`: `--concurrency` default 5 → 7. help text 갱신.
- Progress callback: `asyncio.as_completed` 로 완료 순서대로 counter 증가, 기존 contract `[(10, 23), (20, 23), (23, 23)]` 정확한 tick 유지.
- Cancellation 정책 명시 (Codex debate §3.2):
  - `Document.status` 변경 없음 (pre-run 유지).
  - 부분 commit된 `Translation` rows는 status='translated'로 잔존 (next run에서 skip).
  - `as_completed` loop 중 `BaseException` 발생 시 나머지 tasks `.cancel()` + raise.

### Sub-goal B — RAG latency (stored vector reuse)
- `src/ht_lens/api/chat_context.py::_build_cross_doc_refs` (line 247-269):
  - `embedding_client.encode([text])` 호출 직전:
    - `session.get(BlockEmbedding, target.id)` 시도.
    - hit이고 `source_hash == text_source_hash(target.original_text)` → `vector_from_bytes(row.vector, row.dim)` 사용.
    - miss / stale → 기존 `encode()` fallback.
- `src/ht_lens/api/routers/blocks.py::related_blocks` (line 167-178):
  - 동일 패턴.
- 공통 helper 추출 (가능하면): `src/ht_lens/embedding/lookup.py` (NEW) — `async def get_or_encode_block_vector(session, embedding_client, block) -> np.ndarray`.

### Sub-goal C — DB batch commit
- **Skip per 결정 C**. Sub-goal A 적용 후 verify에서 SQLITE_BUSY 또는 OperationalError 부재 확인. 발생 시 별도 phase 분리.
- summary.md에서 사용자에게 ROADMAP §C tension 보고.

### Tests (신규)
- `tests/unit/test_translate_concurrency.py` (NEW):
  - `test_translate_concurrency_runs_in_parallel`: mock LLM sleep 0.1s × 5 block × c=5. elapsed < 0.25s (parallel). 대조: c=1 elapsed ≥ 0.4s.
  - `test_translate_concurrency_one_sequential`: c=1, 4 blocks, mock LLM. stats + 결과 동등성.
  - `test_translate_partial_failure_does_not_block_others`: 5 block 중 1개 LLMPermanentError raise. 나머지 완료. stats.failed == 1.
  - `test_translate_deduplicates_duplicate_blocks_in_memory_with_concurrency_2`: 동일 text 2개 block × c=2. LLM call_count == 1, stats.cached == 1 (pending_futures 효과).
- `tests/integration/test_translate_progress.py` MODIFY:
  - 기존 `test_translate_callback_fires_every_10_and_on_last` 유지 (c=5 default 5→7 변경 영향 없음, blocks=23이라 ticks 동일).
  - 새 test `test_translate_callback_under_concurrency_4`: 동일 23 blocks × `concurrency=4`. `calls == [(10, 23), (20, 23), (23, 23)]` 동일.
- `tests/unit/test_translate_cancel.py` (NEW):
  - `test_translate_cancel_mid_run_preserves_state`: mock LLM에서 일부 block은 빠르게, 나머지는 무한 await. main task가 `cancel()`. Document.status unchanged. 완료된 Translation rows status='translated'.
- `tests/integration/test_api_related.py` MODIFY (또는 NEW `test_api_related_uses_stored_vector.py`):
  - counting embedding client (`MockEmbeddingClient` subclass with `encode_call_count`). Block에 embedding 미리 저장. `GET /blocks/{id}/related?k=5` 호출 → `encode_call_count == 0`.
  - 동일 fixture에서 source_hash mismatch (block.original_text 수정) → `encode_call_count == 1` (fallback).
  - block_embeddings에 row 없음 → `encode_call_count == 1` (fallback).
- `tests/integration/test_chat_context_rag.py` MODIFY (또는 신규 case):
  - `test_chat_context_uses_stored_embedding_when_available`: embedding 저장된 target block. `_build_cross_doc_refs` 호출 → `encode_call_count == 0`.

**Out**:
- DB batch commit 구현.
- GPU offload bge-m3.
- sqlite-vec / faiss swap.
- Schema 변경.
- API contract 변경.
- WAL 활성화 (별도 작업).
- doc 6 / 7 강제 retranslate.
- ROADMAP / CHANGELOG 갱신 (사람).

## Approach

### 1. Translation concurrency fix — architecture

```python
# src/ht_lens/translate/pipeline.py (V2 핵심 골격)

async def translate_document(
    doc_id: int,
    session: AsyncSession,
    llm: TranslateLLMClient,
    *,
    concurrency: int = 7,  # V1 5 → V2 7
    max_retries: int = 3,
    retry_failed: bool = False,
    block_types: tuple[str, ...] = ("text", "header"),
    dry_run: bool = False,
    on_progress: ProgressCallback | None = None,
) -> TranslateStats:
    await _require_schema_head(session)
    doc = await session.get(Document, doc_id)
    if doc is None:
        raise ValueError(f"document {doc_id} not found")

    rows = await session.execute(...)
    blocks = list(rows.scalars())
    stats = TranslateStats(document_id=doc_id)

    if dry_run:
        return await _dry_run_stats(blocks, doc, session, llm, block_types, stats)

    pending_cache: dict[str, str] = {}
    pending_futures: dict[str, asyncio.Future[str]] = {}
    sem = asyncio.Semaphore(concurrency)
    db_lock = asyncio.Lock()

    async def bounded(block: Block) -> None:
        await _process_block(
            block, doc, session, llm, sem, db_lock,
            pending_cache, pending_futures, stats,
            max_retries=max_retries,
            retry_failed=retry_failed,
            block_types=block_types,
        )

    total = len(blocks)
    tasks = [asyncio.create_task(bounded(b)) for b in blocks]
    done = 0
    try:
        for fut in asyncio.as_completed(tasks):
            await fut  # propagates exceptions if any
            done += 1
            if on_progress is not None and total > 0:
                if done % _PROGRESS_EVERY == 0 or done == total:
                    await on_progress(done, total)
    except BaseException:
        for t in tasks:
            t.cancel()
        # Don't await cancelled tasks here — let asyncio cleanup. Re-raise.
        raise

    await _finalize_document_status(session, doc, stats)
    return stats
```

`_process_block` (V2):
```python
async def _process_block(
    block: Block,
    doc: Document,
    session: AsyncSession,
    llm: TranslateLLMClient,
    sem: asyncio.Semaphore,
    db_lock: asyncio.Lock,
    pending_cache: dict[str, str],
    pending_futures: dict[str, asyncio.Future[str]],
    stats: TranslateStats,
    *,
    max_retries: int,
    retry_failed: bool,
    block_types: tuple[str, ...],
) -> None:
    if block.type not in block_types:
        stats.skipped += 1
        return

    # Phase 1: pre-checks under db_lock (single session access)
    async with db_lock:
        existing = await session.get(Translation, block.id)
        if existing is not None:
            if existing.status == "translated":
                stats.skipped += 1
                return
            if existing.status == "failed" and not retry_failed:
                stats.skipped += 1
                return

        model_name: str = getattr(llm, "model_name", "unknown")
        ck = make_cache_key(block.original_text, doc.src_lang, doc.tgt_lang, model_name)
        now = datetime.now(UTC)

        if ck in pending_cache:
            stats.cached += 1
            await _upsert_translation(
                session, block.id, pending_cache[ck], f"cache-hit:{model_name}",
                ck, "translated", now, existing,
            )
            return

        db_hit = await _db_cache_lookup(session, ck)
        if db_hit is not None:
            cached_text, source_model = db_hit
            pending_cache[ck] = cached_text
            stats.cached += 1
            await _upsert_translation(
                session, block.id, cached_text, f"cache-hit:{source_model}",
                ck, "translated", now, existing,
            )
            return

        # No cache. Check pending_futures (in-flight LLM call for same ck).
        existing_future = pending_futures.get(ck)
        if existing_future is None:
            my_future: asyncio.Future[str] = asyncio.get_running_loop().create_future()
            pending_futures[ck] = my_future
            in_flight = None
        else:
            my_future = None
            in_flight = existing_future
    # ─── db_lock released ───

    if in_flight is not None:
        # Another task is already LLM-translating this text. Wait for it.
        try:
            translated_text = await in_flight
        except Exception:
            # The owning task failed; mark this block as failed too.
            async with db_lock:
                stats.failed += 1
                await _upsert_translation(
                    session, block.id, "", model_name, ck, "failed",
                    datetime.now(UTC), None,
                )
            return
        async with db_lock:
            # Owner already put translated_text into pending_cache. Just upsert this block.
            stats.cached += 1
            await _upsert_translation(
                session, block.id, translated_text, f"cache-hit:{model_name}",
                ck, "translated", datetime.now(UTC),
                await session.get(Translation, block.id),
            )
        return

    # We own the future. Do the LLM call.
    try:
        translated_text = await _translate_with_retry(
            llm, block.original_text, doc.src_lang, doc.tgt_lang, max_retries, sem,
        )
    except Exception as exc:
        my_future.set_exception(exc)
        async with db_lock:
            stats.failed += 1
            await _upsert_translation(
                session, block.id, "", model_name, ck, "failed",
                datetime.now(UTC), None,
            )
            pending_futures.pop(ck, None)
        return

    my_future.set_result(translated_text)
    async with db_lock:
        pending_cache[ck] = translated_text
        pending_futures.pop(ck, None)
        stats.translated += 1
        await _upsert_translation(
            session, block.id, translated_text, model_name, ck, "translated",
            datetime.now(UTC), None,
        )
```

`_translate_with_retry` (V2 — sem outside sleep):
```python
async def _translate_with_retry(
    llm: TranslateLLMClient,
    text: str,
    src: str,
    tgt: str,
    max_retries: int,
    sem: asyncio.Semaphore,
) -> str:
    last_exc: LLMTransientError | None = None
    for attempt in range(max_retries + 1):
        if attempt > 0:
            await asyncio.sleep(2 ** (attempt - 1))  # OUTSIDE sem — slots yielded during backoff
        try:
            async with sem:
                return await llm.translate(text, src, tgt)
        except LLMTransientError as exc:
            last_exc = exc
    assert last_exc is not None
    raise last_exc
```

### 2. Stored vector reuse — architecture

```python
# src/ht_lens/embedding/lookup.py (NEW)

from __future__ import annotations
import numpy as np
from sqlalchemy.ext.asyncio import AsyncSession
from ht_lens.db.models import Block, BlockEmbedding
from ht_lens.embedding.service import EmbeddingClient, text_source_hash
from ht_lens.embedding.store import vector_from_bytes


async def get_or_encode_block_vector(
    session: AsyncSession,
    embedding_client: EmbeddingClient,
    block: Block,
) -> np.ndarray:
    """Return query vector for ``block.original_text``.

    Prefers the stored ``block_embeddings`` row when present and not stale
    (``source_hash`` matches current text). Falls back to live encode otherwise.
    """
    text = (block.original_text or "").strip()
    if not text:
        return np.zeros((embedding_client.dim,), dtype=np.float32)

    row = await session.get(BlockEmbedding, block.id)
    if row is not None and row.source_hash == text_source_hash(text):
        return vector_from_bytes(row.vector, row.dim)

    # Fallback: cold encode (~575ms on CPU)
    return embedding_client.encode([text])[0]
```

Caller change in `src/ht_lens/api/chat_context.py::_build_cross_doc_refs`:
```python
# OLD:
# query_vec = embedding_client.encode([text])[0]
# NEW:
query_vec = await get_or_encode_block_vector(session, embedding_client, target)
```

Caller change in `src/ht_lens/api/routers/blocks.py::related_blocks`:
```python
# OLD:
# query_vec = embedding_client.encode([text])[0]
# NEW:
query_vec = await get_or_encode_block_vector(session, embedding_client, target)
```

### 3. Backward compatibility
- `--concurrency` flag default 5 → 7. 명시한 사용자는 그대로 (단 진짜로 동시 처리).
- `translate_document` signature: `concurrency: int = 5` → `concurrency: int = 7`. 다른 인자 동일.
- `_translate_with_retry` signature: 동일 (sem 그대로 받음, 단 내부 동작이 sleep-outside-sem).
- `_process_block` signature: 새 인자 `db_lock`, `pending_futures` 추가. Internal helper이므로 caller 없음.
- API 응답, DB schema, 환경 변수 변경 없음.

## File-level changes

| Path | Action | Note |
| ---- | ------ | ---- |
| `src/ht_lens/translate/pipeline.py` | MODIFY | `asyncio.as_completed` fan-out, db_lock, pending_futures, default concurrency 5→7 |
| `src/ht_lens/translate/cli.py` | MODIFY | `--concurrency` default 5→7, help text 갱신 |
| `src/ht_lens/embedding/lookup.py` | NEW | `get_or_encode_block_vector` |
| `src/ht_lens/embedding/__init__.py` | MODIFY (maybe) | export `get_or_encode_block_vector` |
| `src/ht_lens/api/chat_context.py` | MODIFY | `_build_cross_doc_refs` 에서 lookup helper 사용 |
| `src/ht_lens/api/routers/blocks.py` | MODIFY | `related_blocks` 에서 lookup helper 사용 |
| `tests/unit/test_translate_concurrency.py` | NEW | 4 tests: parallel, c=1 sequential, partial failure, dedup-c2 |
| `tests/unit/test_translate_cancel.py` | NEW | 1 test: cancel preserves state |
| `tests/integration/test_translate_progress.py` | MODIFY | concurrency=4 variant |
| `tests/integration/test_api_related.py` | MODIFY | counting embedding client, 3 cases (hit, stale, miss) |
| `tests/integration/test_chat_context_rag.py` | MODIFY | 1 추가 case: stored vector hit |

## Dependencies (new)
없음. `asyncio` (stdlib), 기존 numpy / sqlalchemy / 기존 BlockEmbedding ORM.

## Test strategy

### Unit (new)
1. **`test_translate_concurrency_runs_in_parallel`**:
   - Mock LLM: `await asyncio.sleep(0.1)` then return canned text.
   - 5 blocks (distinct texts to avoid dedup), `concurrency=5`. File-backed SQLite (`tmp_path`).
   - `time.monotonic()` elapsed < 0.25s (parallel) vs c=1 elapsed ≥ 0.4s.
2. **`test_translate_concurrency_one_sequential`**:
   - `concurrency=1`. 4 blocks. mock LLM no-sleep. stats + results 동등성. (regression for c=1 path)
3. **`test_translate_partial_failure_does_not_block_others`**:
   - 5 blocks, mock LLM raises `LLMPermanentError` for 3rd block. nonretryable. stats.failed == 1, stats.translated == 4.
4. **`test_translate_deduplicates_duplicate_blocks_in_memory_with_concurrency_2`**:
   - 2 blocks with identical text. `concurrency=2`. mock LLM counter.
   - assert `call_count == 1`, `stats.translated == 1`, `stats.cached == 1`. (pending_futures 효과)
5. **`test_translate_cancel_mid_run_preserves_state`**:
   - 4 blocks. Mock LLM: 처음 2개 빠른 완료, 3번째는 `await asyncio.sleep(60)` (cancel 트리거).
   - main task: `asyncio.create_task(translate_document(...))` 후 0.5s 뒤 cancel.
   - cancel 후: `Document.status` 변경 없음 (pre-run 상태 유지), 완료된 2개 `Translation` rows status='translated', 미완료 2개 row 없음.

### Integration (modify)
6. **`test_translate_callback_under_concurrency_4`** (test_translate_progress.py에 추가):
   - 동일 23 blocks fixture, `concurrency=4`. `calls == [(10, 23), (20, 23), (23, 23)]`.
7. **`test_api_related_uses_stored_vector_when_available`** (test_api_related.py modify):
   - `MockEmbeddingClient` subclass with `encode_call_count`. Block에 embedding 미리 upsert. `GET /blocks/{id}/related?k=5` → encode_call_count == 0.
8. **`test_api_related_falls_back_to_encode_on_stale_hash`**:
   - Block embedding 저장 후 `block.original_text` 수정 + commit. `GET /blocks/{id}/related` → encode_call_count == 1.
9. **`test_api_related_falls_back_to_encode_when_not_embedded`**:
   - Block embedding 없음. `GET /blocks/{id}/related` → encode_call_count == 1.
10. **`test_chat_context_uses_stored_embedding_when_available`** (test_chat_context_rag.py에 추가):
    - 동일 패턴.

### 회귀
- 기존 508 tests pass 유지. 특히:
  - `tests/integration/test_translate_pipeline_mock.py::test_translate_deduplicates_duplicate_blocks_in_memory` (Codex §3.1 회귀 risk) — c=5 default에서도 통과해야 함.
  - `tests/integration/test_translate_progress.py::test_translate_callback_fires_every_10_and_on_last` — `as_completed` 기반 progress가 동일한 `[(10,23),(20,23),(23,23)]` 출력.
  - `tests/integration/test_translate_cli.py` CLI default 5→7 변경 영향 (`--help` 출력 검증 test가 있으면 update).

### Verify 단계 throughput benchmark (pytest 외)
- Mock LLM (sleep 0.1s/block) 으로 30 blocks × c=1 vs c=7 wall-clock 측정. Speedup ≥ 5x.
- Optional live: small doc retranslate, 시간 측정.

### Verify 단계 RAG latency 측정
- Live API 가동 후 5 unique block × 3 sample = 15 requests. stored vector hit 경로 평균 p95 < 500ms 확인. fallback (miss) 경로 별도 측정.

### Verify 단계 DB contention 측정 (Sub-goal C 결정)
- Sub-goal A 적용 후 small doc retranslate. SQLITE_BUSY / OperationalError 로그 부재 확인. → Sub-goal C skip 확정 evidence. summary에서 사용자 보고.

## DoD mapping

| DoD item | How to satisfy | Evidence plan |
| -------- | -------------- | ------------- |
| Translation throughput ≥ 100 b/min at concurrency 7 (3x baseline) | `as_completed` + Semaphore + db_lock | verify benchmark: 30 blocks c=1 (~3s) vs c=7 (~0.5s) ≥ 5x. 이론 throughput 7 × 60/2.62 = 160 b/min |
| `/explain` p95 < 500ms (cold-include) | stored vector reuse → ~1ms DB lookup | verify benchmark: 5 unique block × 3 sample (warm-cache 효과 없음, stored vector 효과). hit 경로 p95 < 500ms |
| 회귀 0 (508 tests 유지) | API/CLI signature 동일, dedup 보존, progress tick 동일 | `uv run pytest -q | tail -3` → 508 + N new = 518+ passed (예측) |
| `--concurrency` parameter 진짜 동작 | `as_completed` + Semaphore | unit test 1+2 |
| Dedup 회귀 0 | pending_futures | 기존 dedup test 통과 + 신규 c=2 variant |
| Progress callback contract | `as_completed` 단일 counter | 기존 + concurrency=4 variant |
| Cancellation 정책 정의 | as_completed loop의 except BaseException + Document.status 미변경 | 신규 test_translate_cancel |
| DB batch commit (ROADMAP §C) | **Deferred per 결정 C**. verify에서 SQLITE_BUSY 부재 → skip 확정 | verify log + summary에서 사용자에게 ROADMAP §C 보고 |
| Documentation | pipeline.py module docstring 갱신 (V1 sequential bug fix 언급), CLI help text | summary.md |

## Risk / 주의

### Critical (V1 hazards resolved)
- ~~AsyncSession concurrent share~~ → db_lock으로 단일 task만 session 사용 (debate §2.1 ACCEPT)
- ~~Dedup race~~ → pending_futures (debate §3.1 ACCEPT)
- ~~Retry storm under sem~~ → sleep outside sem (debate §3.3 ACCEPT)
- ~~WAL false claim~~ → 제거 (debate §2.2 ACCEPT)
- ~~LRU cache 측정 부족 + cold-only fail~~ → stored vector reuse (debate §1.2 + §2.3 ACCEPT)

### Remaining
1. **Cancellation 시점에 db_lock hold 중인 task가 있으면**: as_completed가 main task에서 `BaseException` 잡고 `t.cancel()` 호출. CancelledError가 hold 중인 task에 propagate되면 lock 자동 해제 (`async with` __aexit__). 정합. 단 `session.commit()` 중간에 cancel되면 partial transaction 가능. SQLAlchemy 가 rollback 처리. 위험 낮음.
2. **`pending_futures` 의 future가 LLM failure로 set_exception → 같은 ck 기다리던 다른 task는 fail로 인식**. 정합 (한 LLM call이 실패하면 같은 텍스트 다른 block도 동일 결과 예상). 단 분리해서 재시도하고 싶다면 다른 정책. 본 plan은 "동일 LLM call 실패 = 같은 텍스트 fail"로 통일.
3. **stored embedding stale**: source_hash check로 안전. 단 staleness window (block.original_text 수정과 embedding regenerate 사이) 는 짧다. 본 phase 무관.
4. **`as_completed` 의 task cancel propagation**: `t.cancel()` 호출 후 task가 await중인 lock/sem 에서 CancelledError 발생. 단 `as_completed` iterator 자체는 cancelled tasks를 yield하지 않음 (이미 yield된 것은 await에서 exception). 정합.
5. **Progress callback에서 user code가 long-running**: as_completed loop의 `await on_progress(...)` 가 callback 완료까지 block → 다음 fut.await 지연. 단 progress callback은 idempotent fast update여야 함 (jobs/pipeline.py 의 update_job 은 빠른 DB row update). 정합.
6. **`asyncio.Lock` overhead**: lock acquire/release 자체는 µs. LLM call 2.62s 대비 무시. throughput 영향 X.

### sglang cap (known)
- `effective_max_running_requests_per_dp = 7`. concurrency > 7 줘도 sglang queue로 cap. P99 ↑, throughput cap. 사용자 expectation 변화 (V1에서 c=30이 fake였음) summary 보고.

### Debate에서 추가 다룰 질문 (Stage 2 1회 종료, V2는 verify-cross에서 다시 검토)
- (없음 — challenge.md에서 모든 §1-§5 처리)
