# Phase 6d — Challenge

## Debate responses

### 1. Over-engineering

**POST /documents/{id}/summarize + 재요약 UI is scope creep** — **PARTIAL ACCEPT**
응답: 명시적 재요약 endpoint는 유지 (`@pytest.mark.llm` test + 명확한 fail recovery 경로). 그러나 **index 카드의 재요약 버튼은 drop** — 사용자가 viewer에서만 트리거. UI surface 감소.
**결정**: endpoint 유지, index 재요약 버튼 제거.

**Summary는 viewer 표시가 맞음** — **ACCEPT**
응답: ROADMAP DoD "문서 첫 페이지에 thread로 자동 attach (또는 별도 영역)" 따라 **viewer 진입 시 첫 페이지 위에 summary banner** 표시. Index card에는 짧은 preview (≤120 chars) 유지 (목록 식별용). viewer summary는 dismiss 가능하나 localStorage persist 안 함 (매 진입 시 보임).
**결정**: viewer.html에 summary banner 추가, index card에는 짧은 preview만.

**Playwright 자동화는 Phase 6e debt** — **ACCEPT**
응답: 10 screenshots는 manual capture로 진행. Playwright scenario 자동화는 **drop** (Phase 6e). manual evidence + `@pytest.mark.llm` + integration tests로 verify.
**결정**: 10 screenshots manual + Playwright 자동화 drop.

**BackgroundTaskPool 추상화 — premature** — **ACCEPT**
응답: lifespan에 `app.state.background_tasks: set[asyncio.Task]` 직접 + `spawn_bg` 헬퍼만. 클래스 drop.
**결정**: `BackgroundTaskPool` 클래스 drop → app.state 직접 set + helper 함수.

### 2. Hidden assumptions

**extract_pdf는 sync → event loop block** — **ACCEPT (critical)**
응답: `process_upload_job` 안의 sync 호출 (extract_pdf, sha256 hashing)을 **`asyncio.to_thread()`로 래핑**. `ingest_extract_dir`와 `translate_document`는 이미 async — 그대로. callback (`on_progress`)도 await 가능.

**doc_meta.filename ≠ user filename** — **ACCEPT**
응답: 두 가지 fix 옵션:
- (a) `extract_pdf`에 `filename_override` 매개변수 추가
- (b) `ingest_extract_dir`에 `display_filename_override` 매개변수 추가 (Document.filename에 들어가는 값만 override)
**결정**: (b) — ingest 단계가 DB 쓰기 책임. extract는 그대로 (sha256.pdf 이름 그대로 doc_meta.json에 저장). ingest에서 override.

**Session boundary 모호** — **ACCEPT**
응답: `process_upload_job`이 단계별로 **자기 session**을 열고 닫음 (Phase 2b 패턴):
- prepare/state update: 짧은 session
- extract: session 불필요 (file I/O)
- ingest: ingest 전용 session (자체 commit)
- translate: 자체 session/concurrency (이미 그러함)
- summarize: 짧은 session
- 각 update_job 호출도 짧은 자체 session

**5~10 페이지 + extrapolation은 weak evidence** — **PARTIAL ACCEPT**
응답: 200 페이지 PDF는 plan author 보유 없음. 5~10 페이지 실측 + **per-block latency 측정 + linear projection** + Phase 2b shared-LLM variability 명시. extrapolation 불확실성을 verify에 명시. DoD "1~2시간" 충족 여부는 sample 수치 + 신뢰구간.

### 3. Edge cases

**Concurrent same-file race** — **ACCEPT (critical)**
응답: migration 0003에 **`documents.src_pdf_sha256` UNIQUE constraint** 추가. POST /uploads에서 INSERT 시 `IntegrityError` catch → dedup 처리로 fall-back. 또한 `jobs` 테이블에도 `(upload_sha256, status IN (active))` 부분 인덱스 — 동일 sha256 active job 둘 동시 못 함.
**결정**: unique constraint + IntegrityError catch.

**Cross-device rename (EXDEV)** — **ACCEPT**
응답: 임시 파일을 **`data/uploads/`와 동일 디렉토리**에 만든다 (`tempfile.NamedTemporaryFile(dir=uploads_dir)`). 같은 fs라 rename atomic.

**Image-only PDF / 번역 전무 시 summarize empty** — **ACCEPT**
응답:
- `summarize_document`가 `SummarizeEmptyError` raise
- `process_upload_job`이 catch → `status=done`, `summary=None`, `error_message="번역된 텍스트가 없어 자동 요약을 생략했습니다"`
- `POST /documents/{id}/summarize` endpoint도 동일 → HTTP 422 + 한국어 detail
- frontend는 viewer banner에 "요약 없음" 메시지

