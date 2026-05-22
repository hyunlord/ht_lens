# Phase 6e — Summary

## Status

**PASS_CANDIDATE_96** (Worker self v2, post RE-CODE) → **DOWNGRADE** (Codex R2, 제안 89). Round-cap.

R2 명시: "Round 1's substantive misses are fixed, and I do not see a concrete regression that justifies REJECT." R1 결함 fix 인정.

**Push 보류 → Planner escalate** (자동 push 정책 미충족).

## Score

- **Self v2 (RE-CODE 후)**: 96 / 100
- Self v1: 93 / 100
- Cross R1: DOWNGRADE (제안 86) — 3 substantive gaps, 모두 fix됨
- Cross R2: DOWNGRADE (제안 89) — R1 fix 인정 + 3 새 verification gap

## What was built

### Backend (R0)
- `llm/client.py`: `TranslateLLMClient`, `ChatLLMClient` (Protocol, runtime_checkable), legacy `LLMClient` alias
- `llm/factory.py`: `from_env_translate()`, `from_env_chat()`, `_resolve` 헬퍼
- `llm/openai_compat.py`: `__init__`에 `max_tokens=2048, temperature=0.7` (default 시그니처 유지)
- `api/app.py`: lifespan 두 LLM + state
- `api/deps.py`: scoped DI + legacy alias
- 라우터 DI 분기 + jobs/pipeline.py translate/chat 분기
- translate/summarize 타입 명시

### Backend (R1 RE-CODE)
- `_resolve_int` / `_resolve_float` invalid fallback 정책: scoped → legacy → default. invalid 시 다음 layer로 fall through.

### Tests +18 (403 → 421)
- R0: 14 (factory split 7, timeout 2, startup 2, routing 3)
- R1 RE-CODE: +4 (process_upload_job 실 실행, CLI scoped, two-layer invalid, structural typing isinstance)

### Docs + Config
- `.env.example`: TRANSLATE_LLM_* / CHAT_LLM_* + legacy commented out
- `docs/CONFIGURATION.md` NEW: 변수 표 + 마이그레이션 + health check semantics

## Both sides

### Worker (96)
R1 3 fix + 4 추가 테스트 + numeric fallback 일관성 + structural typing isinstance + 18 신규 테스트. ROADMAP DoD 일부 Out of scope 명시.

### Codex R2 (89)
R1 fix 인정. 그러나:
- numeric fallback chat-side 미테스트 (translate-timeout만)
- structural typing isinstance MockLLMClient만 (OpenAICompatibleClient 미)
- mock_fail asymmetric (chat path도 fail 시키는 mock 부재)
- self 96이 ROADMAP narrow subset 비해 과대

### Worker 보충
- numeric fallback: 단일 코드 경로 — translate-timeout invalid 동작 검증되면 동일. R2 valid: explicit lock 부재.
- OpenAICompatibleClient isinstance: mypy strict + Phase 6c live tests로 간접 lock. R2 valid: 명시 isinstance 부재.
- mock_fail asymmetric: 본 phase scope 아님 (§3-d). 별도 phase 필요.
- self 96: 본 phase scope 한정 평가. ROADMAP 잔여는 별도 phase 명시.

## Deviations from challenge

1. DeprecationWarning 빼기 (§1-b)
2. autouse prefix 유지 (§1-c)
3. jobs/pipeline.py 분기 (§2-a critical)
4. make_test_client API 확장 (§2-b)
5. _resolve 빈 문자열 fallback (§2-c)
6. _resolve_int/float invalid → fall through (R1 RE-CODE)
7. OpenAICompatibleClient default 유지 (§3-c)
8. ROADMAP DoD 일부 Out of scope 명시

## Evidence index

- plan / debate / challenge / verify v2 / verify-cross R1+R2 / summary
- code: `src/ht_lens/llm/` + `api/` + `jobs/` + `translate/` + `summarize/`
- docs: `.env.example`, `docs/CONFIGURATION.md`
- 421 fast tests + RC=0

## Known issues / debt — Phase 6e-2 / 6f / future

### R2 raised (Planner 검토)

1. numeric fallback chat-side explicit tests (R2 §4-1)
2. OpenAICompatibleClient structural typing isinstance (R2 §4-2)
3. mock_fail asymmetric — chat-fail mock 또는 docs 정정 (R2 §4-3)

### ROADMAP Phase 6e 잔여 (별도 phase)

- 핀 표시 / 사이드바 리사이즈 / 이미지 모달 / streaming / 백그라운드 패널 확장 / Playwright
- viewer 재시작 불필요 (runtime store)
- README 일주일 캡처

## Push status

**보류 (Planner escalate)**. 사유:
- Workflow round-cap (R1 DOWNGRADE → RE-CODE → R2 DOWNGRADE) 도달
- 자동 push 정책 `self ≥ 95 + cross CONFIRM_PASS` 미충족
- R2가 R1 fix 인정 → R0+R1 본체 작업 가치 인정
- Self 96 vs Codex R2 89 — 7점 차이 (scope 평가 + verification gap)
- Local main: origin 대비 **12 commits ahead**

Planner 결정 옵션:
- (a) Planner-directed micro-fix 3건 (chat numeric + isinstance + mock_fail docs) → verify v3 → push
- (b) 그대로 push 승인 + ROADMAP 잔여 별도 phase
- (c) Phase 6e scope 확장 (UI 항목 추가, 큰 작업)

## Recommended next

- Planner 결정 후 push 또는 micro-fix
- Phase E1.5 / E2 (fine-tune): 본 phase 인프라가 swap 1줄로 도와줌
- Phase 6f (extract 품질): header heuristic + fragment 분리
- Phase 6e-2 (UI polish): ROADMAP Phase 6e 잔여 항목

---

**ht_lens 도메인 코드 변경**: src/ht_lens/llm/ + api/ + jobs/pipeline.py + translate/summarize/cli 타입 + 환경 변수 분리. ht_lens 서버 무영향 (deployment 시 .env 호환). Phase E1과 직교.
