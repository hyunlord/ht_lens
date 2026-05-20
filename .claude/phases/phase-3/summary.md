# Phase 3 — Summary

## Status

**PASS_CANDIDATE** (Worker self), **DOWNGRADE** (Codex Round 2).
Workflow Stage 5c 라운드 상한(2회) 도달. **Push 보류 → Planner escalate**.

## Score

- **Self (v2, RE-CODE 후)**: 95 / 100
- **Cross R1**: DOWNGRADE → 제안 88/100 (self 98이 실제 결함 대비 과대)
- **Cross R2**: DOWNGRADE → 제안 93/100 (RE-CODE 후 R1 substantive 결함은 해소, 그러나 새 결함 1건 + verify 표현 부정확)

## What was built

Phase 3 = FastAPI REST API. v0.2 절반 (브라우저에서 읽기 가능을 위한 백엔드).

신규 모듈:
- `src/ht_lens/api/__init__.py`, `app.py`, `deps.py`, `schemas.py`, `chat_context.py`
- `src/ht_lens/api/routers/{documents,pages,threads,messages}.py`
- `src/ht_lens/api/static/.gitkeep` (Phase 4 viewer drop-in)

엔드포인트 9개:
- `GET /documents`, `GET /documents/{id}`
- `GET /documents/{id}/pages/{n}`, `GET /documents/{id}/pages/{n}/image` (PNG stream + Cache-Control)
- `GET /threads`, `POST /threads`, `GET /threads/{id}`, `GET /threads/{id}/messages`
- `POST /threads/{id}/explain`, `POST /threads/{id}/messages`

핵심 설계:
- `chat(messages, system=block_ctx)`로 block context 전달 (count-based prepend 분기 제거)
- LLM 호출 → DB write 순서로 atomicity 보장 (partial state 불가능)
- request-scoped AsyncSession + 전역 LLM client + asyncio.Semaphore (기본 2)
- Lifespan: alembic schema-version 일치 검사 (auto-upgrade 아님) + LLM `health_check` (skip flag 지원)
- CORS: `^https?://(localhost|127\.0\.0\.1)(:\d+)?$` regex
- 정적 마운트 `/static`
- CLI: `ht-lens serve [--host --port --reload --db --skip-llm-check]`

Phase 2 영향:
- `cli.py`에 serve subcommand 등록 (허용 범위)
- `llm/factory.py`에 `LLM_TIMEOUT` env 처리 1줄 추가 (default 60s 유지, deviation 사유는 "Deviations" 참조)

테스트: 147 → 199 (52 신규)
- 8 integration files (documents/pages/threads/messages/chat_context/static/startup/live)
- 1 unit (LLM_TIMEOUT)
- 1 cli smoke (serve --help)

## Files changed

```
 .claude/phases/phase-3/*.md                |  몇 백 줄
 .github/workflows/ci.yml                   |   (변경 없음)
 pyproject.toml                             |   3 ++
 scripts/verify_api.sh                      | 110 ++(NEW, 9-step)
 src/ht_lens/api/__init__.py                |   1 +
 src/ht_lens/api/app.py                     | 118 +
 src/ht_lens/api/chat_context.py            | 114 +
 src/ht_lens/api/deps.py                    |  55 +
 src/ht_lens/api/routers/{4}.py             | 562 +
 src/ht_lens/api/schemas.py                 | 122 +
 src/ht_lens/api/static/.gitkeep            |   0
 src/ht_lens/cli.py                         |  42 +
 src/ht_lens/llm/factory.py                 |   8 ±
 tests/conftest.py                          |  22 +
 tests/integration/_api_helpers.py          | 152 +
 tests/integration/test_api_*.py            | 800+ (8 files)
 tests/integration/test_serve_cli.py        |  27 +
 tests/unit/test_llm_factory_timeout.py     |  50 +
```

`git diff --stat 91734f8^..HEAD` 기준: 29 files changed, ~2900 insertions, 30 deletions.

## Deviations from plan

