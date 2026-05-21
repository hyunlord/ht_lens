# Phase 6d — Plan

## Goal

브라우저 PDF drop → 백그라운드 extract→ingest→translate→summarize 체인 → viewer 진입까지 단일 흐름. v0.7 마일스톤.

## Scope

**In**
- DB Migration 0003: `jobs` 테이블 + `documents.summary` + `documents.summarized_at`
- Backend:
  - `POST /uploads` (multipart, sha256 dedup, 100MB limit, PDF magic byte 검증)
  - `GET /jobs?status=active|...`
  - `GET /jobs/{id}`
  - `POST /documents/{id}/summarize` (동기 처리, 재시도용)
  - `process_upload_job` 5단계 + 진행 callback
  - 자동 요약 (`summarize_document`)
  - lifespan background task pool + 재시작 시 in-flight `failed`로 mark
  - `translate_document`에 optional `on_progress` callback (backward-compat)
  - `data/uploads/{sha256}.pdf` 저장 + sanitize_filename
- Frontend:
  - `index.html` upload zone + drag-drop + 파일 선택 버튼
  - `jobs_panel.js` 활성 jobs polling (2초, Page Visibility)
  - `upload.js` multipart POST + 응답 처리
  - 카드의 summary preview + 재요약 버튼
- Tests: uploads, jobs, summarize, jobs_pipeline, translate progress callback, static markers, migration
- 10 screenshots + Playwright scenario (가능한 만큼)
- 1 new dep: `python-multipart` 명시 (transitive → explicit)

**Out**
- 멀티 사용자 동시성 (race 최소화만)
- HTTPS/인증
- Worker queue (Celery 등)
- Streaming response (Phase 6e)
- 모델 토글 (Phase 6e)
- 추출 품질 (Phase 6f)
- 멀티 tenant 권한

## Approach

### 1) DB Migration 0003

`src/ht_lens/db/migrations/versions/0003_jobs_and_summary.py`:

```python
def upgrade():
    op.create_table(
        "jobs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("type", sa.String, nullable=False),
        sa.Column("status", sa.String, nullable=False),
        sa.Column("document_id", sa.Integer, sa.ForeignKey("documents.id"), nullable=True),
        sa.Column("upload_path", sa.String, nullable=True),
        sa.Column("upload_filename", sa.String, nullable=True),
        sa.Column("upload_sha256", sa.String, nullable=True),
        sa.Column("progress_pct", sa.Integer, nullable=False, server_default="0"),
        sa.Column("progress_message", sa.String, nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("started_at", sa.DateTime, nullable=True),
        sa.Column("finished_at", sa.DateTime, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_jobs_status", "jobs", ["status"])
    op.add_column("documents", sa.Column("summary", sa.Text, nullable=True))
    op.add_column("documents", sa.Column("summarized_at", sa.DateTime, nullable=True))
```

`ALEMBIC_HEAD = "0003"`. `db/models.py`에 `Job` 클래스 + `Document.summary` / `summarized_at` 컬럼.

### 2) Status machine

`pending → extracting → ingesting → translating → summarizing → done` (linear). `failed`는 어디서든 진입. `active = pending|extracting|ingesting|translating|summarizing`.

### 3) `process_upload_job` 5단계 (progress %)

| 단계 | progress | message |
| ---- | -------- | ------- |
| prepare | 0~5 | "준비 중" |
| extract | 5~25 | "PDF 추출 중" |
| ingest | 25~30 | "DB 적재 중" |
| translate | 30~90 | "번역 중 {N}/{M}" (10 block마다 update) |
| summarize | 90~99 | "요약 생성 중" |
| done | 100 | "완료" |

`src/ht_lens/jobs/pipeline.py::process_upload_job(job_id)`:
- 매 단계마다 `update_job(...)` 호출
- top-level exception → `status=failed, error_message=str(e), finished_at=now`
- summarize 실패는 **non-fatal** (debate §4): `status=done, summary=None, error_message="요약 실패: ..."` — 사용자가 viewer 진입 가능

### 4) Background task pool

`src/ht_lens/jobs/background.py::BackgroundTaskPool`:

```python
class BackgroundTaskPool:
    def __init__(self): self._tasks: set[asyncio.Task] = set()
    def spawn(self, coro):
        t = asyncio.create_task(coro)
        self._tasks.add(t)
        t.add_done_callback(self._tasks.discard)
        return t
    async def shutdown(self):
        for t in self._tasks: t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
```

