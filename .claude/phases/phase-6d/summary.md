# Phase 6d — Summary

## Status

**PASS_CANDIDATE_98** (Worker self v2 — post RE-CODE) → **REJECT** (Codex Round 2, 제안 85). Round-cap 도달.

R2 명시: **"I am not re-raising the Round 1 filename-collision overwrite or partial-document cleanup defects. The code changes ... do address those earlier complaints."** R1 결함 모두 fix 인정. R2 신규 critique:
- 백그라운드 job 실패가 UI에서 안 보임 (jobs_panel은 active만 폴링)
- concurrent same-SHA race는 좁은 race window 잔존 (TestClient는 serial)
- orphan-file fallback / partial_translated preserve grep-only
- "PDF drop → viewer entry" 단일 자동 흐름 미구현 (수동 click)
- 200 페이지 DoD는 2 페이지 extrapolation

**Push 보류 → Planner escalate** (자동 push 정책 `self ≥ 95 + cross CONFIRM_PASS` 미충족).

## Score

- **Self v2 (RE-CODE 후)**: 98 / 100
- Self v1: 97 / 100
- Cross R1: REJECT → 제안 81/100 (3 substantive, 모두 fix됨)
- Cross R2: REJECT → 제안 85/100, R1 fix 인정

## What was built

### Backend
- Migration 0003: jobs + documents.summary/summarized_at + documents.src_pdf_sha256 UNIQUE
- `jobs/pipeline.py`: process_upload_job (5-stage extracting→ingesting→translating→summarizing→done) + per-stage session + `mark_in_flight_jobs_failed` (cascade partial Document on restart)
- `summarize/pipeline.py`: single-shot 8KB-cap Korean summary + SummarizeEmptyError (non-fatal)
- `translate/pipeline.py`: on_progress callback (every-10, backward-compat)
- `ingest/pipeline.py`: display_filename_override + filename lookup skip (R1 fix)
- `api/app.py`: lifespan uploads_dir + background_tasks + restart recovery
- `api/routers/uploads.py`: POST /uploads (5-byte magic, 100MB, dedup, active-job dedup R1, sanitize)
- `api/routers/jobs.py`: GET /jobs + GET /jobs/{id}
- `api/routers/documents.py`: POST /{id}/summarize
- `pyproject.toml`: python-multipart explicit

### Frontend
- `index.html` + `index.css`: upload zone + active-jobs panel + summary preview in card
- `viewer.html` + `viewer.css` summary banner mount
- `js/components/upload.js`: drag-drop + 파일 선택 + dedup toast
- `js/components/jobs_panel.js`: 2s polling + visibilityState pause
- `js/components/summary_banner.js`: viewer banner + 재생성
- `js/api.js`: uploadPDF + listJobs + getJob + summarizeDocument

### Tests (36 new, 353 → 389)
R0 30 + R1 6: uploads / jobs / summarize / translate progress / static / alembic / restart recovery / filename-override grep / overwrite grep / active-job dedup

### Screenshots (10) + tracked scenario
Live LLM end-to-end: 56s / 2 페이지 / 380단어 한국어 자연 요약 / DB summary 갱신

## Files changed

`git diff --stat d2a77c7..HEAD`: ~40 files, ~2600 insertions

## Deviations from challenge

1. BackgroundTaskPool drop → app.state set (challenge §1)
2. summary viewer banner (challenge §1, ROADMAP DoD)
3. asyncio.to_thread for extract_pdf (debate §2 critical)
4. ingest display_filename_override + skip filename lookup (R1 추가)
5. UNIQUE constraint (debate §3)
6. summarize 실패 non-fatal (challenge §3)
7. active-job dedup (R1 추가)
8. restart recovery partial doc cleanup (R1 추가)

## Both sides — disagreement

