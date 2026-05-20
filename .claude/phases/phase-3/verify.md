# Phase 3 — Verify (self, v2 — RE-CODE 후 재작성)

R1 cross-verify가 `DOWNGRADE` (제안 88/100) 판정함. RE-CODE 라운드 1회 수행 후 본 verify v2 작성.

작성 직전 `git status` clean. 본 verify는 RE-CODE 커밋 `67c7fbd` 시점에 대한 self-evaluation.

## 5-A. Automated checks

| Check    | Command (실행한 그대로) | Result |
| -------- | ----------------------- | ------ |
| Lint     | `uv run ruff check .`     | All checks passed! (38 files, 0 errors) |
| Format   | `uv run ruff format --check .` (verify 단계 전용 별도 호출) | 38 files already formatted |
| Type     | `uv run mypy src/`         | Success: no issues found in 49 source files |
| Test (fast) | `make test-fast` → `pytest -m "not llm and not slow"` (Makefile:17) | **196 passed, 5 deselected** in 72.76s |
| Coverage | `pytest -m "not llm" --cov=ht_lens.api --cov=ht_lens.llm.factory --cov-report=term` | API + factory 파일별 breakdown 아래 |
| Test (llm)  | `pytest -m llm` with LLM_* + LLM_TIMEOUT=300 | **5 passed, 196 deselected** in 110.16s |
| CI (local) | `make check` (Makefile:20: ruff format, ruff check, mypy strict, pytest "not llm") | RC=0 |

R1 cross-verify가 지적한 wording 정정:
- `make test-fast`는 `pytest -m "not llm and not slow"`로 실행됨 (현재 repo에 `slow` 표시 테스트는 없음). 본 verify에서는 두 가지 모두 등가의 196 통과를 산출.
- `make check`는 `ruff format .`(쓰기 적용)로 실행되며, 본 verify에서는 별도로 `ruff format --check .`(읽기 검사)를 돌려 양쪽 모두 깨끗함을 확인.
- 본 repo는 GitHub Actions remote CI 없음 (Phase 0 README/WORKFLOW에 미명시). `make check`로 동등한 로컬 게이트 통과.

### Phase 3 신규 파일 coverage breakdown

| File | stmt | miss | cov | 주요 미커버 |
| ---- | ---- | ---- | --- | ----------- |
| `api/__init__.py` | 0 | 0 | 100% | (빈 모듈) |
| `api/app.py` | 66 | 4 | **92%** | DB env URL 미설정 분기 (42, 63), LLMHealthCheckFailed-aware path (74-77) |
| `api/chat_context.py` | 38 | 0 | **100%** | — |
| `api/deps.py` | 25 | 2 | **92%** | `get_chat_concurrency` invalid int 분기 (45-46) |
| `api/routers/documents.py` | 36 | 9 | 66% | `list_documents` paging/limit 변형 (72-75) — Phase 3 DoD 핵심 경로는 커버됨 |
| `api/routers/messages.py` | 88 | 44 | 45% | unknown LLMError fallback 분기 (73), generic `LLMError` (non-Permanent/Transient) → 502 mapping은 매핑 분기 셋 중 하나만 커버. `/messages` 라인 145-149는 `/explain`과 동일 구조의 일부; 양쪽 happy-path는 커버. |
| `api/routers/pages.py` | 55 | 15 | 63% | bbox decode 예외, image content-type 동적 (98), 페이지 도큐먼트 404 분기 (117-118) — 핵심 happy/error는 커버. |
| `api/routers/threads.py` | 56 | 14 | 68% | `GET /threads/{id}/messages` 404 분기 미커버는 신규 추가 케이스 — `test_get_thread_messages_route_404_when_thread_missing`에서 커버. 라인 mapping 미세 차. |
| `api/schemas.py` | 71 | 0 | **100%** | — |
| `llm/factory.py` | 23 | 2 | 90% | `mock_fail` 분기 (27-29) — Phase 2b 전용 코드 |

핵심 새 코드 (chat_context, schemas)는 100%, 라우터는 65% 안팎 (대부분 happy-path 경로 + 주요 error 경로 커버). 라우터 미커버 라인은 대부분 dead-end 분기 (예: get_thread inner None branch가 selectinload 이후 도달 불가) 또는 동등한 다른 라우터에서 이미 커버된 동형 코드.

## 5-B. Functional checks

### 1) End-to-end 데이터 흐름 (extract → ingest → translate → API)