`api/app.py::_lifespan`:
- startup: `app.state.bg_pool = BackgroundTaskPool()` + 모든 `active` job → `status=failed, error_message="서버 재시작으로 중단됨"` (recovery)
- shutdown: `await app.state.bg_pool.shutdown()`

### 5) Translate `on_progress` callback

`translate/pipeline.py::translate_document(..., on_progress=None)`:
- 매 block 처리 후, `idx % 10 == 9 or idx == len(blocks)-1`일 때 `await on_progress(idx+1, len(blocks))`
- backward compat: None일 때 기존 동작 그대로

### 6) `summarize_document`

`src/ht_lens/summarize/pipeline.py`:

```python
MAX_SUMMARY_CHARS = 8000

async def summarize_document(doc_id, session, llm) -> str:
    body = await _fetch_translated_text(doc_id, session, max_chars=MAX_SUMMARY_CHARS)
    if not body.strip():
        raise SummarizeEmptyError("번역된 텍스트가 없습니다")
    prompt = build_summary_prompt(body)
    return (await llm.chat([{"role": "user", "content": prompt}])).strip()
```

`build_summary_prompt`: 한국어 prompt — 주제/주장/결론 + 300-500 단어. Phase 6e에서 hierarchical 검토.

### 7) POST /uploads

`api/routers/uploads.py`:

```python
MAX_UPLOAD_BYTES = 100 * 1024 * 1024

@router.post("/uploads", status_code=202)
async def upload_pdf(file: UploadFile, request, session) -> UploadResponse:
    # peek magic byte
    head = await file.read(5)
    if head != b"%PDF-":
        raise HTTPException(415, "PDF 파일만 업로드 가능합니다")
    await file.seek(0)
    # stream to tmp + sha256 with size cap
    sha256, total = await _stream_to_tmp(file, MAX_UPLOAD_BYTES)
    # dedup
    existing = await session.scalar(
        select(Document).where(Document.src_pdf_sha256 == sha256)
    )
    if existing:
        return UploadResponse(job_id=None, document_id=existing.id, dedup=True)
    # mv to uploads/
    final = settings.uploads_dir / f"{sha256}.pdf"
    Path(tmp_path).rename(final)
    # create job + spawn
    job = Job(type="process_upload", status="pending",
              upload_path=str(final),
              upload_filename=sanitize_filename(file.filename or "unknown.pdf"),
              upload_sha256=sha256)
    session.add(job)
    await session.commit()
    request.app.state.bg_pool.spawn(process_upload_job(job.id, app=request.app))
    return UploadResponse(job_id=job.id, document_id=None, dedup=False)
```

`sanitize_filename`: `Path(name).name` + non-allowed-char sub + 200 cap. 한국어 허용.

### 8) GET /jobs, GET /jobs/{id}

`api/routers/jobs.py`:

```python
@router.get("/jobs", response_model=list[JobRead])
async def list_jobs(status: str | None = None, session=...):
    q = select(Job).order_by(Job.id.desc())
    if status == "active":
        q = q.where(Job.status.in_(_ACTIVE_STATES))
    elif status:
        q = q.where(Job.status.in_(status.split(",")))
    return list(await session.scalars(q))

@router.get("/jobs/{job_id}", response_model=JobRead)
async def get_job(job_id, session=...):
    j = await session.get(Job, job_id)
    if not j: raise HTTPException(404, "job not found")
    return j
```

### 9) POST /documents/{id}/summarize

`api/routers/documents.py` 확장:

```python
@router.post("/{doc_id}/summarize", response_model=DocumentRead)
async def summarize_route(doc_id, session, llm) -> DocumentRead:
    doc = await session.get(Document, doc_id)
    if not doc: raise HTTPException(404)
    summary = await summarize_document(doc_id, session, llm)
    doc.summary = summary
    doc.summarized_at = datetime.utcnow()
    await session.commit()
    return doc
```

### 10) Frontend

`index.html`:
```html
<section class="upload-zone" id="upload-zone">...</section>
<section class="active-jobs" id="active-jobs" hidden></section>
<section class="documents-list">
  <ul class="doc-card-grid" id="doc-grid"></ul>
</section>
```

`js/components/upload.js`:
- dragenter/over/leave 핸들러 → `.upload-zone--drag`
- drop / 파일 선택 → POST /uploads (FormData)
- 응답:
  - dedup → toast "이미 업로드된 문서입니다" + `viewer.html?doc=N` 링크
  - new job → toast "업로드 시작" + jobs polling 시작

