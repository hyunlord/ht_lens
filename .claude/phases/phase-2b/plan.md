# Phase 2b — Plan

## Goal

sglang Qwen3.6-27B (`enable_thinking=false`) 기반 `OpenAICompatibleClient` 구현, block 단위 async 번역 파이프라인 + cache, `python -m ht_lens.translate` CLI 완성. v0.1 마일스톤 달성.

## Scope

**In**
- `llm/errors.py` — LLM 에러 위계 (`LLMError`, `EmptyLLMResponseError`, `LLMTransientError`, `LLMPermanentError`, `LLMHealthCheckFailed`)
- `llm/openai_compat.py` — `OpenAICompatibleClient` (`openai.AsyncOpenAI` 기반, `_extract_safe` 가드, `health_check` reasoning_tokens 회귀 체크)
- `llm/factory.py` — `openai_compat` 분기 추가
- `db/migrations/versions/0002_phase_2b_cache_and_sha.py` — `documents.src_pdf_sha256` (nullable), `translations.cache_key` (string, indexed) 추가
- `db/models.py` — 두 컬럼 추가
- `ingest/pipeline.py` — `doc_meta.json`의 `src_pdf_sha256` → `Document.src_pdf_sha256` 저장
- `translate/` — `__init__.py`, `__main__.py`, `pipeline.py`, `cache.py`, `cli.py`
- `cli.py` — `translate` subcommand 등록
- 테스트: unit (cache_key, safe_extract, errors), integration/mock, integration/live (@llm)

**Out**
- FastAPI / REST API (Phase 3)
- threads/messages CRUD (Phase 3)
- UI/viewer (Phase 4)
- 다국어 확장 (Phase 5)
- `translations.block_id` PK 리팩토링 (Phase 6)

## Approach

### 1. LLM 에러 위계

```
LLMError (base)
├── EmptyLLMResponseError      # finish_reason='length' + empty content
├── LLMTransientError          # 5xx, timeout, rate limit → retry 가능
├── LLMPermanentError          # 4xx (auth, bad request) → retry 불가
└── LLMHealthCheckFailed       # health_check 실패
```

openai SDK 예외 매핑:
- `openai.APIStatusError` 5xx → `LLMTransientError`
- `openai.APIStatusError` 4xx → `LLMPermanentError`
- `openai.APITimeoutError`, `openai.APIConnectionError` → `LLMTransientError`
- 그 외 → `LLMTransientError` (안전 기본값)

### 2. OpenAICompatibleClient

- `AsyncOpenAI(base_url=..., api_key=..., timeout=60, max_retries=0)` — 재시도는 translate pipeline에서 처리
- `extra_body={"chat_template_kwargs": {"enable_thinking": False}}` — sglang 전용
- `_extract_safe(response)`: finish_reason='length' + empty → `EmptyLLMResponseError`, empty content → `EmptyLLMResponseError`
- `health_check()`: 짧은 ping, reasoning_tokens == 0 확인. reasoning > 0 → `False` (chat template 회귀)

### 3. Migration 0002

컬럼만 추가 (backward compatible):
- `documents.src_pdf_sha256 VARCHAR NULL`
- `translations.cache_key VARCHAR NOT NULL DEFAULT ''` + INDEX
- `UNIQUE` 제약 없음 (같은 텍스트가 여러 block에 존재 가능)

### 4. Cache 전략 (결정)

`cache_key = sha256(text + "\x00" + src + "\x00" + tgt + "\x00" + model)`

- Hit: DB에서 같은 `cache_key`의 기존 `translation` 행을 찾아 텍스트 복사, model에 `"cache-hit:{원본 model}"` 표시
- Miss: LLM 호출

**image 블록**: `Translation` 행을 만들지 않음. skip으로 처리 (caption은 Phase 6).

### 5. 번역 파이프라인

```python
async def translate_document(
    doc_id: int,
    session: AsyncSession,
    llm: LLMClient,
    *,
    concurrency: int = 5,
    max_retries: int = 3,
    retry_failed: bool = False,
    block_types: tuple[str, ...] = ("text", "header"),
    dry_run: bool = False,
) -> TranslateStats
```

- `asyncio.Semaphore(concurrency)` 제어
- 재시도: `LLMTransientError` → exponential backoff (1s, 2s, 4s)
- `LLMPermanentError`, `EmptyLLMResponseError` → 즉시 `status='failed'`
- 성공 → `status='translated'`
- 모든 처리 후 단일 commit (중간 partial commit 없음 — 부분 실패 시 전체 rollback)
- `dry_run`: DB write 없이 캐시 예상 통계만 출력

**transaction 경계 결정**: batch 끝에 한 번 commit. 중간 실패 block은 `status='failed'`로 마킹 후 계속 처리 (전체 rollback 아님). 이유: 번역은 멱등 연산이므로 재시도 가능하며, 부분 결과가 전혀 없는 것보다 낫다.

**`--max-retries N`**: total 시도 횟수 = 1 + N. `--max-retries 3` → 최대 4번.

### 6. header 블록 처리 결정

`text`와 동일한 번역 prompt 사용. 별도 prompt 없음. 이유:
- Phase 2b scope에서는 단순화 유지
- header는 짧고 tech term 보존 동일 요구사항 적용
- Phase 3+ UI 단계에서 구분이 필요하면 revisit

### 7. 긴 block 처리 결정

