# Phase 2a — Plan

## Goal
SQLite + SQLAlchemy 2.0 async DB 스키마, `LLMClient` Protocol + `MockLLMClient`, 그리고 `python -m ht_lens.ingest <extract_dir>` CLI를 추가해 Phase 1 산출물을 DB로 적재한다. 외부 LLM 호출 0건.

## Scope

**In**
- 7-table ORM schema (SQLAlchemy 2.0 typed `Mapped[...]`) — prompt 고정 스키마 따름
- Async engine/session (aiosqlite), `make_engine` / `make_session_factory`
- Alembic migration 1개 (`0001_initial_schema`) — 손으로 작성 (autogenerate 없이, mypy strict 호환 + 결정적)
- `LLMClient` Protocol + `Message` TypedDict + `MockLLMClient` 구현 + `from_env` 팩토리
- conftest `llm_mock` placeholder → 실제 `MockLLMClient` 인스턴스
- `python -m ht_lens.ingest <extract_dir>` / `ht-lens ingest <extract_dir>` CLI
  - Phase 1 `doc_meta.json` + `pages/page_*.json` 검증 후 ORM 적재
  - 옵션: `--db-path`, `--src`, `--tgt`, `--overwrite`
- `ht-lens db migrate` 편의 명령 (내부적으로 `alembic upgrade head`)
- Unit + integration test (3 fixture)

**Out**
- 실제 LLM 호출 (Phase 2b)
- HTTP 클라이언트 (`httpx` / `openai` / `requests` 등) — import도 금지
- 캐시, 번역 파이프라인 (Phase 2b)
- FastAPI / 정적 viewer (Phase 3/4)
- threads/messages CRUD CLI (DB 스키마만 두고, 사용은 Phase 3+)

## Approach

### 핵심 결정 7가지 (prompt "결정을 plan에서 내려야 할 것들")

1. **Async engine 셋업**
   - URL: `sqlite+aiosqlite:///<absolute path>`. 상대경로는 `Path.resolve()`로 절대화 후 사용.
   - `create_async_engine(url, echo=False, future=True)`. SQLite는 동시 writer가 1이라 pool 튜닝 불필요 (기본).
   - PRAGMA: `event.listens_for(engine.sync_engine, "connect")`로 **`foreign_keys=ON`만** 설정. cascade test 정합성에 필수. WAL/`synchronous=NORMAL`은 Phase 2b/3에서 부하 측정 후 결정 (Phase 2a serial CLI에 불필요).
   - `async_sessionmaker(engine, expire_on_commit=False)`로 session factory.
   - CLI는 직접 sessionmaker 사용. FastAPI(Phase 3)에서 dependency로 재사용 가능.

2. **Transaction 경계**
   - **단일 transaction per document**. ingest 한 권 전체를 한 트랜잭션으로 묶고 끝에서 commit. 도중 실패 시 rollback → DB 깨끗.
   - 페이지 단위 commit은 거부 — Phase 1 산출물 한 권은 보통 50페이지 미만이라 메모리 부담 없고, 부분 적재 상태(documents 행은 있고 pages는 일부만)가 verify/debug를 어렵게 함.
   - `flush()`는 매 페이지 후 호출해 `page.id`를 받아 block 행에 외래키로 넣는다.

3. **재진입성**
   - 기본 동작: `documents.filename`이 이미 존재하면 `--overwrite` 없이는 exit 2 + 메시지 ("document already ingested; use --overwrite").
   - `--overwrite`: 기존 document(filename 기준) cascade 삭제 후 재적재. **CLI help + stderr 진입 시 경고** ("WARNING: --overwrite matches by filename only; two different PDFs sharing a name will destroy data"). sha256 컬럼은 schema에 없어 in-memory 비교 불가; Phase 6 known debt로 column 추가 + 검증 강화 예정.
   - 단일 transaction으로 delete + insert. 도중 실패 시 rollback → 기존 doc survive (overwrite rollback safety).
   - 이로써 idempotent하진 않지만 명시적 (silent skip이 더 위험).

