# Phase 6e — Verify (self, v3 — post Planner-directed R2 micro-fix)

Planner 결정 (R2 round-cap 이후): Option (a) — Planner-directed micro-fix 3건 → verify v3 → push.
- R2 critique 3건 모두 valid + R2 자체 "R1 fix 인정 + concrete regression 없음" 명시
- 1.5시간 작업이라 별도 phase 분리 가치 작음
- Round-cap 우회는 Planner-directed라 정책상 허용

작성 직전 `git status` clean. cross-verify 재호출 금지.

## 5-A. Automated checks (fresh)

| Check | Command | Result |
| ----- | ------- | ------ |
| Lint | `uv run ruff check .` | All checks passed! |
| Format | `uv run ruff format --check .` | already formatted |
| Type | `uv run mypy src/` | Success: no issues found in 59 source files |
| Test (fast) | `make test-fast` | **427 passed, 7 deselected** in 161.81s |
| Coverage | `make check` 내장 | TOTAL 71% |
| CI (local) | `make check` | **RC=0** |
| CI (remote) | `.github/workflows/ci.yml` | pending push |

Phase 6e 누적 신규 테스트 **24건** (403 → 427):
- R0: 14
- R1 RE-CODE: +4
- **R2 Planner-directed micro-fix: +6**
  - `test_chat_timeout_invalid_falls_back_to_legacy` — CHAT scoped invalid → legacy 45
  - `test_chat_timeout_invalid_at_both_layers_uses_default` — 둘 다 invalid → 60
  - `test_chat_max_tokens_invalid_falls_back_to_legacy` — CHAT scoped invalid → legacy 1024
  - `test_chat_temperature_invalid_falls_back_to_legacy` — CHAT scoped invalid → legacy 0.5
  - `test_openai_client_implements_translate_protocol` — isinstance lock
  - `test_openai_client_implements_chat_protocol` — isinstance lock

## 5-B. Functional checks — R2 critique 3건 처리

### Fix 1 — chat-side numeric invalid lock (R2 §4-1)

기존: `_resolve_int` / `_resolve_float` invalid fallback이 translate-timeout만 explicit lock.
처리: chat-side 4 mirror tests 추가. 미래 chat refactor가 translate-side와 동일 logic 유지하게 lock.

```
LLM_TIMEOUT=45, CHAT_LLM_TIMEOUT=not_a_number → from_env_chat() timeout = 45  ✅
LLM_TIMEOUT=also-bad, CHAT_LLM_TIMEOUT=not_a_number → default 60               ✅
LLM_MAX_TOKENS=1024, CHAT_LLM_MAX_TOKENS=abc → max_tokens = 1024               ✅
LLM_TEMPERATURE=0.5, CHAT_LLM_TEMPERATURE=not_a_float → temperature = 0.5      ✅
```

### Fix 2 — OpenAICompatibleClient Protocol isinstance lock (R2 §4-2)

기존: structural typing isinstance가 `MockLLMClient`만 explicit. 실 prod client (`OpenAICompatibleClient`)는 mypy + 간접 lock.
처리: 2 explicit isinstance test 추가. Protocol 요구사항 변경 시 즉시 검출.

```python
client = OpenAICompatibleClient(base_url="...", model="...", api_key="...", max_tokens=2048, temperature=0.0)
assert isinstance(client, TranslateLLMClient)  # PASS
assert isinstance(client, ChatLLMClient)        # PASS
```

### Fix 3 — mock_fail asymmetric docs 정정 (R2 §4-3)

기존: `docs/CONFIGURATION.md`가 mock_fail을 generic 지원 provider로 표기.
처리: 명시적 "translate-side only" note 추가 + `src/ht_lens/llm/mock.py::FailMockLLMClient` docstring에 동일 정보. chat-side failure injection은 `make_test_client(chat_llm_override=...)` 패턴 안내.

코드 동작은 변경 없음 (intentional asymmetry). docs/docstring만 정정.