2000자 초과 블록: 자르지 않고 그대로 전달. 이유:
- LLM max_tokens=2048로 대부분 커버
- 자르면 문장 단위 의미 손실 우려
- finish_reason='length' → `_extract_safe`가 잡음
- 추후 chunking은 Phase 3에서 text 분할 전략과 함께 논의

### 8. batch 중 endpoint down

endpoint down은 `LLMTransientError`로 매핑. 개별 block이 retry exhaustion 후 `status='failed'`로 마킹. 나머지 block은 계속 처리. 이유: 하나의 block이 endpoint 문제로 나머지 전체를 막으면 안 됨.

### 9. tqdm + logging 공존

tqdm은 `tqdm.asyncio.tqdm_asyncio` 사용, `write()` 대신 `tqdm.write()`로 로그 출력. structlog 추가 안 함 (Phase 2b scope 외). `logging.basicConfig` + `tqdm.contrib.logging` 사용.

### 10. `--dry-run` 정확한 동작

cache_key 계산 후 DB에서 hit 여부만 확인. LLM 호출 없음. 통계: total / cache_hits / estimated_llm_calls 출력 후 exit 0.

## File-level changes

| Path | Action | Note |
|------|--------|------|
| `src/ht_lens/llm/errors.py` | NEW | LLM 에러 위계 |
| `src/ht_lens/llm/openai_compat.py` | NEW | OpenAICompatibleClient |
| `src/ht_lens/llm/factory.py` | MODIFY | openai_compat 분기 |
| `src/ht_lens/llm/__init__.py` | MODIFY | 에러 클래스 re-export |
| `src/ht_lens/db/migrations/versions/0002_phase_2b_cache_and_sha.py` | NEW | migration |
| `src/ht_lens/db/models.py` | MODIFY | src_pdf_sha256, cache_key 컬럼 |
| `src/ht_lens/ingest/pipeline.py` | MODIFY | sha256 저장 |
| `src/ht_lens/translate/__init__.py` | NEW | re-export |
| `src/ht_lens/translate/__main__.py` | NEW | module entry |
| `src/ht_lens/translate/cache.py` | NEW | cache_key 함수 |
| `src/ht_lens/translate/pipeline.py` | NEW | async batch pipeline |
| `src/ht_lens/translate/cli.py` | NEW | Typer subcommand |
| `src/ht_lens/cli.py` | MODIFY | translate subcommand 등록 |
| `tests/unit/test_cache_key.py` | NEW | |
| `tests/unit/test_safe_extract.py` | NEW | _extract_safe mock |
| `tests/unit/test_llm_errors.py` | NEW | 에러 위계 |
| `tests/integration/test_translate_pipeline_mock.py` | NEW | MockLLMClient 기반 |
| `tests/integration/test_translate_pipeline_live.py` | NEW | @pytest.mark.llm |
| `tests/integration/test_health_check_live.py` | NEW | @pytest.mark.llm |
| `tests/conftest.py` | MODIFY | live_llm_client fixture |

## Dependencies (new)

| Package | Why |
|---------|-----|
| `openai>=1.50,<2` | AsyncOpenAI client (sglang compatible) |
| `tqdm>=4.66,<5` | batch progress display |

`tenacity` 없음 — retry는 직접 구현 (단순 exponential backoff 3회).

## Test strategy

### Unit (no @llm, fast)
- `test_cache_key.py`: 같은 입력 → 같은 digest, 다른 입력 → 다른 digest, separator 포함
- `test_safe_extract.py`: mock response 객체로 `_extract_safe` 가드 검증
- `test_llm_errors.py`: 에러 위계, isinstance 체크

### Integration / mock (no @llm)
- `test_translate_pipeline_mock.py`:
  - 3 fixture end-to-end (ingest → translate with mock → DB 행 검증)
  - cache hit 시나리오
  - retry exhaustion → status='failed'
  - `--retry-failed` 동작
  - `--dry-run` 통계
  - header/image 블록 처리

### Integration / live sglang (`@pytest.mark.llm`)
- `test_translate_pipeline_live.py`: sample_mixed.pdf end-to-end 번역 + 재실행 cache 100%
- `test_health_check_live.py`: health_check() reasoning_tokens == 0

## DoD mapping

| DoD item | How to satisfy | Evidence plan |
|----------|----------------|---------------|
| short fixture 번역 가능 | sample_mixed.pdf CLI round-trip | live test + manual spot-check |
| 재실행 캐시 hit 100% | cache_key lookup before LLM call | test_translate_pipeline_mock + live |
| 실패 block 재시도 | --retry-failed flag + status='failed' re-process | mock retry test |
| reasoning_tokens == 0 회귀 체크 | health_check() + EmptyLLMResponseError | unit test + live health_check |
| finish_reason='length' + empty 가드 | _extract_safe raises EmptyLLMResponseError | test_safe_extract |
| mypy strict 0 | uv run mypy src/ | CI + verify |
| ruff clean | uv run ruff check . | CI + verify |

## 미결정 사항 (debate에서 결정)

다음 9가지는 현재 plan 결정으로 debate에 제출:
1. image 블록 → skip (Translation 행 없음)
2. header 블록 → text와 동일 prompt
3. 긴 block → 자르지 않고 전달, finish_reason='length'로 감지
4. endpoint down → 개별 block failed, 나머지 계속
5. transaction 경계 → batch 끝에 한 번 commit
6. `--max-retries N` = 총 N+1번 시도
7. tqdm + logging → tqdm.contrib.logging
8. `--dry-run` → hit/miss 통계만 (DB write 없음)
9. `live_llm_client` fixture → LLM_BASE_URL env var, skip if not reachable