4. **Phase 1 page JSON 스키마 변동 대비 + 매니페스트 무결성**
   - ingest는 Phase 1의 `ht_lens.extract.models.PageDoc` / `DocMeta` Pydantic 모델을 **재사용해 parse**한다. 새 의존성 없고 schema 정합성 자동 보장.
   - 그러나 Pydantic parse만으로는 매니페스트 무결성 보장 안 됨 → ingest pipeline에 **명시적 검증** 추가 (debate §2 accept):
     - `doc_meta.num_pages == len(<extract_dir>/pages/page_*.json)`
     - page_num 시퀀스가 `1..doc_meta.num_pages` contiguous
     - 각 page에 대응 `<extract_dir>/pages/page_{page_num:04d}.png` 존재
   - 위반 시 `IngestError` raise, exit 2 + 구체 메시지 (어떤 page가 누락/잉여/번호 깨짐).
   - Pydantic `ValidationError`도 `IngestError`로 wrap, exit 2 + 구체 메시지 (page 번호 포함).
   - `render` 필드는 `PageDoc` 정의상 필수이므로 누락 case는 발생하지 않음.
   - `bg_image_path`는 Phase 1 산출물에 명시되어 있지 않으므로 ingest가 `<extract_dir>/pages/page_{page_num:04d}.png`로 도출 후 존재성 검증.

5. **`bbox_json` 직렬화 헬퍼**
   - `Block` ORM 모델에 read-only property `bbox` 추가:
     ```python
     @property
     def bbox(self) -> tuple[float, float, float, float]:
         x0, y0, x1, y1 = json.loads(self.bbox_json)
         return (x0, y0, x1, y1)
     ```
   - setter는 추가 안 함 (혼란 방지). 쓰기는 ingest가 명시적으로 `bbox_json=json.dumps(list(bbox))`.

6. **Alembic migration 자동 적용 정책**
   - **ingest 시작 시 자동 적용 안 함**. 사용자가 명시적으로 적용해야 함.
   - 편의 명령 `ht-lens db migrate`는 **제공하지 않음** (debate §1 partial accept — minimal). 사용자에게 `uv run alembic upgrade head` 안내.
   - ingest 시작 시 schema version 체크: `alembic_version` 테이블 없거나 head와 불일치 → `SchemaVersionMismatch` raise, exit 3 + 메시지 ("run: uv run alembic upgrade head"). runtime gate는 유지 (사용자 UX/디버깅 명확성).

7. **DB 파일 위치**
   - 기본값 `./data/ht_lens.db` (`Path.cwd() / "data" / "ht_lens.db"`).
   - `--db-path`가 절대경로면 그대로, 상대경로면 `cwd` 기준 resolve.
   - 부모 디렉토리 없으면 `mkdir(parents=True, exist_ok=True)`로 자동 생성.
   - `.gitignore`는 이미 `data/*` + `!data/.gitkeep`로 처리되어 있음 (Phase 0). 추가 수정 불필요 (확인 완료).

8. **`--src` / `--tgt` 처리 (debate §2 accept)**
   - `--tgt` default `ko`.
   - `--src` default = `DocMeta.lang_guess` 값이 `"en"` 또는 `"ko"`면 그 값.
   - `lang_guess`가 `"mixed"`/`"unknown"`인데 `--src`가 미지정이면 exit 2 + 메시지 ("source language ambiguous; pass --src explicitly").
   - sample_mixed.pdf는 `--src en` 또는 `--src ko`로 명시 ingest (Phase 2b 번역 단계에서 정교화 가능).

### 부가 결정

- **PK 전략**: 모든 테이블 surrogate int (`Mapped[int] = mapped_column(primary_key=True)`). Phase 1 식별자(`p1_b001`)는 `Block.block_local_id`(string)에 보존, **글로벌 unique 가정 없음** (debate §2 accept 강조 보완).
- **`translations.block_id` PK 한계**: prompt schema 고정. 멀티모델 캐시·재번역은 Phase 2b는 단일 모델 가정으로 진행. Phase 6에서 schema migration 예정 (known debt, debate §2 partial accept).

