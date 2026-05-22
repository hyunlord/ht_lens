# Phase 6e — Plan (LLM Routing Split)

## Goal

ROADMAP Phase 6e (Polish Pack) 중 "모델 빠른 토글" 부분만 본 phase에서 처리한다. Phase E1 결과 qwen3.6-27b 유지 → 미래 swap 받을 수 있는 인프라만 분리.

핵심 4건:
1. `LLMClient` Protocol을 **`TranslateLLMClient`** / **`ChatLLMClient`** 로 분리.
2. Factory `from_env()` → `from_env_translate()` / `from_env_chat()` 두 분기 + legacy deprecation.
3. `max_new_tokens` 정책: translate 2048 (E1 측정 max 1513 token + 35% 여유), chat 4096.
4. Phase 6c `_isolate_llm_env` autouse fixture를 두 LLM env 그룹 모두 격리.

ROADMAP Phase 6e의 다른 항목 (사이드바 리사이즈, 핀 색깔, 이미지 모달, streaming, 백그라운드 패널, Playwright)은 **본 phase 미포함** — 별도 phase 처리.

## Scope

**In**
- `src/ht_lens/llm/client.py`: 2 Protocol 분리 + legacy alias
- `src/ht_lens/llm/factory.py`: `from_env_translate()` / `from_env_chat()` + `from_env()` deprecation
- `src/ht_lens/llm/openai_compat.py`: `max_tokens` / `temperature`을 생성자 인자로 노출
- `src/ht_lens/llm/__init__.py`: export 확장
- `src/ht_lens/api/app.py`: lifespan에서 두 LLM 생성 + state 저장
- `src/ht_lens/api/deps.py`: `get_translate_llm_client` / `get_chat_llm_client`
- `src/ht_lens/api/routers/messages.py`: chat handler DI 변경
- `src/ht_lens/api/routers/blocks.py`: retranslate handler DI 변경
- `src/ht_lens/api/routers/documents.py`: summarize endpoint DI 변경
- `src/ht_lens/translate/pipeline.py`: 인자 타입 명시
- `src/ht_lens/summarize/pipeline.py`: 인자 타입 명시
- `src/ht_lens/translate/cli.py`: `from_env_translate()` 호출
- `tests/conftest.py`: autouse 확장
- `tests/integration/_api_helpers.py`: mock env 두 키 pin
- `tests/unit/test_factory_split.py` (NEW): 6 cases
- `tests/unit/test_llm_factory_timeout.py`: TRANSLATE/CHAT_LLM_TIMEOUT 분기
- `.env.example`: 새 변수 + legacy commented
- `docs/CONFIGURATION.md` (NEW): 변수 표 + 마이그레이션 가이드

**Out**
- Phase E1.5 / E2 (Hy-MT2 swap, fine-tune)
- ROADMAP Phase 6e의 다른 polish 항목
- 환경 변수 이름 변경 (`LLM_*` 그대로 유지, deprecation만)
- ROADMAP / WORKFLOW / CLAUDE / AGENTS 수정

## Approach

### 1) Protocol 분리

```python
# client.py
@runtime_checkable
class TranslateLLMClient(Protocol):
    async def translate(self, text: str, src: str, tgt: str, *, context: str | None = None) -> str: ...
    async def health_check(self) -> bool: ...

@runtime_checkable
class ChatLLMClient(Protocol):
    async def chat(self, messages: list[Message], *, system: str | None = None) -> str: ...
    async def health_check(self) -> bool: ...

# Legacy alias — 단일 client 객체가 translate + chat 모두 구현하면 두 Protocol 다 만족.
LLMClient = TranslateLLMClient
```

Structural typing이라 `OpenAICompatibleClient` / `MockLLMClient`이 두 메서드를 들고 있으면 두 Protocol 모두 implements. 따라서 break 없음.

### 2) Factory 분리

