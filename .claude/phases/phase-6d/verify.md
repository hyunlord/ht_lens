# Phase 6d — Verify (self, v1)

작성 직전 `git status` clean. head 시점에 대한 self-evaluation.

## 5-A. Automated checks

| Check    | Command | Result |
| -------- | ------- | ------ |
| Lint     | `uv run ruff check .` | All checks passed! |
| Format   | `uv run ruff format --check .` | already formatted |
| Type     | `uv run mypy src/` | Success: no issues found in 59 source files |
| Test (fast) | `make test-fast` | **383 passed, 7 deselected** in 212.16s |
| Coverage | `make check` 내장 | TOTAL 68% (신규 jobs/uploads 라우터 면적 큼) |
| Test (live LLM) | `pytest -m llm` (LLM_TIMEOUT=300) | **7 passed** in 163.11s |
| CI (local) | `make check` | **RC=0** |
| CI (remote) | `.github/workflows/ci.yml` | pending push |

Phase 6d 누적 신규 자동 테스트 **30건** (353 → 383):
- `test_api_uploads.py` (6): 415 / 413 / sanitize / 202 / dedup / race fast-path
- `test_api_jobs.py` (7): empty / order / active filter / explicit / 404 / by-id / startup-recovery
- `test_api_summarize.py` (3 + 1 @llm): 404 / image-only 422 / writes summary / live Korean
- `test_translate_progress.py` (2): every-10 callback / None backward-compat
- `test_static_serving.py` 확장 (+9): assets / html mounts / api / drag-drop / visibility polling / summary banner / index wiring / viewer banner

## 5-B. Functional checks

### 1) Migration 0003 적용 (live DB)

```
$ HT_LENS_DB_URL=... uv run alembic upgrade head
Running upgrade 0002 -> 0003, phase 6d: jobs table + documents.summary + sha256 UNIQUE

$ sqlite3 data/ht_lens.db "SELECT name FROM sqlite_master WHERE type='table' AND name='jobs';"
jobs

$ sqlite3 data/ht_lens.db "PRAGMA table_info(documents);" | grep summary
7|summary|TEXT|0||0
8|summarized_at|DATETIME|0||0

$ sqlite3 data/ht_lens.db "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'uq_%';"
uq_documents_src_pdf_sha256
```

### 2) End-to-end upload (real LLM)

```
POST /uploads (phase6d_demo.pdf, 2 페이지, 1914 bytes)
→ 202 {"job_id": 1, "document_id": null, "dedup": false}

t=0s   extracting  pct=10  "PDF 추출 중: phase6d_demo.pdf"
t=5s   translating pct=30  "번역 시작"
t=15s  summarizing pct=92  "요약 생성 중"
t=56s  done        pct=100 "완료"
```

56 초 / 2 페이지 = 28 s/page. 200 페이지 추정 ~93 분 (DoD 1~2시간).

자동 요약 (1135 자 ≈ 380 단어):
> 제시된 문서는 두 가지 명확히 구분된 주제를 포함하고 있으며, 전체적으로는 기술적 테스트 도구와 인공지능(AI) 비디오 생성 모델의 성과 보고로 …

한국어 자연성 양호 / 300~500 단어 충족 / 주제·주장·결론 포함 → DoD ✅.

### 3) Dedup 동작

```
$ curl -X POST /uploads -F "file=@phase6d_demo.pdf"
{"job_id": null, "document_id": 2, "dedup": true}
```

UNIQUE constraint + 라우터 fast-path 둘 다 검증.

### 4) 보안 거부

- non-PDF (txt) → 415 "PDF 파일만 업로드 가능합니다 (매직 바이트 불일치)"
- 100MB 초과 → 413 "파일이 N MB 제한을 초과했습니다"
- path traversal sanitize: `../../etc/passwd.pdf` → `passwd.pdf`
- 한국어 파일명 보존: `내 문서 (1).pdf` → `내 문서 _1_.pdf`

### 5) 10 screenshots (live)

`scripts/phase6d_scenario.py` 실행:
- 01 empty upload zone
- 02 drag-over hover state
- 03 upload in progress (active-jobs 패널)
- 04 translating mid
- 05 summarizing
- 06 done + 새 카드 + summary preview
- 07 dedup toast
- 08 failed error (non-PDF)
- 09 summary in card
- 10 summary banner in viewer

### 6) DoD evidence matrix

| DoD | 만족 | 근거 |
| --- | ---- | ---- |
| 브라우저 PDF 드롭 → 자동 처리 → viewer 진입 한 흐름 | ✅ | screenshots 01-06 + 10 + 56초 end-to-end |
| 200 페이지 1~2시간 + 진행 표시 | ✅ | per-page 28s 측정 + every-10 progress callback + 5-stage status machine |
| 자동 요약 300~500 단어 한국어 | ✅ | live 380단어 + screenshot 09/10 + @pytest.mark.llm |
| sha256 dedup | ✅ | UNIQUE constraint + 라우터 fast-path + integration test |
| 실패 시 명확한 에러 | ✅ | 415 / 413 / 422 / jobs.error_message + screenshot 08 |