## 5-C. Regression check + 신 코드 경로 잠금 (워크플로우 0-3-A)

### R0 + R1 + R2 micro-fix 신 식별자 lock

| 영역 | 새 식별자 / 정책 | 잠금 |
| ---- | ---------------- | ---- |
| (R0) Protocol 분리 | `TranslateLLMClient`, `ChatLLMClient`, `LLMClient` alias | structural typing isinstance + 6 unit tests |
| (R0) Factory 2 분기 | `from_env_translate`, `from_env_chat`, `_resolve` 등 | 7 unit + 2 timeout tests |
| (R0) max_tokens 정책 | 2048 / 4096 상수 | unit test |
| (R0) DI 분기 | `get_translate/chat_llm_client` | 3 routing tests |
| (R0) lifespan 두 LLM | startup 양쪽 검사 | 4 startup tests |
| (R1) jobs/pipeline.py 분기 | `app.state.translate_llm` / `app.state.chat_llm` | 실 실행 routing test |
| (R1) CLI scoped 우선 | `from_env_translate()` 호출 | mock_fail integration test |
| (R1) numeric fallback 정책 | scoped → legacy → default invalid 시 fall through | 2 unit tests (translate-side) |
| (R1) MockLLMClient isinstance | runtime Protocol 검증 | 1 unit test |
| **(R2) chat-side numeric invalid** | CHAT_LLM_TIMEOUT/MAX_TOKENS/TEMPERATURE 모두 fallback 검증 | **4 unit tests** |
| **(R2) OpenAICompatibleClient Protocol** | TranslateLLMClient + ChatLLMClient isinstance | **2 unit tests** |
| **(R2) mock_fail asymmetric docs** | docs/CONFIGURATION.md + mock.py docstring 정정 | docs review |

모든 신 식별자/정책 명시 lock. 워크플로우 0-3-A 의무 충족.

### 기존 contract 무회귀

- 421 → 427 fast tests 통과 (R0 14 + R1 4 + R2 6 = 24 신규)
- Phase 2b-6d 회귀 0
- mock.py / openai_compat.py / factory.py 동작 무변경 (docs/test만 추가)

### Deviations from Planner directive

- 모든 directive 준수 (3 fix + 명시 commit + push)
- cross-verify 재호출 없음
- 새 feature 없음 (chat-side mock_fail 구현은 Out of scope — docs 정정만)
- 다른 phase 영역 무변경

## 5-D. Scoring (100, v3 final)

| Item | Score | Evidence |
| ---- | ----- | -------- |
| 독창성 | 13 / 15 | (v2 동일) Protocol structural typing + scoped overrides + dual health check + numeric fallback 일관성 |
| 완결성 | **34 / 35** | (v2 동일) DoD 8건 + 24 신규 + 모든 호출처 실 실행 lock + isinstance prod client + chat numeric explicit |
| 안정성 | **30 / 30** (v2 29 → 30) | R1 critical fix + numeric fallback semantics + lifespan 양쪽 검사 + chat-side explicit lock + prod client Protocol 검증 + mock_fail asymmetry 명시 |
| 확장성 | 20 / 20 | env 1줄 swap + numeric fallback 안정성 + 모든 호출처 명시 lock |
| **Worker** | **97 / 100** | (v2 96 → v3 **97**) |

R2 critique 3건 모두 처리 — verification gap 해소.

## 5-E. Self verdict

- [x] **PASS_CONFIRMED** (Worker 97/100, Planner-directed R2 fix 적용)
- [ ] FAIL → RE-CODE
- [ ] FAIL → RE-PLAN

근거:
- R0 + R1 + R2 critique 모두 처리 (총 substantive 3 + verification 3 = 6 fix)
- 24 신규 테스트 + 회귀 0 (403 → 427)
- numeric fallback chat-side explicit lock + OpenAICompatibleClient isinstance + mock_fail docs 정정
- cross-verify 재호출 없음 (Planner-directed)
- self 97 → 자동 push 정책 충족
- **push 가능**
