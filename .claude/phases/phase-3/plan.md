# Phase 3 — Plan

## Goal

CLI 위에 FastAPI REST API를 올린다. `documents` / `pages` / `pages/{n}/image` / `threads` / `threads/{id}/explain` / `threads/{id}/messages` 엔드포인트와 ±2 block 컨텍스트 자동 구성으로, Phase 4 viewer가 그대로 붙을 수 있는 인터페이스를 v0.2 마일스톤 절반으로 완성한다.

## Scope

**In**
- `src/ht_lens/api/` 패키지 (`app.py`, `__main__.py`, `deps.py`, `schemas.py`, `routers/{documents,pages,threads,messages}.py`, `chat_context.py`, `static/.gitkeep`)
- `src/ht_lens/cli.py` — `serve` subcommand 추가 (그 외 손대지 않음)
- FastAPI lifespan: Alembic auto-upgrade + LLM `health_check()` (skip 플래그 지원) + engine init/dispose
- Pydantic schema (DB ORM과 분리)
- `/static/` 정적 마운트 (Phase 4용, 현재 placeholder)
- 페이지 PNG는 별도 endpoint (`/documents/{id}/pages/{n}/image`)로 stream + path traversal 방어
- 채팅 컨텍스트 빌더 (`build_block_context` ±2 block markdown)
- LLMClient singleton + asyncio.Semaphore 기반 chat concurrency 한도
- Integration test (TestClient + mock LLM) + `@pytest.mark.llm` live test
- `scripts/verify_api.sh` end-to-end 시나리오 (run_*는 수정 금지이므로 새 스크립트 추가)
- 새 dep: `fastapi>=0.115`, `uvicorn[standard]>=0.32` (pyproject `dependencies`에 추가)

**Out**
- Phase 4 viewer HTML/JS (`static/.gitkeep`만)
- Streaming/SSE/WebSocket (Phase 5)
- 인증/authorization (single-user)
- Phase 2 코드 본체 수정 (cli.py serve 등록 외)
- production hardening (CORS allow_origins 제한, OpenAPI 비공개화 등 → Phase 6)
- Multi-worker / process-level concurrency 보호 (single-user tool, single worker 가정)

## Approach

### 1. `/explain` 멱등성 (사전 결정사항 1)

**결정**: idempotency 강제하지 않음. 호출 시마다 새 `messages` 행 append.

- 이유: 사용자가 시간 흐름/모델 업데이트/주변 컨텍스트 변경 후 동일 block을 다시 설명받고 싶을 수 있음. 409 거부는 흐름을 막음.
- `/explain` 호출 1회 = `messages` 행 2건 (role=user content="위 단락을 자세히 설명해주세요. 핵심 개념, 배경 지식, 관련 용어를 포함해서." + role=assistant content=LLM 응답)
- 사용자 prefix를 DB에도 저장하는 이유: 후속 `/messages`가 thread history를 자연스럽게 이어가도록.

### 2. `/messages` 첫 호출 컨텍스트 (사전 결정사항 2)

**결정**: thread의 기존 messages 개수로 분기.

- thread messages 0개 → block context prepend (LLM 호출 시 첫 user 메시지 = `block_context_md + "\n\n" + 사용자 입력`)
- 1개 이상 → prepend 안 함 (이미 history 에 자연스럽게 들어 있음)
- prepend는 **LLM 호출 시점에만** 적용. DB에는 사용자 원본만 저장. 이유: history 재전송 시 중복 컨텍스트 방지.
- `/explain` 호출 후의 첫 `/messages`는 prepend 안 함 (이미 explain 단계에서 context prepend 완료).

구현: `_should_prepend_block_context(session, thread_id) -> bool`은 messages count == 0일 때만 True.

### 3. 에러 응답 형식 (사전 결정사항 3)

**결정**: FastAPI 기본 `{"detail": "..."}` 유지. 별도 schema 도입 안 함.

- 표준 코드:
  - 400: 명시 검증 실패 (예: block_id != document/page에 속하지 않음)
  - 404: not found (document/page/block/thread)
  - 422: pydantic validation (FastAPI 자동)
  - 500: 서버 오류 또는 path traversal 의심
  - 502: `LLMTransientError` (upstream)
