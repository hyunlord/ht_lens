# Phase 3 — Challenge

## Debate responses

### 1. Over-engineering

**lifespan에 alembic + LLM health 묶음** — **PARTIAL accept (큰 변경)**
Codex 주장: Phase 3 DoD에는 REST endpoint + async + schema 분리 + `/static`만 필요. lifespan에서 DB mutation은 운영 정책.
응답: alembic auto-upgrade는 reload 시 race + 테스트 setup 복잡도 → **제거**. 대신 lifespan에서 `current_schema_version()`을 호출하여 `ALEMBIC_HEAD`와 비교, 다르면 `SchemaVersionMismatch`로 startup abort. 운영자는 `ht-lens` CLI 다른 부분과 동일하게 `alembic upgrade head` 수동 실행. LLM health_check는 그대로 유지 (DoD: "AI 응답"이 통과하려면 startup 시 endpoint 가용성을 확인하는 게 합리적, skip flag 있음).
**결정**: alembic auto-upgrade 제거. schema-version 일치 검사로 대체. LLM health_check 유지.

**두 개의 entrypoint (`ht-lens serve` + `python -m ht_lens.api`)** — **ACCEPT**
Codex 주장: option parsing/실패 모드 중복.
응답: `ht-lens serve` 하나로 통일. `src/ht_lens/api/__main__.py`는 이번 phase에서 추가 안 함. `python -m ht_lens.api` 진입은 Phase 4 이후 필요 시 도입.
**결정**: `__main__.py` 제거. file-level changes에서 빼고 test도 줄임.

**`uvicorn[standard]` extras** — **REJECT**
Codex 주장: 부가 의존성.
응답: `--reload`가 watchfiles를 필요로 하며 dev 환경에서 표준 옵션. `[standard]`는 widely-recommended. 유지.

**`LLM_CHAT_CONCURRENCY` semaphore** — **REJECT**
Codex 주장: 핵심 contract 아님.
응답: 단일 사용자라도 explain+messages 동시 호출 가능 (브라우저 다중 탭). LLM endpoint를 보호하는 작은 한도(기본 2)는 비용 거의 0. 유지.

**`HT_LENS_DATA_ROOT` env** — **ACCEPT (다른 형태)**
Codex 주장: 부가 의존성. **§2의 bg_image_path 절대경로 문제와 연계**.
응답: env 자체는 단순하지만, 실제 ingest path는 임의(`tests/fixtures/...`, `/tmp/...`)이므로 root 기반 검증은 false positive 위험. **DATA_ROOT 제거하고**, 이미지 endpoint는: (a) 파일 존재 확인, (b) `.png` 확장자, (c) `..` segment 거부, (d) symlink resolve 후 그대로 serve. 단일 사용자 도구에서 DB write 권한이 곧 신뢰 경계이므로 이만큼이면 충분.
**결정**: `HT_LENS_DATA_ROOT` 제거. 단순 파일 존재 + 확장자 + `..` 거부만.

**`/docs` Swagger** — **REJECT**
근거: 비용 0, 디버깅 가치 큼.

**`/static/.gitkeep` mount** — **REJECT**
근거: Phase 4 viewer 진입을 위한 placeholder. 비용 1줄.

### 2. Hidden assumptions

**`Page.bg_image_path`가 `data/` 안에 있다고 가정** — **ACCEPT (중대 버그)**
Codex 주장: ingest는 `ht-lens extract -o /tmp/out` 출력의 절대경로를 그대로 저장. `HT_LENS_DATA_ROOT` 검증으로는 정상 흐름이 500을 받음.
응답: §1의 DATA_ROOT 제거 결정으로 해결. 정상 ingest 경로의 파일을 그대로 serve.
**결정**: data-root 검증 삭제. test_page_image_serves_ingested_absolute_path 추가 (실제 ingest 경로 그대로 serving).

**`llm_client.model` attribute 사용** — **ACCEPT (중대 버그)**
Codex 주장: 실제로는 `model_name`이고, `LLMClient` Protocol에는 attribute 자체가 없음.
응답: `getattr(llm, "model_name", "unknown")`으로 안전하게 읽음. `MockLLMClient.model_name = "mock"`이고 `OpenAICompatibleClient.model_name = self._model` (Phase 2b에서 기설치). plan revision에 반영.
**결정**: `Message.model = getattr(llm, "model_name", "unknown")`.

**`GET /threads/{id}/messages` 부재** — **PARTIAL accept**
Codex 주장: roadmap이 `/threads/{id}/messages`를 deliverable로 명시.
응답: prompt §"API 엔드포인트 명세"에서 `POST /threads/{thread_id}/messages` 만 정의됨. roadmap의 항목은 _리소스_ 표기이며 method는 prompt가 fix. `GET /threads/{id}`가 messages 전체 동봉 → 분리된 GET 불필요. Phase 5 pagination에서 별도 endpoint 검토. 다만 challenge.md에 명시적 인용으로 의도 못 박음. **plan은 변경 없음.**
**결정**: `GET /threads/{id}/messages` 추가 안 함. `GET /threads/{id}`가 messages 동봉으로 충당. test에서 "thread GET 응답이 messages를 순서대로 포함"을 명시 검증 (Codex 제안 채택).

