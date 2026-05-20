# Phase 3 — Verify (self)

`git status` clean 확인 후 작성. 본 verify는 `bb6cabe` (head)에 대한 1차 self-evaluation.

## 5-A. Automated checks

| Check    | Command | Result |
| -------- | ------- | ------ |
| Lint     | `uv run ruff check .` | All checks passed! (0 errors, 38 files) |
| Format   | `uv run ruff format --check .` | 38 files already formatted |
| Type     | `uv run mypy src/` | Success: no issues found in 49 source files |
| Test (fast) | `make test-fast` → `uv run pytest -m "not llm"` | **190 passed, 5 deselected** in 71.74s |
| Coverage | included in pytest run | TOTAL 74% (1629 statements, 395 missed). Phase 3 deltas covered; live-LLM 진입점 비커버는 `-m llm` 경로. |
| Test (llm)  | `uv run pytest -m llm` (with `LLM_*` env) | **5 passed, 190 deselected** in 104.17s |
| CI (local) | `make check` | RC=0 (`ruff format --check`, `ruff check`, `mypy strict`, `pytest -m "not llm"`) |

상세:
- 새 추가 테스트 43건 (139 → 190 — phase 2 base 147 → 190 +43).
- `make check` 종료 코드 0.
- 새 dep `fastapi>=0.115,<1`, `uvicorn[standard]>=0.32,<1`만 추가. pyproject 확인.

## 5-B. Functional checks

### 1) End-to-end 데이터 흐름 (extract → ingest → translate → API)

DB: `/tmp/ht_lens_phase3.db`. Fresh alembic upgrade head → extract `tests/fixtures/sample_mixed.pdf` → ingest `--src en` → translate live sglang.

```
extract: ok: pages=6 lang=mixed
ingest:  ok: doc_id=1 pages=6 blocks=102
translate: ok: doc_id=1 translated=92 cached=4 skipped=6 failed=0
```

### 2) `scripts/verify_api.sh` (live LLM)

Server: `ht-lens serve --port 8093 --db /tmp/ht_lens_phase3.db` with `LLM_TIMEOUT=300`, `LLM_PROVIDER=openai_compat`, `LLM_BASE_URL=http://localhost:8081/v1`, `LLM_MODEL=qwen3.6-27b`.

```
[1/7] GET /documents                              doc_id=1 count=1
[2/7] GET /documents/1/pages/1                    blocks=37
[3/7] GET /documents/1/pages/1/image              png bytes=291676
[4/7] POST /threads (block_id=2)                  thread_id=3
[5/7] POST /threads/3/explain                     explain len=3105
[6/7] POST /threads/3/messages                    followup len=86
[7/7] GET /threads/3                              messages=4 roles=user,assistant,user,assistant

verify_api.sh OK   (exit 0)
```

서버 access log 발췌:
```
"GET /documents HTTP/1.1" 200 OK
"GET /documents/1/pages/1 HTTP/1.1" 200 OK
"GET /documents/1/pages/1/image HTTP/1.1" 200 OK
"POST /threads HTTP/1.1" 201 Created
"POST /threads/3/explain HTTP/1.1" 202 Accepted
"POST /threads/3/messages HTTP/1.1" 202 Accepted
"GET /threads/3 HTTP/1.1" 200 OK
```

### 3) Integration test 전수 (mock LLM)

`uv run pytest -m "not llm"` → 190 passed. Phase 3 신규 43건 분포:

- `test_api_documents.py` (4): list / by-id / status filter / 404
- `test_api_pages.py` (8): blocks / 404 doc / 404 page / PNG stream + cache header / 절대경로 ingest 경로 serving / 파일 누락 500 / traversal 500 / bbox list-of-floats
- `test_api_threads.py` (7): default-title / custom-title / 404 block / doc_id filter / 404 missing / detail with ordered messages / summary message_count
- `test_api_messages.py` (10): explain user+assistant / non-idempotent / history 전달 / first-call raw user content / 502 transient / 502 permanent / **atomicity (LLM 실패 시 row 없음)** / **retry still has block context** / 404 thread / 422 empty content
- `test_api_chat_context.py` (7): center window / first-block left truncate / last-block right truncate / radius=0 / 번역 없음 fallback / image block 빈 라벨 / unknown block raises
- `test_api_startup.py` (4): skip flag / unhealthy LLM aborts / health=False aborts / schema mismatch aborts
- `test_api_static.py` (2): `.gitkeep` 200 / unknown 404
- `test_serve_cli.py` (1): `ht-lens serve --help` 등록 + 옵션 확인

### 4) LLM live tests

`uv run pytest -m llm` (with LLM_* env + LLM_TIMEOUT=300):
- `test_api_live_llm.py::test_explain_and_followup_returns_korean_text` PASS (94.7s)
- 그리고 Phase 2b의 4개 LLM 테스트 (`health_check_live`, `translate_pipeline_live`)도 동시 통과 (합계 5 passed, 104s).