```python
_TRANSLATE_DEFAULT_MAX_TOKENS = 2048
_CHAT_DEFAULT_MAX_TOKENS = 4096
_TRANSLATE_DEFAULT_TEMP = 0.0
_CHAT_DEFAULT_TEMP = 0.2

def _resolve(scoped: str, legacy: str, default: str | None = None) -> str | None:
    """우선순위: scoped > legacy > default."""
    v = os.environ.get(scoped)
    if v is not None: return v
    v = os.environ.get(legacy)
    if v is not None: return v
    return default

def from_env_translate() -> TranslateLLMClient: ...
def from_env_chat() -> ChatLLMClient: ...

def from_env() -> TranslateLLMClient:
    warnings.warn("use from_env_translate / from_env_chat", DeprecationWarning, stacklevel=2)
    return from_env_translate()
```

### 3) `OpenAICompatibleClient` 생성자 확장

현재 `translate()` 안에 `temperature=0.7, max_tokens=2048` hard-coded. 이걸 `__init__`에 인자로 받고 method에서 self.max_tokens / self.temperature 사용.

`translate()`의 default temperature는 현재 0.7인데 0.0으로 변경 (factual, E1에서 0.0 사용). Factory 분기로 chat용은 0.2 유지.

### 4) Lifespan 두 LLM

```python
translate_llm = from_env_translate()
chat_llm = from_env_chat()
if not _skip_llm_check():
    ok = await translate_llm.health_check()
    if not ok: raise ...
    # 같은 backend면 두 번째 호출은 sub-ms (sglang은 idempotent)
    ok2 = await chat_llm.health_check()
    if not ok2: raise ...

app.state.translate_llm = translate_llm
app.state.chat_llm = chat_llm
app.state.llm = translate_llm  # legacy alias
```

### 5) DI 분기

```python
def get_translate_llm_client(request) -> TranslateLLMClient: return request.app.state.translate_llm
def get_chat_llm_client(request) -> ChatLLMClient: return request.app.state.chat_llm
def get_llm_client(request) -> LLMClient: return request.app.state.llm  # legacy
```

호출처:
- `routers/messages.py`: `get_chat_llm_client` (chat + explain)
- `routers/blocks.py`: `get_translate_llm_client` (retranslate)
- `routers/documents.py`: `get_chat_llm_client` (summarize)
- `translate/pipeline.py`: 인자 타입 `TranslateLLMClient`
- `summarize/pipeline.py`: 인자 타입 `ChatLLMClient`

### 6) `max_tokens` 정책

| 용도 | 기본값 | 근거 |
| ---- | ------ | ---- |
| translate | **2048** | E1 측정 max 1513 token + 35% 여유. P99.9=803, MAX=1513 |
| chat | **4096** | Q&A/요약은 답이 더 길 수 있음 |

### 7) `.env.example`

```bash
# === Translate LLM ===
TRANSLATE_LLM_PROVIDER=openai_compat
TRANSLATE_LLM_BASE_URL=http://localhost:8081/v1
TRANSLATE_LLM_MODEL=qwen3.6-27b
TRANSLATE_LLM_API_KEY=EMPTY
TRANSLATE_LLM_MAX_TOKENS=2048
TRANSLATE_LLM_TEMPERATURE=0.0
TRANSLATE_LLM_TIMEOUT=300

# === Chat LLM ===
CHAT_LLM_PROVIDER=openai_compat
CHAT_LLM_BASE_URL=http://localhost:8081/v1
CHAT_LLM_MODEL=qwen3.6-27b
CHAT_LLM_API_KEY=EMPTY
CHAT_LLM_MAX_TOKENS=4096
CHAT_LLM_TEMPERATURE=0.2
CHAT_LLM_TIMEOUT=300

# === Legacy (deprecated fallback) ===
# LLM_PROVIDER=openai_compat
# LLM_BASE_URL=http://localhost:8081/v1
# LLM_MODEL=qwen3.6-27b
# LLM_TIMEOUT=300
```

### 8) Autouse fixture 확장