### 3. Edge cases

**transaction 경계: user row를 LLM call 전에 쓰면 partial state** — **ACCEPT (중대)**
Codex 주장: `/explain`, `/messages` 모두 user → assistant 흐름에서 LLM 실패 시 user-only row가 남으면 `_should_prepend_block_context(count==0)` 영구히 False로 깨짐. block context가 다시 안 들어감.
응답: **LLM 호출이 먼저, 그 다음 user + assistant 두 row를 한 transaction에 commit**. LLM 실패 시 어떤 row도 안 남음. 부가 효과로 prepend 결정도 안전.
**결정**: 모든 router에서 순서는 (1) build context → (2) LLM chat 호출 → (3) user + assistant row 한꺼번에 `session.add_all([...]); await session.commit()`.

**§4의 `system=` 도입과 결합한 단순화**: block context는 LLM 호출에 `system=` 인자로 전달. user message는 사용자 raw 입력만. DB에는 raw user input + assistant 응답만 저장. `_should_prepend_block_context` 함수 제거. count-based 분기 자체가 사라짐. 자연스러운 깔끔한 모델.

**concurrent thread writes (interleave)** — **REJECT (문서화)**
Codex 주장: 동시 호출 시 user-user-assistant-assistant 가능.
응답: 단일 사용자 도구. Phase 5+ pinning UI에서도 동시 호출이 잘 일어나는 시나리오는 드뭄. test로 검증할 수단도 불명확. 알려진 한계로 문서화.

**±2 block 페이지 경계 cross 안 함** — **REJECT (문서화)**
Codex 주장: 페이지 첫/마지막 block은 컨텍스트 품질 저하.
응답: 페이지 cross는 reading order 일관성을 깸 (Phase 1 reading_order는 페이지 내부만 정의). PDF 페이지는 시각적/문서적 단위라 cross-page context는 noise일 가능성이 높음. Phase 5에서 thread-level context로 보강. 알려진 한계로 문서화.

**empty header/table block fallback** — **PARTIAL accept**
Codex 주장: image 외 type도 빈 content 가능.
응답: type 분기 대신 `original_text.strip() == ""` 일반 fallback: `"[빈 {type} 블록]"`. test 추가.
**결정**: empty 일반화.

### 4. Alternative approaches

**`LLMClient.chat(..., system=...)` 활용** — **ACCEPT (큰 변경)**
Codex 주장: prepend hack 없이 system message로 block context 전달.
응답: 채택. Phase 2b의 `chat` 시그니처가 이미 `system=` 지원. 효과:
- DB user row는 raw 사용자 입력만 (clean)
- count-based 분기 제거
- `/explain`은 `chat(messages=[{role:user, content: 설명 prompt}], system=block_ctx)` + 응답 받아서 (user, assistant) 두 row 저장
- `/messages`는 thread history를 `messages=[]`에 넣고 `system=block_ctx` 매번 (block context는 thread의 anchor이므로 매 호출 prepend OK; 사용자 raw input 중복 prepend 문제 없음)

**plan §1, §2, §3에 cascading 영향**: prepend 함수 제거, 첫 호출 분기 제거, system param 모든 chat 호출에 일관 사용.

**alembic skip + schema-version check** — **ACCEPT (§1과 동일)**

**`httpx.AsyncClient` + `ASGITransport`** — **REJECT**
Codex 주장: TestClient가 async boundary masking.
응답: FastAPI 공식 권장은 TestClient. async route는 starlette TestClient 내부에서 asyncio loop로 정상 실행됨. `system=` async test도 TestClient로 검증 가능. 복잡도 증가 정당화 안 됨.

### 5. Missing tests

**startup-path tests** — **PARTIAL accept**
- `test_app_startup_fails_on_llm_health_check`: ACCEPT (mock LLM이 `LLMHealthCheckFailed` raise, startup fail 확인)
- `test_app_startup_skips_llm_check_with_flag`: ACCEPT (env로 skip 확인)
- `test_app_rejects_schema_mismatch`: ACCEPT (DB의 alembic_version을 가짜 값으로 두고 startup fail)
- alembic upgrade 자동실행은 제거되므로 그 케이스는 빠짐.

**`test_page_image_serves_ingested_absolute_path`** — **ACCEPT**
실제 ingest 경로의 PNG를 200으로 받는 happy-path 추가.