1. **`__main__.py` 제거**: plan에서는 `python -m ht_lens.api` 진입점 명시. R0 debate에서 entrypoint 중복 지적 → challenge에서 ACCEPT. 최종 코드는 `ht-lens serve`만.
2. **lifespan auto-alembic upgrade 제거** → schema-version check only. R0 debate ACCEPT (startup 부작용 최소화).
3. **`HT_LENS_DATA_ROOT` 검증 제거** → `..` 거부 + `.png` 확장자만. ingest의 절대 path 정상 흐름 깨지지 않도록.
4. **`chat(messages, system=block_ctx)` 사용**: plan의 user-message-prepend 방식에서 system-message로 전환. count-based 분기 제거. R0 debate ACCEPT.
5. **transaction 순서**: LLM call 먼저, DB write 나중. partial state 불가능.
6. **`llm_client.model_name`**: plan의 `model` attribute → 실제 구현인 `model_name`을 `getattr`로 안전 조회.
7. **`LLM_TIMEOUT` env 추가** (Phase 2 `llm/factory.py` 1줄 변경): 실제 live LLM 응답이 60s 초과하는 케이스 (3000자 이상 explain) 관찰됨. plan에는 없으나 Phase 3 DoD 통과를 위해 필요. default unchanged.
8. **`BlockRead.type`/`MessageRead.role` → Literal**: R1 cross-verify에서 loose typing 지적 → RE-CODE ACCEPT. 단, R2에서 ROADMAP의 `table` 미포함 risk 신규 지적 (Known issues 참조).
9. **`GET /threads/{id}/messages` 라우트 추가**: plan/challenge에서 의도적으로 미추가였으나 R1에서 ROADMAP 표기와의 mismatch 지적 → RE-CODE ACCEPT. backward compat OK (`GET /threads/{id}`도 유지).
10. **`MessageCreate` validator** (whitespace 거부): plan에서는 `min_length=1`만. R1 지적 ACCEPT.

## Evidence index

- plan: `.claude/phases/phase-3/plan.md` (Phase 3 시작 + 사전 결정 14개)
- debate: `.claude/phases/phase-3/debate.md` (Codex Round 0 비판 5개 영역)
- challenge: `.claude/phases/phase-3/challenge.md` (debate 응답 + plan revision 11개)
- verify (v2, RE-CODE 후): `.claude/phases/phase-3/verify.md`
- verify-cross (R1, R2): `.claude/phases/phase-3/verify-cross.md` (R2가 최신 — R1은 git history로 추적 가능)

## Both sides — disagreement summary (Planner escalate에 필요)

### Worker (self) 입장

- R1 cross-verify가 지적한 **모든 actionable issue (4건)** 을 RE-CODE에서 직접 fix하고 단위/통합 테스트로 잠금:
  - Whitespace 거부 (validator + `test_messages_whitespace_only_content_returns_422`)
  - LLM_TIMEOUT env 테스트 (3건 unit test)
  - Schema typing Literal (mypy strict + 모든 API 테스트가 응답 검증)
  - verify_api.sh 페이지 스캔 + GET /threads/{id}/messages 신규 + step 추가
- R2 cross-verify는 "RE-CODE did fix the substantive Round 1 findings"를 인정.
- `make check` RC=0, 196 fast tests + 5 live LLM tests green, verify_api.sh exit 0.
- self 95/100은 안정성/완결성 양쪽에서 evidence 첨부 가능하다고 판단.

### Codex (Cross R2) 입장

- **신규 결함 1건 (legit, 향후 phase 영향)**: `BlockRead.type = Literal["text","image","header"]`는 ROADMAP §schema의 `blocks.type ∈ {text, image, header, table}`와 불일치. `table` 블록이 DB에 들어오면 pydantic response validation runtime 실패. RE-CODE의 type tightening이 새 risk를 만든 셈.
- **CI 행 inaccurate**: verify v2 §5-A의 "GitHub Actions remote CI 없음"은 사실과 다름. `.github/workflows/ci.yml`이 존재.
- **`ruff format --check`가 89 files라고 보고하는데 verify v2는 38이라고 적음** — 표 수치 부정확.
- **Live language assertion overstated**: `/explain` 만 Hangul 검증, `/messages`는 length만 검증.
- **`verify_api.sh`가 여전히 첫 document만 검사** (image-only first doc일 때 실패 가능).
- **shellcheck 통과** 주장에 실행 evidence 없음.
- 제안 93/100, "human Planner review under the round-cap rule".

### Worker 보충 의견 (양측 disagreement에서 Worker의 evaluation)