```python
@pytest.fixture(autouse=True)
def _isolate_llm_env(monkeypatch):
    keys = [
        "TRANSLATE_LLM_PROVIDER", "TRANSLATE_LLM_BASE_URL", "TRANSLATE_LLM_MODEL",
        "TRANSLATE_LLM_API_KEY", "TRANSLATE_LLM_MAX_TOKENS",
        "TRANSLATE_LLM_TEMPERATURE", "TRANSLATE_LLM_TIMEOUT",
        "CHAT_LLM_PROVIDER", "CHAT_LLM_BASE_URL", "CHAT_LLM_MODEL",
        "CHAT_LLM_API_KEY", "CHAT_LLM_MAX_TOKENS",
        "CHAT_LLM_TEMPERATURE", "CHAT_LLM_TIMEOUT",
        "LLM_PROVIDER", "LLM_BASE_URL", "LLM_MODEL",
        "LLM_API_KEY", "LLM_MAX_TOKENS", "LLM_TEMPERATURE", "LLM_TIMEOUT",
        "OLLAMA_BASE_URL", "OLLAMA_MODEL",
    ]
    for k in keys:
        monkeypatch.delenv(k, raising=False)
```

`make_test_client` (`tests/integration/_api_helpers.py`): `TRANSLATE_LLM_PROVIDER=mock` + `CHAT_LLM_PROVIDER=mock` 두 키 모두 pin.

### 9) 새 식별자 (워크플로우 0-3-A 의무 표)

| 영역 | 새 식별자 |
| ---- | -------- |
| llm/client.py | `TranslateLLMClient`, `ChatLLMClient` (Protocol), legacy `LLMClient` 유지 |
| llm/factory.py | `from_env_translate`, `from_env_chat`, `_resolve`, `_TRANSLATE_DEFAULT_MAX_TOKENS=2048`, `_CHAT_DEFAULT_MAX_TOKENS=4096`, `_TRANSLATE_DEFAULT_TEMP=0.0`, `_CHAT_DEFAULT_TEMP=0.2` |
| llm/openai_compat.py | `OpenAICompatibleClient.__init__(..., max_tokens=2048, temperature=0.0)`, `self.max_tokens`, `self.temperature` |
| api/app.py | `app.state.translate_llm`, `app.state.chat_llm` (+ legacy `app.state.llm`) |
| api/deps.py | `get_translate_llm_client`, `get_chat_llm_client` (+ legacy `get_llm_client`) |
| api/routers/messages.py | DI `chat_llm` |
| api/routers/blocks.py | DI `translate_llm` |
| api/routers/documents.py | DI `chat_llm` (summarize) |
| translate/pipeline.py | 인자 타입 `TranslateLLMClient` |
| summarize/pipeline.py | 인자 타입 `ChatLLMClient` |
| translate/cli.py | `from_env_translate()` |
| tests/conftest.py | autouse 확장 (20+ keys) |
| tests/integration/_api_helpers.py | `TRANSLATE_LLM_PROVIDER=mock` + `CHAT_LLM_PROVIDER=mock` pin |
| tests/unit/test_factory_split.py NEW | 6 cases |

## File-level changes

| File | Action | Note |
| ---- | ------ | ---- |
| `src/ht_lens/llm/client.py` | MODIFY | Protocol 분리 + legacy alias |
| `src/ht_lens/llm/factory.py` | MODIFY | 2 분기 + deprecation + max_tokens 상수 |
| `src/ht_lens/llm/openai_compat.py` | MODIFY | __init__ 인자 + self 사용 |
| `src/ht_lens/llm/__init__.py` | MODIFY | export 확장 |
| `src/ht_lens/api/app.py` | MODIFY | lifespan 두 LLM |
| `src/ht_lens/api/deps.py` | MODIFY | get_translate/chat_llm_client |
| `src/ht_lens/api/routers/messages.py` | MODIFY | DI → chat_llm |
| `src/ht_lens/api/routers/blocks.py` | MODIFY | DI → translate_llm |
| `src/ht_lens/api/routers/documents.py` | MODIFY | DI → chat_llm |
| `src/ht_lens/translate/pipeline.py` | MODIFY | 타입 명시 |
| `src/ht_lens/summarize/pipeline.py` | MODIFY | 타입 명시 |
| `src/ht_lens/translate/cli.py` | MODIFY | from_env_translate |
| `tests/conftest.py` | MODIFY | autouse 확장 |
| `tests/integration/_api_helpers.py` | MODIFY | 두 mock 키 pin |
| `tests/unit/test_factory_split.py` | NEW | 6 cases |
| `tests/unit/test_llm_factory_timeout.py` | MODIFY | TRANSLATE/CHAT timeout |
| `.env.example` | MODIFY | 새 변수 + legacy commented |
| `docs/CONFIGURATION.md` | NEW | 변수 표 + 마이그레이션 가이드 |