- 409는 사용 안 함 (idempotency 강제 안 함).
- 503은 사용 안 함 (lifespan health_check 실패 시 startup 자체 abort → 서버 미가동).

### 4. DB session scope (사전 결정사항 4)

**결정**: request-scoped. FastAPI dependency.

- 전역 engine + sessionmaker는 lifespan에서 생성/dispose.
- request마다 `async with factory() as session: yield session` 으로 주입.
- transaction 경계: 한 endpoint = 한 request. router 내부에서 명시 commit (write 시).
- SQLite + aiosqlite는 단일 writer이므로 uvicorn workers > 1 가정하지 않음. CLI에서 `--workers` 옵션 노출 안 함.

### 5. LLMClient 동시 호출 한도 (사전 결정사항 5)

**결정**: `api.deps`에 `asyncio.Semaphore(LLM_CHAT_CONCURRENCY)` (env, 기본 2).

- Phase 2b `LLM_CONCURRENCY` (batch translate)와 다른 변수.
- semaphore acquire → LLM `chat()` 호출 → release.
- 초과 시 대기 (timeout 없음). LLM 응답 timeout은 OpenAI SDK 기본 60s 의존.
- `MessageRead.model`은 LLM client의 `.model` (mock은 "mock") 저장.

### 6. 페이지 image cache 헤더 (사전 결정사항 6)

**결정**: `Cache-Control: public, max-age=2592000` (30일). `immutable` 빼고 max-age만.

- 이유: bg_image_path는 ingestion 후 변경되지 않으나 re-ingest 가능성 0이 아님. `immutable`은 과한 약속.
- ETag/Last-Modified 추가 안 함.
- `FileResponse(path, media_type="image/png", headers={"Cache-Control": "public, max-age=2592000"})`.

### 7. OpenAPI 문서 (사전 결정사항 7)

**결정**: `/docs` (Swagger) + `/openapi.json` 노출. dev 도구이므로 위협 아님.

### 8. server lifecycle 로깅 (사전 결정사항 8)

**결정**: uvicorn 기본 + Python `logging.basicConfig(INFO)`. structlog 통합은 Phase 6.

- lifespan startup/shutdown은 `logging.getLogger("ht_lens.api").info(...)` 직접 emit.

### 9. path traversal 방어 (사전 결정사항 9)

**결정**: 이미지 endpoint는 DB의 `Page.bg_image_path`를 root 기준으로 검증.

- root: 환경변수 `HT_LENS_DATA_ROOT` (없으면 `Path("data").resolve()`).
- `Path(bg_image_path).resolve().is_relative_to(root)` 체크.
- 위반 또는 파일 부재 → 500 (DB 데이터 자체 문제, 클라이언트 input 무관이므로 400 아님).
- `..` 패턴 직접 검사도 추가.

### 10. 채팅 컨텍스트 빌더

```python
async def build_block_context(
    session: AsyncSession,
    block_id: int,
    *,
    radius: int = 2,
) -> str
```

알고리즘:
1. `Block`(+`Page` joinedload) fetch. 없으면 `ValueError`.
2. 같은 page의 모든 block을 `order_idx` ASC 정렬 fetch.
3. 현재 block의 index `i` 찾기. `[max(0, i-radius), min(len, i+radius+1))` 슬라이스.
4. 각 block의 `original_text` + `Translation.translated_text` (있으면) 출력.
5. 현재 block 줄에는 `→` 표시.

출력 markdown:

```
[Page {page_num}, Block {block_local_id}]
원문: {original}
번역: {translated_or_"(번역 없음)"}

주변 맥락 (±{radius} blocks):
{prev}
→ {current}
{next}

---
```

- 페이지 경계는 자동 slice로 처리.
- `radius=0`일 때는 "주변 맥락" 섹션 생략.
- image block의 original_text가 비어있으면 `[이미지 블록]`로 표시.

### 11. lifespan / migration 자동 적용

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Alembic upgrade head (sync, run_in_executor)
    # 2. engine + sessionmaker 생성 → app.state.session_factory
    # 3. LLM client init + health_check (skip 아니면) → app.state.llm
    # 4. yield
    # 5. engine dispose