- **Datetime**: 모든 `created_at`/`updated_at`은 timezone-aware UTC (`datetime.now(UTC)`). DB는 SQLite naive로 저장하지만 application layer가 항상 UTC로 다룬다.
- **`Translation.status`**: ingest 시점에는 translation 행을 생성하지 않는다. Phase 2b 책임.
- **`Document.status`**: ingest 후 항상 `"ready_for_translation"`. Phase 2b에서 `"translating"` → `"translated"`/`"failed"`로 전이.
- **Test DB**: 모든 테스트는 `tmp_path` 기반의 fresh SQLite. fixture로 `db_url`, `async_session` 제공. 테스트는 ORM `Base.metadata.create_all` 사용 (Alembic 우회) — alembic 자체는 별도 integration test에서 검증.
- **Concurrency**: aiosqlite는 단일 writer. Phase 2a ingest는 직렬이라 문제 없음. Phase 2b 동시성은 별도 plan.

## File-level changes

| Path | Action | Note |
| ---- | ------ | ---- |
| `pyproject.toml` | Modify | dependencies에 `sqlalchemy[asyncio]>=2.0,<3`, `aiosqlite>=0.20`, `alembic>=1.13` 추가. `[[tool.mypy.overrides]]`로 `ht_lens.db.migrations.*`에 strict 완화 (alembic 생성 코드 호환). |
| `.gitignore` | Modify (필요 시) | `data/` 패턴 없으면 추가. |
| `src/ht_lens/db/__init__.py` | Create | empty marker |
| `src/ht_lens/db/base.py` | Create | `class Base(DeclarativeBase)` |
| `src/ht_lens/db/models.py` | Create | 7개 ORM 클래스 — prompt 스키마 그대로 |
| `src/ht_lens/db/session.py` | Create | `make_engine(url)`, `make_session_factory(engine)`, async PRAGMA hooks, `current_schema_version(session) -> str \| None` |
| `src/ht_lens/db/migrations/env.py` | Create | Alembic env (offline + async online) |
| `src/ht_lens/db/migrations/script.py.mako` | Create | Alembic template |
| `src/ht_lens/db/migrations/versions/0001_initial_schema.py` | Create | 손으로 작성된 7-table create. `down_revision=None`, `revision="0001"`. |
| `alembic.ini` | Create | `script_location = src/ht_lens/db/migrations`; URL은 env에서 override (CLI나 env var) |
| `src/ht_lens/llm/__init__.py` | Create | re-export `LLMClient`, `MockLLMClient`, `from_env`, `Message` |
| `src/ht_lens/llm/client.py` | Create | `Role` Literal, `Message` TypedDict, `LLMClient` Protocol |
| `src/ht_lens/llm/mock.py` | Create | `MockLLMClient` 결정적 구현 |
| `src/ht_lens/llm/factory.py` | Create | `from_env() -> LLMClient`; provider != "mock"이면 NotImplementedError |
| `src/ht_lens/ingest/__init__.py` | Create | empty marker |
| `src/ht_lens/ingest/__main__.py` | Create | `from ht_lens.cli import app; app()` — typer 단일 entry 통일 |
| `src/ht_lens/ingest/pipeline.py` | Create | `async def ingest_extract_dir(extract_dir, session, *, src, tgt, overwrite) -> IngestStats` |
| `src/ht_lens/cli.py` | Modify | `ingest` subcommand 추가 (debate §1 partial accept — `db_migrate` 제거). |
| `src/ht_lens/errors.py` | Modify | `IngestError`, `SchemaVersionMismatch`, `DocumentAlreadyIngested` 추가 (`HtLensError` 패턴 재사용) |
| `tests/conftest.py` | Modify | `llm_mock` → 실제 `MockLLMClient`. `tmp_db_url`, `async_session_factory` fixture 추가 |
| `tests/unit/test_db_models.py` | Create | 7 모델 instantiation + relationship + cascade |
| `tests/unit/test_llm_mock.py` | Create | translate/chat/health_check deterministic + factory branching |
| `tests/integration/test_ingest_pipeline.py` | Create | 3 fixture extract→ingest, DB 행 수, overwrite 동작 |
| `tests/integration/test_ingest_cli.py` | Create | subprocess `python -m ht_lens.ingest`, exit codes |
| `tests/integration/test_alembic.py` | Create | `alembic upgrade head` → 7 테이블 + `alembic_version` 행 |

