# Phase 6e — Challenge

## Debate responses

### 1. Over-engineering

**(a) "broad refactor"** — **PARTIAL ACCEPT**
응답: ROADMAP "모델 빠른 토글" DoD 중 **인프라**만 본 phase에 처리. "viewer 재시작 불필요"는 runtime store 필요 → Out of scope. summary.md 명시.

**(b) "legacy LLMClient alias + DeprecationWarning은 migration scaffolding"** — **ACCEPT**
응답: legacy `LLMClient` alias는 유지 (mypy 호환). 그러나 **DeprecationWarning은 안 붙임**. `from_env()`는 단순 위임만. 두 번째 client 실제 도입 시 warning 검토.

**(c) "autouse가 20+ key allowlist"** — **REJECT**
응답: Phase 6c가 이미 allowlist 패턴 도입. plan은 **확장**만. prefix-snapshot 전환은 회귀 위험.

### 2. Hidden assumptions

**(a) `jobs/pipeline.py::process_upload_job`가 `app.state.llm` 사용** — **ACCEPT (critical)**
응답: line 109 `llm = app.state.llm`. process_upload_job은 translate + summarize 둘 다 사용 → **각 단계 별도 client 사용**으로 분기. plan §5 + §9 갱신.

**(b) `_api_helpers.make_test_client`가 `get_llm_client`만 override** — **ACCEPT**
응답: API 확장 — `translate_llm_override`, `chat_llm_override` 신규 인자. 기존 `llm_override`는 두 client 모두 override (backward compat).

**(c) `_resolve` 빈 문자열 처리** — **ACCEPT**
응답:
```python
def _resolve(scoped: str, legacy: str, default: str | None = None) -> str | None:
    v = os.environ.get(scoped, "").strip()
    if v: return v
    v = os.environ.get(legacy, "").strip()
    if v: return v
    return default
```

**(d) DoD가 ROADMAP DoD에 매핑되지 않음** — **PARTIAL ACCEPT**
응답: ROADMAP Phase 6e DoD 중 인프라 부분만 처리. 나머지는 Out of scope. summary.md 명시.

### 3. Edge cases

**(a) One provider healthy, other unhealthy** — **ACCEPT**
응답: lifespan에서 두 LLM 모두 health check pass 요구. 같은 backend면 같이 죽거나 같이 산다. summary.md 명시.

**(b) Mixed scoped/legacy** — **ACCEPT**
응답: precedence는 **per-key 독립**. 빈 문자열은 fallback.

**(c) Direct `OpenAICompatibleClient(...)` 호출** — **ACCEPT**
응답: 생성자 default 시그니처 유지 (`max_tokens=2048, temperature=0.7`). factory에서 explicit value 전달:
- translate: `temperature=0.0`
- chat: `temperature=0.2`

직접 호출 (live_llm_client 등)은 backward compat.

**(d) FailMockLLMClient asymmetric** — **PARTIAL ACCEPT**
응답: 본 phase 미포함 (scope 축소). missing test §5에서 chat-fail이 필요하면 그때 추가.

### 4. Alternative approaches

**`from_env(prefix=...)`** — **REJECT**
응답: Protocol 분리가 더 명시적, mypy 친화적. Worker 선택 유지.

**Runtime settings store** — **ACCEPT (defer)**
응답: viewer 재시작 불필요 충족엔 runtime store 필요. 별도 phase.

### 5. Missing tests — 6건 모두 **ACCEPT**

1. `test_jobs_pipeline.py::test_process_upload_job_routes_summary_to_chat_llm`
2. `test_api_messages.py::test_llm_override_reaches_chat_dependency` + retranslate 변종
3. `test_api_startup.py::test_startup_fails_when_chat_llm_health_check_fails` + translate 변종
4. `test_factory_split.py::test_scoped_empty_string_falls_back_to_legacy`
5. `test_translate_cli.py::test_translate_cli_prefers_translate_scoped_env_over_legacy`
6. `test_api_summarize.py::test_summarize_uses_chat_scoped_env`

---

## Plan revisions (after debate)

1. **scope 축소**: DeprecationWarning 안 붙임. `from_env()` 단순 위임만.
2. **jobs/pipeline.py 분기** (§2-a, critical): translate / summarize 단계별 `state.translate_llm` / `state.chat_llm` 사용.
3. **_api_helpers.make_test_client API 확장** (§2-b): `translate_llm_override` + `chat_llm_override`.
4. **_resolve 빈 문자열 fallback** (§2-c): `os.environ.get(k, "").strip()`.
5. **OpenAICompatibleClient 생성자 default 유지** (§3-c): factory에서 explicit 전달.
6. **Lifespan health check**: 둘 다 fail이면 startup 실패. summary.md 명시.
7. **Missing tests 6건 추가** (§5).
8. **DoD 명시**: ROADMAP "viewer 재시작 불필요" 등은 Out of scope.

---

## File-level changes (revised)

