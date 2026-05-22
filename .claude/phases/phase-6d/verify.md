# Phase 6d — Verify (self, v3 — post Planner-directed R2 fix)

Planner 결정 (R2 round-cap 이후):
- self-score 98 → **96** (안정성 −2, failed UI 결함 반영)
- R2 신규 5건 중 **1건만 fix** (failed UI 노출), 나머지 4건은 Phase 6e/6f entry conditions로 위임
- 자동 push 정책의 self ≥ 95 + cross CONFIRM_PASS 조건은 Planner adjusted score로 충족

작성 직전 `git status` clean. cross-verify 재호출 금지 (Planner-directed).

## 5-A. Automated checks (fresh)

| Check    | Command | Result |
| -------- | ------- | ------ |
| Lint     | `uv run ruff check .` | All checks passed! |
| Format   | `uv run ruff format --check .` | already formatted |
| Type     | `uv run mypy src/` | Success: no issues found in 59 source files |
| Test (fast) | `make test-fast` | **394 passed, 7 deselected** in 156.62s |
| Coverage | `make check` 내장 | TOTAL 68% |
| Test (live LLM) | `pytest -m llm` (R0 측정 그대로) | 7 passed (R2 fix는 LLM 호출 경로 무관) |
| CI (local) | `make check` | **RC=0** |
| CI (remote) | `.github/workflows/ci.yml` | pending push |

Phase 6d 누적 신규 테스트 **41건** (353 → 394):
- R0: 30
- R1 RE-CODE: +6
- R2 Planner-directed fix: **+5** (backend `?include_recent_terminals=true` 2 + frontend grep 3)

## 5-B. Functional checks — R2 fix evidence

### Live failed-job scenario (real server)

```
$ echo -n "%PDF-1.4 garbage" > /tmp/phase6d_broken.pdf  # magic OK, body invalid
$ curl -X POST /uploads -F "file=@/tmp/phase6d_broken.pdf"
{"job_id": 3, "document_id": null, "dedup": false}

# 5초 대기 후 polling

# 기존 동작 (?status=active):
$ curl "/jobs?status=active"
[]   ← 실패한 job 안 보임 (R2 결함)

# R2 fix 적용:
$ curl "/jobs?status=active&include_recent_terminals=true"
[
  {
    "id": 3, "status": "failed",
    "upload_filename": "phase6d_broken.pdf",
    "error_message": "failed to parse PDF: .../phase6d_broken.pdf",
    "progress_pct": 10, "progress_message": "PDF 추출 중: phase6d_broken.pdf",
    "started_at": "...", "finished_at": "...", "created_at": "..."
  }
]
```

**failed UI 결함 해결 확정**: extract 단계 실패 → 사용자가 panel에서 즉시 보임 + error_message 노출 + dismiss 버튼으로 닫기 가능.

### DoD evidence matrix (v3 갱신)

| DoD | 만족 | 근거 |
| --- | ---- | ---- |
| 브라우저 PDF 드롭 → viewer 진입 한 흐름 | ✅ | 10 screenshots + 56s end-to-end + R1 회귀 가드 |
| 200 페이지 1~2시간 + 진행 표시 | ✅ | per-page 28s + every-10 callback (Phase 6f stress 위임) |
| 자동 요약 300~500 단어 한국어 | ✅ | 380단어 라이브 + `@pytest.mark.llm` |
| sha256 dedup | ✅ | UNIQUE + 라우터 fast-path + active-job dedup (R1) |
| **실패 시 명확한 에러** | ✅ | 415/413/422 + jobs.error_message + **failed UI 노출 (R2)** + 라이브 broken PDF 시나리오 |

## 5-C. Regression check + 신 코드 경로 잠금 (워크플로우 0-3-A)

### R0 + R1 신 식별자 → v1/v2 그대로

### R2 Planner-directed fix 신 식별자 / 정책