## 5-C. Regression check + 신 코드 경로 잠금 (워크플로우 0-3-A)

### Phase 6d 신 식별자 → 명시 테스트

| 영역 | 새 식별자 | 잠금 |
| ---- | --------- | ---- |
| db/models.py | `Job` + `Document.summary` / `summarized_at` | migration + 30 integration |
| db/migrations | `0003_jobs_and_summary` + UNIQUE | `test_alembic` + 실측 |
| db/session.py | `ALEMBIC_HEAD = "0003"` | head check |
| jobs/pipeline.py | `process_upload_job`, `update_job`, `mark_in_flight_jobs_failed`, `JOB_STATUSES`, `ACTIVE_STATUSES` | end-to-end 56s + `test_startup_marks_active_jobs_failed` |
| summarize/pipeline.py | `summarize_document`, `build_summary_prompt`, `SummarizeEmptyError`, `MAX_SUMMARY_CHARS` | 4 tests + 1 @llm |
| translate/pipeline.py | `on_progress` + `_PROGRESS_EVERY` | 2 tests |
| ingest/pipeline.py | `display_filename_override` | end-to-end (`documents.filename = "phase6d_demo.pdf"` 정상) |
| api/routers/uploads.py | `POST /uploads`, `sanitize_filename`, `_stream_to_tmp`, `MAX_UPLOAD_BYTES` | 6 tests |
| api/routers/jobs.py | `GET /jobs`, `GET /jobs/{id}` | 7 tests |
| api/routers/documents.py | `POST /{id}/summarize` | 3 + 1 @llm |
| api/schemas.py | `JobRead`, `UploadResponse`, `DocumentRead.summary`/`summarized_at` | response model |
| api/app.py | `_DEFAULT_UPLOADS_DIR`, `app.state.background_tasks`, restart recovery | startup recovery test |
| static/js/api.js | `uploadPDF`, `listJobs`, `getJob`, `summarizeDocument` | grep test |
| static/js/components/upload.js | `attachUpload` + drag/drop | grep test |
| static/js/components/jobs_panel.js | `startJobsPolling`, `stopJobsPolling`, visibility 핸들러 | grep test |
| static/js/components/summary_banner.js | `renderSummaryBanner` | grep test |
| static/index.html | `#upload-zone`, `#active-jobs`, `#doc-grid` | grep test |
| static/viewer.html | `#summary-banner-mount` | grep test |
| static/css/index.css | `.upload-zone*`, `.active-jobs`, `.summary-preview` | asset 200 |
| tests/_api_helpers | seed sha256 unique-aware | 30 신규 + 무회귀 |

모든 신 식별자 grep-lock 또는 통합 테스트 lock. 워크플로우 0-3-A 의무 충족.

### 기존 contract 무회귀

- 353 → 383 fast tests 통과
- Phase 2b CLI translate / manual pipeline — on_progress=None backward compat ✅
- Phase 3 / 4 / 5 / 6a / 6b / 6c — 회귀 0
- viewer.html / index.html 신규 mount만 추가

### Deviations from challenge

- `BackgroundTaskPool` 클래스 drop → `app.state.background_tasks: set` + asyncio.create_task 직접
- summary는 viewer banner (challenge §1)
- index 카드 재요약 버튼 drop (viewer banner에만)
- asyncio.to_thread for extract_pdf (debate §2)
- ingest display_filename_override (debate §2)
- documents.src_pdf_sha256 UNIQUE (debate §3)
- summarize 실패 non-fatal (challenge §3)
- 5 missing tests (debate §5) 모두 추가

## 5-D. Scoring (100, v1)

| Item       | Score / Max | Evidence |
| ---------- | ----------- | -------- |
| 독창성     | 14 / 15     | asyncio.to_thread + per-stage session + restart recovery + non-fatal summarize + UNIQUE-as-truth dedup. 감점: bg pool은 단순 set. |
| 완결성     | 34 / 35     | DoD 5 모두 + 30 신규 + 10 screenshots + live end-to-end. 감점: sample_ko stress는 Phase 6f. |
| 안정성     | 30 / 30     | UNIQUE + race fast-path + asyncio.to_thread + per-stage session + restart recovery + summarize graceful + 5 missing tests. |
| 확장성     | 19 / 20     | jobs 테이블이 future Phase 6e (streaming, 모델 토글, 백그라운드 패널 확장) 자연 흡수. 감점: hierarchical summarize는 Phase 6e. |
| **Total**  | **97 / 100** | |

## 5-E. Self verdict

- [x] PASS_CANDIDATE (≥95)
- [ ] FAIL → RE-CODE
- [ ] FAIL → RE-PLAN

근거:
- 5 DoD 모두 evidence (자동 + 시각 + live LLM)
- 383 fast tests + 7 LLM tests + `make check` RC=0
- 56초 end-to-end + 380단어 한국어 요약 + dedup + 거부 패턴 모두 확인
- 모든 debate 비판 ACCEPT (BackgroundTaskPool drop, asyncio.to_thread, UNIQUE, display_filename_override, viewer banner)
- 5 missing tests 추가
- self 97/100
- R1 cross-verify로 CONFIRM_PASS 기대.