`src/ht_lens/ingest/__main__.py`는 단순 위임이라 별도 `ingest/cli.py` 두지 않음. Phase 1의 `extract/__main__.py` 패턴과 일관.

## Dependencies (new)

| Package | Version | Why |
| ------- | ------- | --- |
| `sqlalchemy[asyncio]` | `>=2.0,<3` | DB ORM. typed `Mapped[...]` 지원. `[asyncio]` extra가 greenlet 자동 끌어옴. |
| `aiosqlite` | `>=0.20` | SQLite의 async driver. SQLAlchemy 2.0 async 지원. |
| `alembic` | `>=1.13` | Schema migration. Python 3.11 + SQLAlchemy 2.0 호환. |

`httpx`, `openai`, `requests` 등 HTTP 클라이언트는 **Phase 2b로 미룸** — 이번 phase에서는 import도 금지.

## Test strategy

### Unit (in-memory, fast)

- `test_db_models.py`
  - Base classes import, 7 모델 매핑 정합성 (선언 시점에 SQLAlchemy가 검증)
  - `Base.metadata.create_all`로 in-memory SQLite 스키마 생성
  - 각 모델 instantiate + relationship traversal (Document→Page→Block→Translation, Block→Thread→Message)
  - cascade delete: Document 삭제 시 pages/blocks/translations/threads/messages 모두 삭제
  - `Block.bbox` property가 `bbox_json` 파싱 결과 반환
  - foreign_keys ON 확인 (잘못된 FK insert가 IntegrityError)

- `test_llm_mock.py`
  - `MockLLMClient().translate("hello", "en", "ko")` deterministic
  - `MockLLMClient().chat([...])` deterministic
  - `health_check()` True
  - `from_env()` provider=mock → MockLLMClient, provider="openai_compat" → NotImplementedError

### Integration

- `test_ingest_pipeline.py`
  - 3 fixture 각각에 대해:
    1. `extract_pdf` 실행 (in-process) → temp extract_dir
    2. ORM `create_all`로 스키마 초기화 후 `ingest_extract_dir(...)` 실행
    3. assertions: `documents`=1, `pages`=doc_meta.num_pages, `blocks`>0, **첫 text-type block**의 `original_text` 비어있지 않음 (image block은 빈 텍스트 허용 — debate §3 accept), `Block.bbox` tuple[4]
  - 두 번 ingest (overwrite=False) → `DocumentAlreadyIngested` raise
  - 두 번째 overwrite=True → cascade 삭제 + 재적재 OK (`documents` 여전히 1)
  - **신규 (debate §3, §5 accept)**:
    - `test_ingest_accepts_empty_text_image_blocks`: image block + `text=""` 정상 적재
    - `test_ingest_detects_manifest_mismatch`: page json 누락 / num_pages 불일치 → `IngestError`, exit 2
    - `test_overwrite_rollback_preserves_existing_document_on_failure`: 정상 ingest 후, tamper된 extract_dir로 overwrite 실패 → 기존 row 그대로
    - `test_ingest_rejects_or_disambiguates_duplicate_filenames_with_different_sha256`: 같은 filename + 다른 sha256 두 번째 → overwrite 없으면 거부, overwrite 시 stderr 경고