| File | Action | Note |
| ---- | ------ | ---- |
| `src/ht_lens/llm/client.py` | MODIFY | Protocol 분리 + legacy alias |
| `src/ht_lens/llm/factory.py` | MODIFY | 2 분기 + `_resolve` |
| `src/ht_lens/llm/openai_compat.py` | MODIFY | __init__ 인자 + default 유지 |
| `src/ht_lens/llm/__init__.py` | MODIFY | export |
| `src/ht_lens/api/app.py` | MODIFY | lifespan 두 LLM |
| `src/ht_lens/api/deps.py` | MODIFY | get_translate/chat_llm_client |
| `src/ht_lens/api/routers/messages.py` | MODIFY | DI → chat_llm |
| `src/ht_lens/api/routers/blocks.py` | MODIFY | DI → translate_llm |
| `src/ht_lens/api/routers/documents.py` | MODIFY | DI → chat_llm |
| **`src/ht_lens/jobs/pipeline.py`** | **MODIFY (R1)** | translate/summarize 분기 |
| `src/ht_lens/translate/pipeline.py` | MODIFY | 타입 명시 |
| `src/ht_lens/summarize/pipeline.py` | MODIFY | 타입 명시 |
| `src/ht_lens/translate/cli.py` | MODIFY | from_env_translate |
| `tests/conftest.py` | MODIFY | autouse 확장 |
| `tests/integration/_api_helpers.py` | MODIFY (R1) | 새 override 인자 |
| `tests/unit/test_factory_split.py` | NEW | 7 cases |
| `tests/unit/test_llm_factory_timeout.py` | MODIFY | TRANSLATE/CHAT_LLM_TIMEOUT |
| `tests/integration/test_jobs_pipeline.py` | MODIFY (R1) | summary → chat_llm |
| `tests/integration/test_api_messages.py` | MODIFY (R1) | chat override |
| `tests/integration/test_api_blocks.py` | MODIFY (R1) | retranslate override |
| `tests/integration/test_api_startup.py` | MODIFY (R1) | health check fail |
| `tests/integration/test_api_summarize.py` | MODIFY (R1) | chat scoped env |
| `tests/integration/test_translate_cli.py` | MODIFY (R1) | scoped 우선 |
| `.env.example` | MODIFY | 새 변수 + legacy commented |
| `docs/CONFIGURATION.md` | NEW | 변수 표 + 마이그레이션 |

---

## DoD checklist

| ROADMAP Phase 6e DoD | Status | Note |
| --- | --- | --- |
| 핀 표시 / 사이드바 리사이즈 / 이미지 모달 / streaming | **Out of scope** | 별도 phase |
| 모델 빠른 토글 (env 1줄) | ✅ partial | factory split + env documented |
| ↳ viewer 재시작 불필요 | **Out of scope** | runtime store 필요 |
| ↳ README 일주일 캡처 | **Out of scope** | 실 사용 후 |
| 백그라운드 패널 확장 / Playwright | **Out of scope** | — |

본 phase 한정 DoD:

| DoD | Evidence |
| --- | --- |
| Protocol 분리 | `client.py` + `test_factory_split.py` |
| Factory 2 분기 + legacy 위임 | `factory.py` + 7 unit tests |
| max_tokens 정책 (2048/4096) | factory 상수 + `.env.example` |
| `_resolve` 빈 문자열 fallback | unit test |
| autouse fixture 확장 | conftest + 회귀 0 |
| 호출처 매핑 (6 영역) | grep + integration test |
| 회귀 0 | `make check` (403 → 415+) |

---

## Risk register

| Risk | Likelihood | Impact | Mitigation |
| --- | --- | --- | --- |
| `jobs/pipeline.py` 누락 (R1) | High | summarize 잘못된 client | 분기 + 통합 테스트 |
| `make_test_client` override miss | Medium | mock 격리 깨짐 | 새 override 인자 + 테스트 |
| `_resolve` 빈 문자열 → invalid | Medium | startup 실패 | 빈 문자열 fallback |
| 두 health check cost | Low | +10-50ms | sglang idempotent |
| `openai_compat` 직접 호출 회귀 | Medium | 테스트 실패 | default 유지 |
| ROADMAP DoD 미충족 | High by intent | 기대 mismatch | summary.md 명시 |

---

## Decision

- [x] PASS → proceed to code (revisions 8건 적용)
- [ ] RE-PLAN

Codex 비판 17건:
- §1: 1 PARTIAL + 1 ACCEPT + 1 REJECT
- §2: 4 ACCEPT (jobs critical, _api_helpers, _resolve, DoD)
- §3: 3 ACCEPT + 1 PARTIAL
- §4: 1 REJECT + 1 ACCEPT (defer)
- §5: 6 ACCEPT (전부 추가)

핵심:
1. jobs/pipeline.py 분기 (substantive, R1)
2. make_test_client API 확장
3. _resolve 빈 문자열 fallback
4. DeprecationWarning 빼기 (scope 축소)
5. Missing tests 6건
6. ROADMAP DoD 미충족 부분 명시