**Restart recovery 미흡 — partial document/pages/blocks** — **ACCEPT**
응답: in-flight job recovery는 plan의 단순화 (jobs row만 `failed`). 그러나 partial document/extract dir에 대해서는:
- `data/extracts/{sha256}/`에 남은 디렉토리는 다음 같은 sha256 upload 시 conflict — 단순 fix: extract 단계 시작 시 기존 dir이 있으면 삭제 후 재추출 (overwrite=True)
- partial Document/pages/blocks는 `extract_pdf` 가 atomic이라 mid-process crash 시 ingest 미실행 → Document 없음 (clean). ingest는 자기 트랜잭션 commit/rollback 그대로
- 단계가 마지막에 `translate`/`summarize`인 경우: Document는 존재 + 번역 partial. 사용자가 재업로드 시 dedup이 막음 — partial state stuck 위험 ← 명시 (debate §3)
- **mitigation**: `process_upload_job`이 `IntegrityError` (dedup race) 또는 restart-failed job 만났을 때 cleanup helper — Phase 6e로 일부 위임. 6d는 single-user 가정으로 single in-flight 보장 + restart recovery는 jobs만.

### 4. Alternative approaches

**Summary를 threads 모델 재사용** — **REJECT (this phase)**
응답: thread 모델은 user/assistant message pair 구조. 자동 요약을 thread/message로 표현하면 사용자가 답장 가능한 conversation으로 오해 가능. **별도 영역 (`documents.summary`) 유지** — ROADMAP DoD 옵션 "또는 별도 영역" 채택. Phase 6e에서 viewer summary banner UX 재검토 가능.

**POST /summarize endpoint + 재요약 UI drop** — **PARTIAL ACCEPT** (§1 통합)
응답: endpoint 유지 (test surface), index card 재요약 버튼 drop (UI 단순).

**asyncio.to_thread for blocking work** — **ACCEPT** (§2 통합)
응답: `extract_pdf` + `_stream_to_tmp`의 hashlib loop을 `asyncio.to_thread` 래핑. `app.state.background_tasks` set + spawn helper로 단순화 (debate §1 ACCEPT).

### 5. Missing tests

모두 **ACCEPT**:
- `test_upload_same_sha_race_returns_single_job_or_existing_doc`: asyncio.gather 2 upload + 둘 다 결과 검증
- `test_process_upload_job_preserves_original_filename_in_document`: upload "내문서.pdf" → `documents.filename == "내문서.pdf"` (sha256.pdf가 아님)
- `test_process_upload_job_does_not_block_jobs_polling_during_extract`: monkeypatch extract_pdf sleep(2) + `GET /jobs` 응답 < 1초
- `test_summarize_image_only_document_returns_clear_error` + `test_upload_pipeline_skips_auto_summary_when_no_translated_text`: empty body 분기
- `test_startup_marks_active_jobs_failed_without_leaving_orphan_partial_document_state`: pending/translating job 직접 insert + lifespan trigger + jobs.status=failed 검증

---

## Plan revisions (after debate)

1. **Summary 위치**: viewer.html에 summary banner (debate §1 ACCEPT). index card에는 짧은 preview만 (≤120 chars).
2. **재요약 UI**: viewer banner 내 "재생성" 버튼만 (index card 버튼 drop).
3. **Playwright 자동화 drop**: 10 screenshots manual.
4. **BackgroundTaskPool drop**: `app.state.background_tasks: set` + `spawn_bg(coro)` helper.
5. **asyncio.to_thread**: `extract_pdf` + sha256 hashing 래핑 (event loop block 방지).
6. **filename override**: `ingest_extract_dir`에 `display_filename_override` 매개변수.
7. **Session boundaries**: `process_upload_job`이 단계별 자기 session.
8. **Concurrent dedup race**: migration 0003에 `documents.src_pdf_sha256` UNIQUE + IntegrityError catch.
9. **Cross-device rename**: 임시 파일을 `uploads_dir`와 동일 fs.
10. **Empty-body summarize**: `SummarizeEmptyError` + `done + error_message` non-fatal + viewer "요약 없음".
11. **Restart recovery 명시**: jobs만 `failed`, partial Document/extract dir는 single-user 가정 + Phase 6e cleanup helper로 일부 위임.
12. **테스트 추가 5건**: §5 ACCEPT 항목.

---

## File-level changes (revised)