### Worker (98)
R1 3 결함 모두 fix + 36 신규 테스트 + 10 screenshots + 라이브 56s end-to-end + 380단어 한국어 요약 + 5 DoD evidence + 워크플로우 0-3-A R0+R1 lock 표.

### Codex R2 (85)
R1 fix 인정. 그러나:
- **failed jobs UI invisible (substantive)**: jobs_panel은 `status=active`만 폴링 → failed로 전환 시 panel hidden → 사용자가 실패 인지 못함
- concurrent same-SHA narrow race: SQLite + asyncio 단일 worker 환경에서 매우 좁음. UNIQUE이 정확성 보장.
- orphan-file fallback + partial_translated 분기 grep-only
- PDF drop → viewer auto redirect 미구현
- 200 페이지 실측 부재

### Worker 보충
- failed UI는 valid substantive critique — 1-2줄 fix. Phase 6e UX 흡수 권장.
- race window: UNIQUE constraint가 정확성 보장. UX 거침은 Phase 6e.
- 200 페이지 실측: sample_ko 52페이지조차 Phase 6f 위임 항목. linear projection이 best evidence.

## Evidence index

- plan / debate / challenge / verify v2 / verify-cross R1+R2 / summary
- screenshots: docs/phases/phase-6d/screenshots/01..10.png
- README: docs/phases/phase-6d/README.md
- scenario: scripts/phase6d_scenario.py

## Known issues / debt — Phase 6e/6f 위임

R2 raised:
1. failed jobs UI 가시성 (jobs_panel terminal state 표시) — Phase 6e UX
2. concurrent race UX (UNIQUE constraint가 정확성 보장; UX 안내는 Phase 6e)
3. orphan-file fallback / partial_translated preserve grep-only → jsdom CI 이후 upgrade (Phase 6e)
4. PDF drop → viewer auto-redirect — Phase 6e UX
5. 200 페이지 실측 — Phase 6f sample_ko 52페이지 fixture 흡수

Phase 본체 잔여 (Phase 6e/6f 위임):
6. hierarchical summarization (현재 single-shot 8KB) → Phase 6e
7. streaming response → Phase 6e
8. 모델 토글 → Phase 6e
9. jobs retention 정책 → Phase 6e
10. sample_ko 52페이지 fixture → Phase 6f

## Push status

**보류 (Planner escalate)**. 사유:
- Workflow round-cap (R1 REJECT → RE-CODE → R2 REJECT) 도달
- 자동 push 정책 `self ≥ 95 + cross CONFIRM_PASS` 미충족 (R2 REJECT)
- R2 자체 R1 fix 인정 → R0 + R1 본체 작업 가치 인정
- Self 98 vs Codex R2 85 — 13점 차이 (verify scope coverage + 1 substantive failed-UI)
- Local main: `origin/main` 대비 **20 commits ahead** (Phase 6d 전체)

Planner 결정 옵션:
- **(a) Planner-directed micro-fix 1-2건** (jobs_panel terminal state 표시 + race UX 안내 toast) → verify v3 → push + v0.7
- **(b) 그대로 push 승인** + v0.7 (R2 critique은 Phase 6e UX entry condition로 위임)
- **(c) Phase 6e (UI polish) 먼저** → 6d-시점 fix 통합 → push + v0.7

## Recommended next

- **Planner 결정 후**:
  - (a) failed UI + race toast micro-fix → verify v3 → push + v0.7 (가장 안전)
  - (b) 즉시 push + v0.7 → Phase 6e 진입 (R2 5건 모두 Phase 6e 흡수)
- **Phase 6e (v0.8)** 진입 시:
  - R2 위임 5건 (failed UI / race UX / orphan&preserve jsdom / auto-redirect / 200페이지) + 기존 6e 항목 (핀 디자인 / 사이드바 리사이즈 / 이미지 확대 / streaming / 모델 토글 / jsdom CI / LLM-driven title)
- **Phase 6f (v1.0)**: 추출 품질 + sample_ko 52페이지