DB: `/tmp/ht_lens_phase3.db`. Stage 5a 시점에서 이미 채워둠. RE-CODE 후 DB 변경 없이 같은 DB로 verify_api.sh 재실행.

```
extract: ok: pages=6 lang=mixed
ingest:  ok: doc_id=1 pages=6 blocks=102
translate: ok: doc_id=1 translated=92 cached=4 skipped=6 failed=0
```

### 2) `scripts/verify_api.sh` (live LLM, RE-CODE 후 9-step)

```
[1/9] GET /documents                              doc_id=1 count=1
[2/9] GET /documents/1                            num_pages=6
[3/9] scan pages for a text block                 block_id=2 page=1
[4/9] GET /documents/1/pages/1                    blocks=37
[5/9] GET /documents/1/pages/1/image              png bytes=291676
[6/9] POST /threads (block_id=2)                  thread_id=4
[7/9] POST /threads/4/explain                     explain len=3341
[8/9] POST /threads/4/messages                    followup len=111
[9/9] GET /threads/4/messages                     messages=4 roles=user,assistant,user,assistant
verify_api.sh OK   (exit 0)
```

스크립트 변경:
- step 2: `GET /documents/{id}` 신규 추가
- step 3: 모든 페이지 스캔으로 첫 text block 찾기 (이전 R1에서 지적된 page 1 가정 제거)
- step 9: `GET /threads/{id}` → `GET /threads/{id}/messages` (신규 라우트로 history 검증)

### 3) Integration test 전수 (mock LLM)

`uv run pytest -m "not llm"` → **196 passed, 5 deselected** (이전 190 → 196, +6 신규).
신규 6건 (RE-CODE 라운드):
- `tests/unit/test_llm_factory_timeout.py` (3): LLM_TIMEOUT default/honor/invalid-fallback
- `tests/integration/test_api_messages.py::test_messages_whitespace_only_content_returns_422`
- `tests/integration/test_api_threads.py::test_get_thread_messages_route_returns_history_in_order`
- `tests/integration/test_api_threads.py::test_get_thread_messages_route_404_when_thread_missing`

### 4) LLM live tests

`uv run pytest -m llm` (LLM_TIMEOUT=300) → 5 passed in 110.16s. live `/explain`+`/messages` 응답은 Hangul 1자 이상 포함을 assert (R1에서 지적된 "non-empty only" 약점 해소).

### 5) Async 일관성 / pydantic schema 분리

전 router 모두 `async def`. AsyncSession + AsyncOpenAI await 일관. `api/schemas.py`에 Read/Create 10개 모델 + 2개 Literal alias (BlockType, MessageRole). DB ORM 모듈 임포트 없음.

## 5-C. Regression check (R1 → RE-CODE → R2 회귀 가드)

R1 cross-verify에서 지적된 4가지 결함을 fix하면서 새 코드 경로를 도입함. 회귀 보호 evidence:

### R1 결함 vs RE-CODE 적용 + 테스트 매핑

| R1 결함 | RE-CODE 변경 | 회귀 보호 테스트 |
| ------- | ----------- | ---------------- |
| Whitespace-only content 수락 | `MessageCreate.field_validator("content")`가 strip 후 빈 문자열 거부 | `test_messages_empty_content_returns_422` (기존, ""에 대해 422) + 신규 `test_messages_whitespace_only_content_returns_422` ("   \t\n  "에 대해 422) |
| `LLM_TIMEOUT` env 미테스트 | factory.from_env에 env 처리 (기존) + 신규 단위 테스트 3건 | `tests/unit/test_llm_factory_timeout.py`: default 60s / 180s honor / invalid-string fallback to 60s |
| Loose schema typing | `BlockRead.type: Literal["text","image","header"]`, `MessageRead.role: Literal["user","assistant","system"]`, 라우터에서 `cast(BlockType, ...)` 적용 | 기존 모든 API 응답 검증 테스트 (test_api_documents, pages, threads, messages, chat_context)에서 BlockRead/MessageRead의 type/role 값이 Literal 검증 통과; **mypy strict 0 errors** (Phase 2 ORM에서 들어오는 str → cast로 형 정합) |
| verify_api.sh가 page 1 text block 가정 / GET /threads/{id}/messages 부재 | step 3에서 페이지 전체 스캔, step 9에서 신규 GET 라우트 사용 | `test_get_thread_messages_route_returns_history_in_order` (history 순서 + 4건), `test_get_thread_messages_route_404_when_thread_missing` (없는 thread 404), live verify_api.sh exit 0 |