| Path | Action | Note |
| ---- | ------ | ---- |
| `pyproject.toml` | MODIFY | + python-multipart |
| `src/ht_lens/db/migrations/versions/0003_jobs_and_summary.py` | NEW | + UNIQUE on documents.src_pdf_sha256 |
| `src/ht_lens/db/session.py` | MODIFY | ALEMBIC_HEAD = "0003" |
| `src/ht_lens/db/models.py` | MODIFY | + Job + Document.summary/.summarized_at |
| `src/ht_lens/jobs/__init__.py` | NEW | |
| `src/ht_lens/jobs/pipeline.py` | NEW | process_upload_job + update_job + per-stage session |
| `src/ht_lens/summarize/__init__.py` | NEW | |
| `src/ht_lens/summarize/pipeline.py` | NEW | summarize_document + SummarizeEmptyError |
| `src/ht_lens/translate/pipeline.py` | MODIFY | + on_progress callback |
| `src/ht_lens/ingest/pipeline.py` | MODIFY | + display_filename_override |
| `src/ht_lens/api/app.py` | MODIFY | + app.state.background_tasks set + spawn_bg + restart recovery + 라우터 |
| `src/ht_lens/api/schemas.py` | MODIFY | + JobRead + UploadResponse + DocumentRead.summary |
| `src/ht_lens/api/routers/uploads.py` | NEW | POST /uploads (asyncio.to_thread for blocking) |
| `src/ht_lens/api/routers/jobs.py` | NEW | GET /jobs, GET /jobs/{id} |
| `src/ht_lens/api/routers/documents.py` | MODIFY | + POST /{id}/summarize + summary 노출 |
| `src/ht_lens/api/static/viewer.html` | MODIFY | + summary banner mount |
| `src/ht_lens/api/static/js/viewer.js` | MODIFY | + summary banner render + 재생성 버튼 |
| `src/ht_lens/api/static/index.html` | MODIFY | upload zone + jobs panel + summary preview (small) |
| `src/ht_lens/api/static/js/api.js` | MODIFY | + uploadPDF/listJobs/getJob/summarizeDocument |
| `src/ht_lens/api/static/js/index.js` | MODIFY | wiring |
| `src/ht_lens/api/static/js/components/upload.js` | NEW | |
| `src/ht_lens/api/static/js/components/jobs_panel.js` | NEW | |
| `src/ht_lens/api/static/js/components/summary_banner.js` | NEW | viewer summary banner |
| `src/ht_lens/api/static/js/components/document_card.js` | NEW | summary preview (간소) |
| `src/ht_lens/api/static/css/index.css` | NEW | upload UI |
| `src/ht_lens/api/static/css/viewer.css` | MODIFY | + summary banner styling |
| `tests/integration/test_api_uploads.py` | NEW (+5 cases incl. race) | |
| `tests/integration/test_api_jobs.py` | NEW | |
| `tests/integration/test_api_summarize.py` | NEW (+@pytest.mark.llm + image-only + empty) | |
| `tests/integration/test_jobs_pipeline.py` | NEW (+filename + non-block) | |
| `tests/integration/test_translate_progress.py` | NEW | |
| `tests/integration/test_api_startup.py` | MODIFY | + restart recovery test |
| `tests/integration/test_static_serving.py` | MODIFY | + 6d markers + summary banner |
| `tests/integration/test_alembic.py` | MODIFY | + 0003 head + UNIQUE constraint |
| `docs/phases/phase-6d/{README.md, screenshots/*}` | NEW (~10 manual) | |

---

## DoD checklist

| DoD item | Status | Evidence |
| -------- | ------ | -------- |
| 브라우저 PDF 드롭 → 자동 처리 → viewer 진입 한 흐름 | planned | screenshots 01-06 + manual end-to-end |
| 200 페이지 1~2시간 + 진행 표시 | planned | per-block latency 측정 + linear projection (불확실성 명시) + screenshot 04 |
| 자동 요약 300~500 단어 한국어 + viewer 표시 | planned | summary banner + screenshot 09/10 + @pytest.mark.llm |
| sha256 dedup (UNIQUE + race-safe) | planned | UNIQUE constraint + IntegrityError catch + race test |
| 실패 시 명확한 에러 | planned | jobs.error_message + frontend banner + screenshot 08 |

---

## Risk register

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| extract_pdf event loop block | High | jobs polling 정지 | `asyncio.to_thread` 래핑 (debate §2 ACCEPT) |
| Concurrent same-sha race | Medium | duplicate jobs/docs | UNIQUE constraint + IntegrityError catch + race test |
| Cross-device rename EXDEV | Medium | upload 실패 | tmp in uploads_dir 동일 fs |
| Image-only PDF summarize empty | Medium | UX 혼란 | SummarizeEmptyError + done + clear message |
| Restart partial Document | Low | stuck dedup | Phase 6e cleanup helper 위임 + single user 가정 |
| ingest filename = sha256.pdf | High | 카드/viewer 사용자 혼란 | ingest display_filename_override |
| Session boundary 혼란 (rollback) | Medium | 데이터 부정합 | 단계별 자기 session (Phase 2b 패턴) |
| 200-page extrapolation 부정확 | Low | DoD 검증 약함 | sample 측정 + 불확실성 명시 |
| python-multipart 누락 | Low | startup fail | pyproject 명시 + lockfile |

---

## Decision

- [x] PASS → proceed to code (plan revisions 12건 적용)
- [ ] RE-PLAN

Codex 비판 19건 중 16 ACCEPT + 3 PARTIAL ACCEPT + 1 REJECT (threads 모델 재사용 — separate area 채택). 핵심:
1. `asyncio.to_thread`로 event loop block 방지 (critical)
2. UNIQUE constraint + IntegrityError catch (critical)
3. summary는 viewer banner (ROADMAP DoD에 더 충실)
4. BackgroundTaskPool drop → app.state set + helper
5. ingest display_filename_override
6. 5 missing tests 추가