**history atomicity tests** — **ACCEPT (구조 변경 후 더 단순)**
- `test_messages_does_not_persist_partial_user_row_on_llm_failure`: LLM 실패 시 messages count 그대로 (user row 없음).
- `test_explain_retry_still_includes_block_context_after_failed_first_attempt`: 첫 실패 후 재호출도 system=block_ctx로 정상 동작 (system=은 매번 prepend되므로 trivial pass; 그래도 회귀 보호로 추가).

**CLI coverage** — **PARTIAL accept**
- `test_ht_lens_serve_respects_db_option`: ACCEPT — typer registration + `--help`/option parsing smoke (실제 startup은 안 함, lifespan 비싸므로 import-level만).
- `test_python_m_ht_lens_api_starts`: REJECT — `__main__.py` 자체를 안 만드므로 해당 없음.

**`test_get_thread_returns_messages_in_order`** — **ACCEPT**
`GET /threads/{id}` 응답이 messages를 created_at(or id) 오름차순으로 동봉.

---

## Plan revisions (after debate)

1. **alembic auto-upgrade 제거** → schema-version 검사 only. `SchemaVersionMismatch`로 startup abort.
2. **`__main__.py` 제거** → `ht-lens serve`만 entrypoint.
3. **`HT_LENS_DATA_ROOT` 검증 제거** → 파일 존재 + `.png` 확장자 + `..` 거부만.
4. **`llm_client.model` → `getattr(llm, "model_name", "unknown")`**.
5. **transaction 순서**: build_context → LLM chat → (user + assistant) 한 transaction에 commit. partial state 불가능.
6. **block context 전달**: `chat(messages=history+new_user, system=block_ctx)` 매 호출에 적용. count-based prepend 분기 제거.
7. **`/explain`은 messages 2건**: (user="…설명해주세요…" prompt, assistant=응답) — system은 block context.
8. **빈 block 일반 fallback**: `"[빈 {type} 블록]"`.
9. **테스트 추가 7개**:
   - `test_app_startup_fails_on_llm_health_check`
   - `test_app_startup_skips_llm_check_with_flag`
   - `test_app_rejects_schema_mismatch`
   - `test_page_image_serves_ingested_absolute_path`
   - `test_messages_does_not_persist_partial_user_row_on_llm_failure`
   - `test_explain_retry_still_includes_block_context_after_failed_first_attempt`
   - `test_get_thread_returns_messages_in_order`
10. **CLI smoke test**: `test_ht_lens_serve_help_lists_options` (import-level, startup 안 함).
11. **알려진 한계 문서화**: concurrent thread writes, ±2 page-boundary degradation → summary.md "Known limitations"에 명시.

---

## DoD checklist

| DoD item | Status | Evidence |
| -------- | ------ | -------- |
| httpie/curl 시나리오 통과 | planned | `scripts/verify_api.sh` exit 0 |
| async 일관 | planned | router 전부 `async def`, await on AsyncSession + LLM |
| pydantic schema 분리 | planned | `api/schemas.py` Read/Create 모델 |
| 정적 파일 마운트 `/static` | planned | `test_api_static.py` |
| 채팅 컨텍스트 ±2 block | planned | `test_api_chat_context.py` + `test_api_messages.py` system msg 캡처 |
| `/image` PNG stream | planned | `test_api_pages.py` content-type, Cache-Control 검사 |
| mypy strict 0 | planned | `uv run mypy src/` 0 errors |
| ruff clean | planned | `uv run ruff check .` 0 errors |
| 147 기존 테스트 무회귀 | planned | `make test-fast` green |

---

## Risk register

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| LLM 호출 실패로 thread 상태 깨짐 | Low (구조 변경 후) | History 오염 | LLM call 먼저, DB write는 atomic 1번 |
| schema version 불일치로 startup fail | Low | 서버 미가동 | 에러 메시지에 `alembic upgrade head` 안내 |
| bg_image_path 검증 약화로 LFI 위험 | Low | 임의 file leak | `..` 거부 + `.png` 확장자 + DB write 권한이 trust boundary |
| TestClient + lifespan 충돌 | Low | 테스트 flaky | `with TestClient(app) as client` context로 lifespan 명시 실행 |
| Concurrent same-thread writes interleave | Low | history 순서 깨짐 | 단일 사용자 가정, 문서화 |
| ±2 page boundary degrade | Medium | context 품질 | 알려진 한계, Phase 5에서 thread-level context 보강 |
| `chat(..., system=)`이 thread history 매번 재전송 비용 | Low | token 비용 증가 | Phase 5 streaming/SSE 도입 시 재검토 |

---

## Decision

- [x] PASS → proceed to code (plan revisions 11개 적용하여 진행)
- [ ] RE-PLAN (reason: )

11개 수용 (6 큰 구조 변경 + 5 테스트/문서화), 4개 거부 (uvicorn extras, semaphore, ASGITransport, /docs, /static placeholder). 거부 항목은 모두 prompt-fixed이거나 비용 대비 가치 거의 0.