## Dependencies (new)

없음. stdlib만 (`warnings`, `os`, `typing`).

## Test strategy

### 단위
- `test_factory_split.py` NEW (6 cases):
  - `test_from_env_translate_uses_translate_vars` — scoped 우선
  - `test_from_env_chat_uses_chat_vars` — scoped 우선
  - `test_legacy_llm_vars_still_work` — LLM_*만 set, 두 factory 같은 값
  - `test_translate_scoped_overrides_legacy` — scoped 우선
  - `test_max_tokens_defaults` — 2048/4096
  - `test_from_env_emits_deprecation_warning` — DeprecationWarning 발생
- `test_llm_factory_timeout.py` 확장 (TRANSLATE/CHAT_LLM_TIMEOUT)

### 통합 (기존 403건 무회귀)
- Phase 6d까지 403 fast tests 100% pass
- `make_test_client` mock 격리 검증
- messages chat / blocks retranslate / documents summarize / translate cli 무회귀

### Live (선택)
- `pytest -m llm`: 기존 7건 무회귀

## DoD mapping

| DoD | Evidence |
| --- | -------- |
| Protocol 분리 | client.py + `test_factory_split.py` |
| Factory 2 분기 + legacy deprecation | factory.py + 6 unit tests |
| max_tokens 정책 (2048/4096) | factory.py 상수 + `.env.example` + unit test |
| autouse fixture 확장 | conftest.py + 기존 403 무회귀 |
| 호출처 매핑 | grep으로 새 식별자 lock |
| 회귀 0 | `make check` 통과 (403 → 410+) |

## 미결정 사항 (debate 검토 대상)

1. `LLMClient` legacy alias: TranslateLLMClient를 가리킴. 향후 phase에서 deprecation warning.
2. Health check 두 번 호출 (같은 backend일 때): 단순화로 두 번. ~ms 비용.
3. `openai_compat.translate()` temperature 기본값 0.7 → 0.0: factual 우선.
4. `max_tokens` env가 invalid (non-int): 기본값 fallback + warning log.
5. Mock client는 두 Protocol structural typing으로 자동 호환 — 검증 필요.
6. `_resolve` 헬퍼 위치: factory.py 내부.
7. `get_llm_client` legacy: 유지 (warning 없음). 향후 phase에서 deprecation.
8. CLI: `translate/cli.py` fix. 다른 cli 점검 (현재 없음 확인).
9. `OpenAICompatibleClient.__init__` 인자 추가: 기본값 유지로 backward compat.
10. `docs/CONFIGURATION.md` 신규: 환경 변수 표 + 마이그레이션.

debate에서 Codex가 찌를 가능성:
- protocol structural typing이 `runtime_checkable` 정상 동작?
- legacy `LLMClient` alias 모호성 (TranslateLLMClient만 가리키면 chat client API 노출 안 됨)?
- _resolve 우선순위 corner case (빈 문자열 vs 없음)?
- autouse fixture가 다른 LLM 관련 env (OPENAI_API_KEY 등) 영향?
- 신 식별자 grep test 명확성?
- summarize.py 인자 타입 변경 시 import cycle 발생 가능성?
