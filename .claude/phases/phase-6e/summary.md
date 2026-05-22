# Phase 6e — Summary (v2 — Planner adjusted PASS_CONFIRMED)

## Status

**PASS_CONFIRMED (Worker self v3 = 97/100, Planner-directed R2 micro-fix 적용)**.

진행 흐름:
- v1 (R0) self 93 → R1 cross DOWNGRADE 86 (3 substantive)
- v2 (R1 RE-CODE) self 96 → R2 cross DOWNGRADE 89 (3 verification gaps)
- **v3 (R2 Planner-directed micro-fix) self 97** — 모든 critique 처리, cross 재호출 없음 (round-cap 도달, Planner-directed)

## Score progression

| 단계 | Self | Cross | 비고 |
| ---- | ---- | ----- | ---- |
| v1 (R0) | 93 | R1 DOWNGRADE 86 | 3 substantive gaps |
| v2 (R1 RE-CODE) | 96 | R2 DOWNGRADE 89 | R1 fix 인정 + 3 verification gaps |
| **v3 (R2 Planner-fix)** | **97** | (cross 재호출 금지) | 6 critique 모두 처리 |

R2 자체 명시: "Round 1's substantive misses are fixed, and I do not see a concrete regression that justifies REJECT."

## What was built

### Backend (R0 + R1)
- `llm/client.py`: `TranslateLLMClient` + `ChatLLMClient` Protocol + legacy `LLMClient` alias
- `llm/factory.py`: `from_env_translate()` + `from_env_chat()` + `_resolve` 헬퍼 + (R1) invalid scoped → legacy → default fall through
- `llm/openai_compat.py`: `__init__`에 `max_tokens=2048, temperature=0.7` (default 시그니처 유지)
- `api/app.py`: lifespan 두 LLM + state.translate_llm/chat_llm + legacy alias
- `api/deps.py`: scoped DI + legacy alias
- 라우터 DI 분기: messages/documents → chat, blocks → translate
- `jobs/pipeline.py`: translate/chat 분기 (R1 critical)
- `translate/pipeline.py`, `summarize/pipeline.py`: 타입 annotation 명시
- `translate/cli.py` → `from_env_translate()`

### R2 Planner-directed micro-fix (이번 v3)
- `tests/unit/test_factory_split.py` +6 tests:
  - 4 chat-side numeric invalid (timeout/max_tokens/temperature + two-layer invalid)
  - 2 OpenAICompatibleClient isinstance (TranslateLLMClient + ChatLLMClient)
- `docs/CONFIGURATION.md`: mock_fail asymmetric note (translate-side only) + chat-side patch 패턴 안내
- `src/ht_lens/llm/mock.py::FailMockLLMClient` docstring 명시화

### Tests (R0 14 + R1 4 + R2 6 = 24 신규, 403 → 427)

### Docs + Config
- `.env.example`: TRANSLATE_LLM_*/CHAT_LLM_* + legacy commented
- `docs/CONFIGURATION.md` NEW + mock_fail note

## Files changed (전체 8e2a643..HEAD)

13 commits total (R0 ~5 + R1 ~3 + R2 micro-fix ~2 + plan/debate/challenge/verify/summary).

## Deviations from challenge

1. DeprecationWarning 빼기 (§1-b)
2. autouse prefix 유지 (§1-c)
3. jobs/pipeline.py 분기 (§2-a critical)
4. make_test_client API 확장 (§2-b)
5. _resolve 빈 문자열 fallback (§2-c)
6. _resolve_int/float invalid fall through (R1 RE-CODE)
7. OpenAICompatibleClient default 유지 (§3-c)
8. ROADMAP DoD 일부 Out of scope 명시 (별도 phase)

## All critiques addressed

### R1 substantive (R1 RE-CODE에서 fix)
1. jobs/pipeline.py 실 실행 미테스트 → fix
2. CLI scoped env 미테스트 → fix
3. numeric fallback inconsistent → fix (정책 변경 + 2 unit tests)

### R2 verification gaps (R2 Planner-directed micro-fix에서 fix)
1. numeric fallback chat-side explicit lock 부재 → 4 mirror tests 추가
2. OpenAICompatibleClient isinstance 검증 부재 → 2 explicit isinstance tests 추가
3. mock_fail asymmetric docs 부정확 → docs/docstring 정정 (코드 동작 변경 없음)

R0+R1+R2 모두 처리. R2 자체가 "concrete regression 없음" 명시 → 본 phase는 verification gap만 남았었음 → 처리 완료.

## Evidence index

- plan / debate / challenge / verify v3 / verify-cross R1+R2 / summary v2
- code: `src/ht_lens/llm/` + `api/` + `jobs/` + `translate/` + `summarize/`
- docs: `.env.example`, `docs/CONFIGURATION.md`
- 427 fast tests + RC=0

## Known issues / debt — Phase 6e-2 / 6f / future

### ROADMAP Phase 6e 잔여 (별도 phase로 진행)

- 핀 표시 더 직관적 (색깔/크기/위치)
- 사이드바 리사이즈 (좌우 드래그)
- 작은 이미지/도표 확대 모달
- streaming 응답 (SSE)
- 모델 토글 viewer 재시작 불필요 (runtime store)
- 백그라운드 작업 패널 확장
- Playwright 자동 시나리오
- README 일주일 실사용 캡처

### 별도 phase가 필요한 design 선택 (R2 critique 영역)

- chat-side failure injection mock (현재 translate-only) — 새 mock 클래스 추가 필요 시 별도 phase

## Push status

**완료 (Planner-directed adjusted score 97/100, 자동 push 정책 충족)**.

- `git push` 진행
- v0.7 → v0.7.1 micro-tag 또는 v0.7 그대로 (Phase 6d 도메인 기능 무영향)

## Recommended next

- **Phase E1.5 / E2 (fine-tune)**: 본 phase 인프라가 env 1줄로 swap 도움
- **Phase 6f (extract 품질)**: header heuristic + fragment 분리
- **Phase 6e-2 (UI polish)**: ROADMAP Phase 6e 잔여 (사이드바 리사이즈, 이미지 모달, streaming, viewer 재시작 불필요)

---

**ht_lens 도메인 코드 변경**: src/ht_lens/llm/ + api/ + jobs/pipeline.py + translate/summarize 타입 + 환경 변수 분리. ht_lens 서버 무영향 (legacy LLM_* 호환). Phase E1과 직교.