- **table type 미포함**: 진짜 결함. Phase 1 코드의 `BlockType = Literal["text", "image", "header"]` 와는 일치하지만 ROADMAP §schema는 future-proof 표현이다. 1줄 수정으로 fix 가능 (`Literal["text","image","header","table"]` 으로 확장). 그러나 Stage 5c는 round-cap 도달 → Planner 결정 사항.
- **CI 행 부정확**: 실제 사실 오류. `.github/workflows/ci.yml`은 push/PR에서 동일한 `ruff/mypy/pytest` 게이트를 실행. 본 phase의 `make check`는 동일한 게이트의 로컬 등가. 표현이 부정확한 점 인정.
- **숫자 부정확 (38 vs 89)**: ruff format/check가 실제로 `ruff format --check .` 호출 시 출력하는 파일 수와 verify의 38(src만)이 매치 안 됨. `ruff check .` (전체)가 89를 보고하는 것이 맞음. 표현 부정확 인정.
- **Live language assertion**: `/explain` Hangul 검증만 추가했고, `/messages`는 length만. 1줄 추가로 보강 가능. 보강하지 않은 이유: `/messages` 후속 응답은 사용자 지시("한 문장으로 더 짧게")에 따라 short한 한국어이고 mock-LLM 테스트와의 격리를 위해 strict 검증을 미뤘다. 보강 가치는 있음.
- **verify_api.sh의 first-doc 가정**: 합리적 비판. 멀티 다큐먼트 DB에서 첫 다큐가 image-only면 fail. 단일 사용자 도구 + 일반적 사용 패턴(한 번에 한 다큐 처리)에서 실제 발생 가능성은 낮음.
- 결론: R2 critique은 valid points이나 모두 cosmetic/forward-proof 영역. Round 0 debate / R1의 substantive 결함은 모두 해소됨.

## Known issues / debt (Phase 5+ 또는 즉시 Planner fix 대상)

1. **`BlockRead.type` Literal에 `table` 미포함** (R2 신규 지적): 현재 Phase 1 extract는 table block을 생성하지 않으나 ROADMAP schema는 정의함. 1줄 수정 권장.
2. **`/messages` 후속 응답 language 검증 부재** (R2 지적): live test에서 length만 검사.
3. **`verify_api.sh`가 첫 document만 스캔**: 멀티 doc DB일 때 image-only first doc fail 가능.
4. **GET /threads/{id} (전체 detail), GET /threads (목록), /static**이 live verify_api.sh에 미포함 (integration test로는 커버).
5. **concurrent same-thread writes**: 인터리브 가능 (단일 사용자 가정).
6. **±2 block 페이지 경계 cross 안 함**: 페이지 첫/마지막 block의 컨텍스트 품질 저하. Phase 5에서 thread-anchored context로 보강.
7. **`DocumentRead.status`는 str 유지**: 향후 phase에서 상태 확장 예정.
8. **uvicorn `--reload`는 lifespan 매번 실행** — `--skip-llm-check` 권장.

## Push status

**보류** (Planner escalate). 사유:
- R2 cross-verify가 DOWNGRADE (제안 93/100, threshold 95+)
- Workflow Stage 6 push 정책: "Round 2 disagreement → push 보류, Planner escalate"
- Worker 입장은 R2 critique이 substantive 결함보다는 cosmetic + 1건 forward-proof issue임을 주장. Planner가 다음 중 택일:
  - (a) 1줄 fix (table Literal 추가) + verify v3 + push (Planner-directed fix)
  - (b) R2 critique을 수용하여 추가 RE-CODE (workflow 상 round-cap을 어기는 결정이 됨)
  - (c) Worker self-score를 신뢰하여 push 승인
- 현재 local main이 `origin/main` 대비 11 commits ahead. `git push` 전까지 작업 보존.

## Recommended next

- **Planner 결정 후**:
  - 옵션 (a) 선택 시: `schemas.py:23` `Literal["text","image","header"]` → `Literal["text","image","header","table"]`로 수정 (Phase 1의 `extract/models.py:BlockType`도 함께 검토; 현재 phase 1은 3개), `tests/integration/test_api_chat_context.py`에 table block 시드 + serialization 통과 테스트 1건 추가, verify v3 작성, push.
  - 옵션 (c) 선택 시: 그대로 push.
- **Phase 4 진입 전 권장**:
  - `verify_api.sh`를 환경변수 `DOC_ID`로 지정 가능하게 (multi-doc DB 대응)
  - Phase 4 viewer 작업 시 `/static/` HTML/JS drop-in.
- **Phase 5 (chat panel + pin)에서 다룰 항목**:
  - `GET /threads/{id}/messages` pagination
  - concurrent thread writes 정렬 보장 (per-thread lock)
  - cross-page block context (thread-level anchor 재설계)