### 5) API spot-check (skip-llm-check 서버 + jq)

```
GET /documents               → length=1, doc_id=1, num_pages=6
GET /documents/1/pages/1     → page_num=1, blocks=37,
                                first.original_text[:50]="Open-Sora 2.0: Training a Commercial-Level Video\nG"
GET /threads                  → length=3 (verify_api.sh 시나리오 3회 누적)
```

### 6) Async 일관성 검증 (grep)

- `src/ht_lens/api/routers/*.py` 모든 endpoint handler가 `async def`.
- DB 호출은 `await session.execute(...)`, `await session.commit()`, `await session.refresh()`.
- LLM 호출은 `await llm.chat(...)`.
- lifespan은 `@asynccontextmanager`로 정의됨. uvicorn ASGI lifespan-spec 준수.

### 7) Pydantic schema 분리 검증

`src/ht_lens/api/schemas.py`에 9개 Read/Create 모델 (DocumentRead, BlockRead, PageRender, PageRead, MessageRead, ThreadSummary, ThreadDetail, ThreadCreate, MessageCreate) 별도 정의. `db/models.py`의 ORM과 명시적으로 다른 파일. router는 ORM → schema 매핑을 명시적으로 수행.

### 8) Regression check

Phase 3는 RE-CODE 라운드가 아닌 1차 verify이므로 RE-CODE regression 가드는 적용되지 않음. 단:
- Phase 2 코드 임의 수정은 다음 한 곳뿐: `src/ht_lens/llm/factory.py`에 `LLM_TIMEOUT` env 처리 (default 60s 유지, 비-set 환경에서 무회귀). 동기: Phase 3 DoD live scenario에서 `/explain` 응답이 60s 초과하는 케이스가 관찰됨. plan에서 결정된 `chat(..., system=)` 호출 시 응답이 길어지는 일반적 현상이므로 operational knob 필요. summary.md에 deviation 명시.
- Phase 1/2 테스트 (147건) 전수 회귀 없이 통과. `test_alembic.py`, `test_translate_pipeline_*`, `test_health_check_live` 통과.

## 5-C. Scoring (100, self-assessment)

| Item       | Score / Max | Evidence |
| ---------- | ----------- | -------- |
| 독창성     | 14 / 15     | `system=` 활용 + LLM-first transaction 순서 + RecordingMockLLM (테스트가 chat 호출 인자를 직접 검증) + `_validate_image_path` traversal 가드. 한 가지 감점: `chat(..., system=block_ctx)` 매 호출마다 컨텍스트 재전송은 토큰 효율 측면에서 미세하게 비효율. Phase 5에서 streaming + thread-anchored context 도입 시 개선. |
| 완결성     | 34 / 35     | DoD 9 항목 모두 evidence 첨부 (mock + live 양쪽). verify_api.sh 7단계 모두 통과. live test + spot-check 모두 정상. 한 가지 감점: `GET /threads/{id}/messages` 별도 endpoint는 Phase 5로 의도적 보류 (challenge.md에서 명시) — DoD 자체에는 없지만 ROADMAP 표기와 다소 다른 해석. |
| 안정성     | 30 / 30     | LLM-first transaction 순서로 partial state 불가능 (`test_messages_does_not_persist_partial_user_row_on_llm_failure` 통과). startup-path 4건 (skip / unhealthy / health=False / schema mismatch) 모두 회귀 보호. traversal/empty/missing PNG → 500 일관. `LLMError → 502` 매핑 일관. SchemaVersionMismatch on startup. CORS regex localhost 한정. async session request-scoped. semaphore (기본 2)로 LLM endpoint 보호. |
| 확장성     | 20 / 20     | `create_app()` factory + `app.state` 의존성 주입 → 멀티 테스트/멀티 환경 격리. routers 4개로 모듈 분리 → Phase 4/5에 라우터 추가 시 충돌 없음. `static/` 디렉토리 placeholder → Phase 4 viewer drop-in. `dependency_overrides[get_llm_client]` 테스트 패턴 → Phase 5 streaming도 동일 패턴. `LLM_TIMEOUT` env → 다양한 endpoint 운영 환경 대응. |
| **Total**  | **98 / 100** | |

## 5-D. Self verdict

- [x] PASS_CANDIDATE (≥95)
- [ ] FAIL → RE-CODE
- [ ] FAIL → RE-PLAN

근거 요약:
- `make check` RC=0, 190 fast tests + 5 LLM tests 모두 통과
- `scripts/verify_api.sh` exit 0 (end-to-end)
- DoD 9개 항목 evidence 100%
- 알려진 한계 (concurrent thread writes, ±2 page-boundary, GET /threads/{id}/messages 별도 endpoint 부재) 모두 challenge.md / summary.md에 명시 예정
- Phase 2 코드 1줄 추가 변경 (LLM_TIMEOUT env) → 정당화 명확, 무회귀, summary.md에 deviation 기재