`js/components/jobs_panel.js`:
- `startJobsPolling()`: `setInterval(2000ms)`. `document.visibilityState === "hidden"`이면 `clearInterval` + visible 시 재개.
- 각 job: progress bar + message + error display + dismiss 버튼
- done 5초 후 자동 dismiss + `refetchDocs()`
- 모든 active job 종료 시 polling 멈춤

`js/components/document_card.js`:
- summary preview (200 chars + "...")
- summary null이면 "요약 없음 (재생성)" 버튼 → POST /documents/{id}/summarize

`js/api.js`: + `uploadPDF`, `listJobs`, `getJob`, `summarizeDocument`.

`js/index.js`: wiring.

`css/index.css`: upload-zone + active-jobs + summary-preview.

### 11) Polling 정책

- 간격 2초
- active jobs 있을 때만
- `document.visibilityState === "hidden"` 시 일시정지

### 12) 보안

- sanitize_filename: `Path(name).name` + non-allowed sub + 200 cap
- 저장 파일명은 `{sha256}.pdf` (사용자 filename 무시)
- DB `documents.filename` + `jobs.upload_filename`만 사용자 원본
- `data/uploads/` lifespan에서 `mkdir(parents=True, exist_ok=True)`
- 100MB cap

### 13) Phase 6c 호환

- `_load_repo_dotenv` 그대로
- autouse `_isolate_llm_env` fixture로 새 테스트도 자동 격리
- viewer.html / Phase 6b 자연 스크롤 영향 0

### 14) 신 식별자 (워크플로우 0-3-A 의무 표)

| 영역 | 새 식별자 |
| ---- | -------- |
| db/models.py | `Job` 클래스, `Document.summary`, `Document.summarized_at` |
| db/migrations | `0003_jobs_and_summary` |
| db/session.py | `ALEMBIC_HEAD = "0003"` |
| jobs/pipeline.py | `process_upload_job`, `update_job`, `JobStatus` literals |
| jobs/background.py | `BackgroundTaskPool` |
| summarize/pipeline.py | `summarize_document`, `build_summary_prompt`, `SummarizeEmptyError`, `MAX_SUMMARY_CHARS` |
| translate/pipeline.py | `on_progress` 매개변수 + every-10 호출 분기 |
| api/routers/uploads.py | `POST /uploads`, `sanitize_filename`, `_stream_to_tmp`, `MAX_UPLOAD_BYTES` |
| api/routers/jobs.py | `GET /jobs`, `GET /jobs/{id}`, `_ACTIVE_STATES` |
| api/routers/documents.py | `POST /{doc_id}/summarize` |
| api/schemas.py | `JobRead`, `UploadResponse`, `DocumentRead.summary` |
| api/app.py | `_lifespan` `bg_pool` + `_mark_in_flight_jobs_failed` |
| static/js/api.js | `uploadPDF`, `listJobs`, `getJob`, `summarizeDocument` |
| static/js/components/upload.js | `attachUpload`, `handleDrop`, `postUpload` |
| static/js/components/jobs_panel.js | `startJobsPolling`, `renderJobsPanel`, `stopJobsPolling` |
| static/js/components/document_card.js | `renderDocumentCard` (확장) |
| static/index.html | `#upload-zone`, `#active-jobs`, `.upload-zone--drag` |
| static/css/index.css | `.upload-zone`, `.upload-zone--drag`, `.active-jobs`, `.summary-preview` |

## File-level changes