- `test_ingest_cli.py`
  - `subprocess.run([sys.executable, "-m", "ht_lens.ingest", str(extract_dir), "--db-path", str(tmp_db)])` exit 0
  - 존재하지 않는 디렉토리 → exit 2
  - migration 안 한 DB → exit 3 + 메시지에 "uv run alembic upgrade head"
  - **신규 (debate §5 accept)**:
    - `test_ht_lens_console_script_ingest`: `subprocess.run(["ht-lens", "ingest", ...])` (Phase 1 `test_module_cli.py` 패턴 따라)

- `test_alembic.py`
  - 빈 SQLite에 `alembic upgrade head` (subprocess) → exit 0
  - 적용 후 SQLAlchemy reflect → 7 테이블 + `alembic_version` 존재, version=`0001`

### Coverage 목표
- Phase 0/1 baseline 91% 유지. 신규 코드 (`db/`, `llm/`, `ingest/`) 85% 이상.

### marker
- LLM-marked test 0건 (실제 LLM 호출 없음)
- 무거운 test 없음 (3 fixture extract 모두 합쳐 ~30초 이내)

## DoD mapping (ROADMAP Phase 2a)

| DoD item | How to satisfy | Evidence plan |
| -------- | -------------- | ------------- |
| 3종 fixture extract 산출물을 ingest 가능, DB 행 합리적 | `test_ingest_pipeline.py`가 3 fixture 모두 실행 + verify.md에서 manual e2e (exit 0 + DB count) | pytest pass, verify.md table |
| `LLMClient` interface 정의 + `MockLLMClient` unit test 통과 | `src/ht_lens/llm/*` + `test_llm_mock.py` | pytest pass |
| mypy strict (SQLAlchemy 2.0 typed 포함), ruff clean | `make check` exit 0 | verify.md 5-A |
| end-to-end ingest 1회 동작 (CLI exit 0) | `python -m ht_lens.ingest <dir> --db-path <db>` exit 0 (`test_ingest_cli.py` + verify.md manual) | verify.md 5-B |
| Alembic migration 1개 생성, 적용 가능 | `0001_initial_schema.py` + `uv run alembic upgrade head` → schema version `0001`, 7 tables 존재 | verify.md 5-B (`alembic upgrade head` 실행 후 sqlite_master 출력) |

## Risk register

| Risk | Likelihood | Impact | Mitigation |
| ---- | ---------- | ------ | ---------- |
| SQLAlchemy 2.0 `Mapped[...]` + mypy strict 충돌 | Medium | Medium | typed `Mapped[X]` 패턴 일관 사용, `DeclarativeBase` 직접 상속. Forward ref는 string 인용. SQLAlchemy 2.0 공식 가이드 패턴 |
| Alembic `env.py` async 호환 | Medium | Low | Alembic 1.13 공식 패턴 (`async with engine.connect()` + `await connection.run_sync(do_run_migrations)`) 사용 |
| ingest 중 page JSON validation 실패 | Low | Medium | Pydantic `ValidationError`를 `IngestError`로 wrap, exit 2 + page_num 명시 |
| 같은 doc 재적재 silent corruption | Medium | High | `--overwrite` 없으면 exit 2 |
| Phase 1 ExtractResult 기대치와 다를 가능성 (page 파일명 패턴 등) | Low | Medium | 사전 확인 완료: `page_0001.json` (4자리), `pages/`, `doc_meta.json` 모두 prompt 가정과 일치 |
| Alembic 자동 적용 안 함 → 사용자 혼란 | Low | Low | ingest CLI에 명확한 에러 메시지 ("run: ht-lens db migrate") + `db migrate` subcommand |
| Alembic 코드(`migrations/versions/*.py`)가 mypy strict 통과 어려움 | Medium | Low | `[[tool.mypy.overrides]]`로 해당 모듈만 strict 완화 |

## Open questions

(없음 — 위 결정으로 충분. debate에서 추가 이슈 나오면 challenge.md에 반영.)