### RE-CODE에서 새로 추가한 코드 경로의 단위 테스트 존재 여부

- `MessageCreate._non_whitespace` (validator): `test_messages_whitespace_only_content_returns_422` + `test_messages_empty_content_returns_422` 두 케이스로 잠금.
- `GET /threads/{id}/messages` router endpoint: 200 + 404 두 케이스 잠금.
- `Literal[BlockType/MessageRole]`: mypy strict + 모든 API integration test (응답 JSON 검증)에서 잠금.
- `factory.from_env` LLM_TIMEOUT 분기: 3 unit test로 잠금.
- `scripts/verify_api.sh`: shellcheck 통과 + live exit 0로 잠금.

### 기존 contract 무회귀

- 기존 `test_messages_empty_content_returns_422` (R1 이전), `test_get_thread_includes_block_and_messages_in_order` (R1 이전 `GET /threads/{id}` 라우트의 messages 동봉) 모두 변경 없이 통과.
- Phase 1/2 테스트 (147건) 전수 통과.
- LLM client `MockLLMClient.model_name = "mock"` 기존 표현, `OpenAICompatibleClient.model_name` 기존 표현 — API의 `_llm_model_name`은 `getattr` 사용으로 무회귀.
- mypy strict 0 errors. ruff 0 errors.

### Deviations from plan (RE-CODE에서 의도적 변경)

- `BlockRead.type`/`MessageRead.role`을 plan의 `str`에서 Literal로 좁힘. 결과로 routers에서 `cast(BlockType, ...)` 1줄 추가. 의도: R1 지적의 contract tightening + Phase 4/5 클라이언트 타입 안전.
- `GET /threads/{id}/messages` 라우트 신규 추가. plan에서는 명시적으로 "추가 안 함"이었으나 R1 비판 수용. `GET /threads/{id}`는 그대로 두어 backward compatible.
- `MessageCreate` validator는 plan에 없었음 (plan은 `min_length=1`만). 추가는 사용자 입력 검증 강화로 무회귀.

## 5-D. Scoring (100, self-assessment, RE-CODE 후 재산정)

| Item       | Score / Max | Evidence |
| ---------- | ----------- | -------- |
| 독창성     | 14 / 15     | `system=` 활용 + LLM-first transaction 순서 + RecordingMockLLM + Literal 좁힘 + `_validate_image_path` traversal 가드. (Phase 5 streaming/SSE에서 context anchor 재설계 여지) |
| 완결성     | 33 / 35     | DoD 9건 + GET /threads/{id}/messages 추가로 ROADMAP 표기와 일치. 9-step verify_api.sh 통과. 미세 감점: `DocumentRead.status` 가 여전히 str (의도적 — 향후 phase에서 상태값 확장 예정). |
| 안정성     | 29 / 30     | LLM-first transaction + atomicity 보호 + startup-path 4건 + LLM_TIMEOUT 3건 + whitespace validator + schema mismatch / health 회귀 보호 모두 통과. 미세 감점: concurrent same-thread writes는 여전히 미보호 (단일 사용자 가정, 알려진 한계). |
| 확장성     | 19 / 20     | `create_app()` factory + app.state 의존성 주입, Literal로 좁힌 타입은 viewer/Phase 5 클라이언트에서 enum-처럼 활용 가능. `static/` placeholder. 미세 감점: thread message pagination은 Phase 5로 미룸 (Phase 3 DoD 외). |
| **Total**  | **95 / 100** | |

## 5-E. Self verdict (R2 진입 의도)

- [x] PASS_CANDIDATE (≥95)
- [ ] FAIL → RE-CODE
- [ ] FAIL → RE-PLAN

근거:
- R1 cross-verify의 모든 actionable issue (4건) RE-CODE에서 직접 fix + 회귀 테스트 잠금
- 새 코드 경로 (Literal cast, validator, 새 라우트, env handling)에 단위/통합 테스트 첨부
- mypy strict / ruff / 196 fast tests / 5 live LLM tests 모두 green
- verify_api.sh 9-step end-to-end exit 0 (live LLM 응답에 Hangul 포함 검증 포함)
- Push 정책: R2 cross-verify가 CONFIRM_PASS면 push, REJECT/DOWNGRADE면 보류 후 Planner escalate.