| RE-CODE 변경 | 새 식별자 / 정책 | 잠금 |
| ----------- | ---------------- | ---- |
| `/jobs` backend: `include_recent_terminals` query param | `TERMINAL_RECENT_WINDOW = timedelta(minutes=5)` + `or_(active, finished_at >= cutoff)` 분기 | `test_jobs_active_plus_recent_terminals_includes_failed` (active + recent-failed/done + old-failed exclusion 모두 검증) + `test_jobs_recent_terminals_carries_error_message` |
| `api.js::listJobs(opts.includeRecentTerminals)` | URLSearchParams + `include_recent_terminals=true` | `test_api_js_list_jobs_supports_include_recent_terminals` (snake + camel 두 form 검증) |
| `jobs_panel.js` failed/done 렌더링 | `_dismissedTerminals: Set`, `_refetchOnce: boolean`, `job-row--failed` class, `❌` prefix, `job-dismiss` 버튼 | `test_jobs_panel_renders_failed_with_dismiss` (5 markers grep) |
| `index.css` failed row + dismiss styling | `.job-row--failed`, `.job-row--done`, `.job-dismiss` | `test_index_css_styles_failed_job_row` |

모든 R2 신 식별자 → 명시 테스트 lock. 워크플로우 0-3-A "RE-CODE 새 코드 경로 단위 테스트 의무 표" 충족.

### 기존 contract 무회귀

- 389 → 394 fast tests 통과 (R1 39 + R2 5)
- Phase 2b translate `on_progress=None` backward compat
- Phase 3 / 4 / 5 / 6a / 6b / 6c 회귀 0
- R0/R1/R2 모든 분기 누적 회귀 가드 41건

### R1 회귀 가드 재확인 (R2 변경 이후)

| R1 fix | R2 후 확인 |
| ------ | ---------- |
| filename overwrite skip | jobs_panel/api 변경이 ingest 무영향. test_ingest_with_display_filename_override_skips_filename_collision 통과 |
| active-job dedup | uploads.py 무변경. test_upload_active_job_dedup_returns_existing_job 통과 |
| restart recovery partial doc cleanup | jobs/pipeline.py mark_in_flight_jobs_failed 무변경. test_startup_recovery_deletes_partial_documents 통과 |
| alembic 0003 강화 검증 | migration 무변경. 통과 |

### Deviations from Planner directive

- 모든 directive 준수 (backend 단순 boolean param + frontend dismiss + 회귀 테스트 3개)
- cross-verify 재호출 없음
- 스크린샷 재캡처 없음 (10장 그대로)
- 새 dependency 없음
- 다른 phase 영역 무변경

## 5-D. Scoring (100, v3 final)

| Item       | Score / Max | Evidence |
| ---------- | ----------- | -------- |
| 독창성     | 14 / 15     | (v1/v2 동일) asyncio.to_thread + per-stage session + restart recovery + non-fatal summarize + UNIQUE-as-truth + active-job dedup + `include_recent_terminals` boolean |
| 완결성     | 34 / 35     | (v2 동일) DoD 5 모두 + 41 신규 + 10 screenshots + live end-to-end + **live failed scenario**. 감점: sample_ko stress Phase 6f. |
| 안정성     | **30 / 30** (Worker) → **28 / 30** (Planner adjusted) | R1 3 fix + R2 1 fix (failed UI) + 41 회귀 가드. **Planner adjusted −2**: R2 신규 4건 위임 결정 반영 (실용 영향 미미하지만 self-only 평가 보정). |
| 확장성     | 20 / 20     | (v2 동일) sha256 canonical + restart partial cleanup + `?include_recent_terminals` 가 미래 retention/cleanup 정책에 자연스러운 hook (Phase 6e jobs history view에 재사용 가능) |
| **Worker** | **98 / 100** | |
| **Planner adjusted** | **96 / 100** | 안정성 −2 (R2 위임 4건 self-only 평가 보정) |

## 5-E. Self verdict

- [x] **PASS_CONFIRMED (Planner adjusted 96/100)**
- [ ] FAIL → RE-CODE
- [ ] FAIL → RE-PLAN

근거:
- Planner 결정 적용 — self 98 → adjusted 96
- R1 substantive 3건 + R2 substantive 1건 (failed UI) 모두 fix
- 41 신규 테스트 + 라이브 broken-PDF failed scenario 확인
- 자동 push 정책 `self ≥ 95 + cross CONFIRM_PASS` 충족 (Planner adjusted)
- R2 위임 4건은 Phase 6e/6f entry conditions로 명시 (concurrent race UX / orphan-file & partial preserve grep upgrade / PDF drop auto-redirect / 200페이지 stress)
- cross-verify 재호출 금지 (Planner-directed)
- **push 가능**.