| Path | Action | Note |
| ---- | ------ | ---- |
| `pyproject.toml` | MODIFY | + python-multipart 명시 |
| `src/ht_lens/db/migrations/versions/0003_jobs_and_summary.py` | NEW | |
| `src/ht_lens/db/session.py` | MODIFY | ALEMBIC_HEAD = "0003" |
| `src/ht_lens/db/models.py` | MODIFY | + Job + Document.summary/.summarized_at |
| `src/ht_lens/jobs/__init__.py` | NEW | |
| `src/ht_lens/jobs/pipeline.py` | NEW | |
| `src/ht_lens/jobs/background.py` | NEW | |
| `src/ht_lens/summarize/__init__.py` | NEW | |
| `src/ht_lens/summarize/pipeline.py` | NEW | |
| `src/ht_lens/translate/pipeline.py` | MODIFY | + on_progress |
| `src/ht_lens/api/app.py` | MODIFY | + bg_pool + lifespan recovery + 라우터 |
| `src/ht_lens/api/schemas.py` | MODIFY | + JobRead/UploadResponse/DocumentRead.summary |
| `src/ht_lens/api/routers/uploads.py` | NEW | |
| `src/ht_lens/api/routers/jobs.py` | NEW | |
| `src/ht_lens/api/routers/documents.py` | MODIFY | + /summarize + summary 노출 |
| `src/ht_lens/api/static/index.html` | MODIFY | upload zone + jobs panel |
| `src/ht_lens/api/static/js/api.js` | MODIFY | + uploadPDF/listJobs/getJob/summarizeDocument |
| `src/ht_lens/api/static/js/index.js` | MODIFY | wiring |
| `src/ht_lens/api/static/js/components/upload.js` | NEW | |
| `src/ht_lens/api/static/js/components/jobs_panel.js` | NEW | |
| `src/ht_lens/api/static/js/components/document_card.js` | NEW | |
| `src/ht_lens/api/static/css/index.css` | NEW | |
| `tests/integration/test_api_uploads.py` | NEW | |
| `tests/integration/test_api_jobs.py` | NEW | |
| `tests/integration/test_api_summarize.py` | NEW (+ @pytest.mark.llm) | |
| `tests/integration/test_jobs_pipeline.py` | NEW | |
| `tests/integration/test_translate_progress.py` | NEW | |
| `tests/integration/test_static_serving.py` | MODIFY | + 6d grep markers |
| `tests/integration/test_alembic.py` | MODIFY | + 0003 head |
| `docs/phases/phase-6d/README.md` + `screenshots/*.png` | NEW (~10) | |

## Dependencies (new)

| Package | Why |
| ------- | --- |
| `python-multipart >= 0.0.9` | FastAPI `UploadFile` 의존성. starlette transitive지만 명시. |

## Test strategy

### Backend integration (fast, mock LLM)
- `test_api_uploads.py` (5+): 정상/dedup/415 non-PDF/413 oversize/sanitize
- `test_api_jobs.py` (4+): list/get/status filter/404
- `test_api_summarize.py` (3+): mock/404/empty body
- `test_jobs_pipeline.py` (3+): mock extract→ingest→translate→summarize 흐름 + 실패 분기 + summarize 실패 non-fatal
- `test_translate_progress.py` (2): callback every-10 호출 검증 + None backward-compat
- `test_static_serving.py` 확장 (+5): upload-zone/jobs-panel/summary-preview grep
- `test_alembic.py`: 0003 head

### Live LLM (`@pytest.mark.llm`)
- `test_api_summarize.py::test_summarize_live_korean_natural`: 진짜 sglang 요약 300~500 단어 + 한국어 검증

### Manual (verify 5-B)
- 5~10페이지 PDF 업로드 end-to-end
- 같은 파일 dedup
- 잘못된 파일 거부
- 실패 시 에러 표시
- 10 screenshots

## DoD mapping

| DoD item | How to satisfy | Evidence plan |
| -------- | -------------- | ------------- |
| 브라우저 PDF 드롭 → viewer 진입 한 흐름 | upload zone + process_upload_job + polling | screenshots 01-06 + manual |
| 200 페이지 1~2시간 + 진행 표시 | every-10 callback + jobs row update | 5~10페이지 실측 + extrapolation + screenshot 04 |
| 자동 요약 300~500 단어 한국어 | LLM call + Korean prompt | screenshot 09/10 + @pytest.mark.llm |
| sha256 dedup | Document.src_pdf_sha256 lookup | screenshot 07 + test |
| 실패 시 명확한 에러 | jobs.error_message + frontend banner | screenshot 08 + test |

## 미결정 사항 (debate 검토 대상)

1. **lifespan asyncio.create_task vs FastAPI BackgroundTasks**: plan은 lifespan pool (cancel 가능)
2. **동시 업로드 같은 sha256**: plan은 unique constraint + IntegrityError catch
3. **요약 truncation 8000 chars**: 충분성 — Phase 6e token-aware 검토
4. **summarize fail 시 job status**: plan은 done + error_message (non-fatal). 혼란 가능성 debate
5. **upload PDF 깊은 검증**: plan은 5-byte magic only. PyMuPDF는 extract 단계
6. **frontend polling visibility**: plan 적용
7. **jobs cleanup**: plan은 무한 보관. Phase 6e retention 정책
8. **재요약 정책**: plan은 단순 덮어쓰기
9. **upload browser→backend progress**: plan은 단순 fetch. 백엔드 단계 진행으로 충분
10. **error i18n**: 한국어 고정

debate에서 Codex가 사용성 (summarize fail UX), 보안 (sanitize edge), pipeline 호환, background task graceful shutdown, jobs table size 등 찌를 가능성.