```

- skip 플래그: env `HT_LENS_SKIP_LLM_CHECK=1` 일 때 True.
- 실패 시 `RuntimeError`로 startup 중단.

### 12. CLI 진입점

`ht-lens serve` subcommand:

```
ht-lens serve [--host TEXT] [--port INT] [--reload] [--db PATH] [--skip-llm-check]
```

- 기본: host=127.0.0.1, port=8080, reload=False
- `--db` 지정 시 `HT_LENS_DB_URL=sqlite+aiosqlite:///{path}` env로 export.
- `--skip-llm-check` 시 `HT_LENS_SKIP_LLM_CHECK=1` env.
- `--reload` 시 `uvicorn.run("ht_lens.api.app:create_app", factory=True, reload=True)`.
- 아니면 `uvicorn.run(create_app(), host=..., port=...)`.
- `python -m ht_lens.api`는 `__main__.py`에서 동일 옵션 typer로 노출.

### 13. CORS

```python
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

- prompt의 `localhost:*` 의도를 정규식으로 충실 반영.

### 14. 정적 파일 마운트

`app.mount("/static", StaticFiles(directory=<api>/static), name="static")`. `.gitkeep`이 있으므로 디렉토리 존재 보장.

## File-level changes

| Path | Action | Note |
| ---- | ------ | ---- |
| `pyproject.toml` | MODIFY | `fastapi>=0.115,<1`, `uvicorn[standard]>=0.32,<1` 추가 |
| `src/ht_lens/api/__init__.py` | NEW | empty |
| `src/ht_lens/api/__main__.py` | NEW | `python -m ht_lens.api` entry |
| `src/ht_lens/api/app.py` | NEW | `create_app()` factory + lifespan + CORS + static mount + router include |
| `src/ht_lens/api/deps.py` | NEW | `get_session`, `get_llm_client`, `get_chat_semaphore`, `get_data_root` |
| `src/ht_lens/api/schemas.py` | NEW | Pydantic read/create models |
| `src/ht_lens/api/chat_context.py` | NEW | `build_block_context` |
| `src/ht_lens/api/routers/__init__.py` | NEW | empty |
| `src/ht_lens/api/routers/documents.py` | NEW | `GET /documents`, `GET /documents/{id}` |
| `src/ht_lens/api/routers/pages.py` | NEW | `GET /documents/{id}/pages/{n}`, `GET /documents/{id}/pages/{n}/image` |
| `src/ht_lens/api/routers/threads.py` | NEW | `GET /threads`, `POST /threads`, `GET /threads/{id}` |
| `src/ht_lens/api/routers/messages.py` | NEW | `POST /threads/{id}/explain`, `POST /threads/{id}/messages` |
| `src/ht_lens/api/static/.gitkeep` | NEW | Phase 4 placeholder |
| `src/ht_lens/cli.py` | MODIFY | `serve` subcommand 등록 |
| `scripts/verify_api.sh` | NEW | curl + jq 시나리오 |
| `tests/integration/test_api_documents.py` | NEW | TestClient 기반 |
| `tests/integration/test_api_pages.py` | NEW | TestClient + image stream |
| `tests/integration/test_api_threads.py` | NEW | TestClient + mock LLM |
| `tests/integration/test_api_messages.py` | NEW | TestClient + mock LLM + history 누적 |
| `tests/integration/test_api_chat_context.py` | NEW | context builder unit |
| `tests/integration/test_api_static.py` | NEW | `/static/.gitkeep` 200 |
| `tests/integration/test_api_live_llm.py` | NEW | `@pytest.mark.llm` `/explain` + `/messages` |
| `tests/conftest.py` | MODIFY | `api_client` fixture (DB+lifespan-aware) |

## Dependencies (new)

| Package | Why |
| ------- | --- |
| `fastapi>=0.115,<1` | ASGI 라우팅 + pydantic v2 통합 |
| `uvicorn[standard]>=0.32,<1` | ASGI 서버, `[standard]`로 watchfiles/httptools 포함 → `--reload` + 성능 |

httpx는 openai SDK 의존성으로 이미 설치되어 TestClient(starlette) 동작에 충분. tqdm은 API 미사용. python-multipart는 file upload 없으므로 추가 안 함.

## Test strategy

### Integration (fast, mock LLM)
- `test_api_documents.py`: list / by-id / 404
- `test_api_pages.py`:
  - page+blocks 정상
  - 잘못된 page_num 404
  - image stream `content-type=image/png` + `Cache-Control` 헤더
  - DB의 bg_image_path가 data root 밖이면 500
- `test_api_threads.py`:
  - POST 생성 + default title
  - 잘못된 block_id 404
  - GET /threads (filter by doc_id)
  - GET /threads/{id} 상세
- `test_api_messages.py`:
  - `/explain` → user+assistant 2건 append
  - `/explain` 2회 호출 → 4건 (idempotency 강제 없음)
  - `/messages` 첫 호출 → block context prepend (capture LLM 입력 메시지 검사)
  - `/messages` 2번째 호출 → prepend 없음
  - LLM 에러 → 502
- `test_api_chat_context.py`: ±2 정상 / 페이지 첫 block / 마지막 block / radius=0 / image block 표시 / translation 없음 fallback
- `test_api_static.py`: `/static/.gitkeep` 200

### Live LLM (`@pytest.mark.llm`)
- `test_api_live_llm.py`: 시드된 doc → POST /threads → POST /explain → assistant 한국어 응답 길이 > 0 → 후속 `/messages "더 자세히"` → 최종 thread 4건 메시지

### Mocking 전략
- TestClient는 lifespan 자동 실행. `monkeypatch.setenv("HT_LENS_SKIP_LLM_CHECK", "1")`.
- DB: tmp_path sqlite + lifespan의 alembic upgrade. 그 후 fixture seed (Document/Page/Block/Translation) 직접 삽입.
- Mock LLM: `app.dependency_overrides[get_llm_client]`로 RecordingMockLLMClient (테스트 내 정의) 주입.

## DoD mapping

| DoD item | How to satisfy | Evidence plan |
| -------- | -------------- | ------------- |
| httpie/curl 시나리오 통과 | `scripts/verify_api.sh` | Stage 5b functional eval |
| async 일관 | router/deps 모두 `async def` + AsyncSession + LLM `await` | grep 검사 |
| pydantic schema 분리 | `api/schemas.py` Read/Create 모델 | code review |
| 정적 파일 마운트 `/static` | `app.mount("/static", StaticFiles(...))` | `test_api_static.py` |
| 채팅 컨텍스트 ±2 block | `build_block_context(radius=2)` | `test_api_chat_context.py` + `test_api_messages.py` |
| `/image` PNG stream | `FileResponse(... media_type="image/png")` | `test_api_pages.py` 헤더 검사 |
| mypy strict 0 | type 명시 | `uv run mypy src/` |
| ruff clean | line 100 / SIM/UP/B 준수 | `uv run ruff check .` |
| make test-fast green | mock 기반 integration | local + verify |

## 미결정 사항 (debate 검토 대상)

이미 결정한 9가지(위 1~9) + 추가 잠재 약점:

A. `/explain`에서 user prefix 메시지를 DB에 영구 저장하는 결정 — DB 부피/history 자연성 trade-off.
B. LLM 호출 prepend block context를 system 메시지 vs first user 메시지 합치기 — Phase 2b의 `chat(messages, *, system=...)` 시그니처 검토 필요.
C. lifespan auto alembic upgrade — 여러 인스턴스 동시 startup 시 race (single-user 가정으로 무시?).
D. CORS regex 보다 명시 list가 안전한지.
E. `HT_LENS_DATA_ROOT` 결정 로직: env vs DB path 그대로 trust.
F. uvicorn `--reload`에서 lifespan이 매번 alembic + LLM health 비용 발생 — `--skip-llm-check` 권장으로 회피.
G. messages list endpoint 부재 → 페이지네이션 미지원 (`GET /threads/{id}`가 messages 전부 동봉; Phase 5).
H. `/messages` 본문 length 제한 (현재 무제한, pydantic 기본).
I. shutdown 처리에서 진행 중인 LLM 호출 graceful (현재 cancel 위임, asyncio 기본).
