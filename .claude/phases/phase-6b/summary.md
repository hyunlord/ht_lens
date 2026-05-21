# Phase 6b — Summary (v2 — Planner-directed fix applied)

## Status

**PASS_CANDIDATE_98** (Worker self v3 — post Planner-directed fix).

Phase 6b R2 cross-verify가 REJECT (제안 84). R2가 R1 4 결함 모두 fix됨 인정 ("Round 1's defects were genuinely fixed") + 신규 substantive 2건 발견. Workflow round-cap 도달 → Planner-directed targeted fix.

Planner-directed fix 정책: **cross-verify 재호출 금지** + **Worker는 push 안 함** (Planner가 직접 push).

## Score

- **Self v3 (Planner-directed fix 후)**: **98 / 100**
- Self v2 (RE-CODE 후): 97 / 100
- Self v1: 93 / 100
- **Cross R1**: REJECT → 제안 81/100 (4 substantive: togglePanel viewModeActual, popstate blockId, page bounds, scheduleFarPageUnmount untested)
- **Cross R2**: REJECT → 제안 84/100. **"Round 1's defects were genuinely fixed"** 명시.

## Planner-directed fix applied (post R2)

Planner가 R2 substantive 2건에 대해 targeted fix 지시. **cross-verify 재호출 금지**.

| Commit | 내용 |
| ------ | ---- |
| `5652081` fix(phase-6b): jumpToThread sets activeThreadId explicitly (multi-thread accuracy) | navigateTo가 `opts.activateThreadId` 받아 `openPanel({threadId})`에 직접 전달 + auto-select 분기 우회. jumpToThread + popstate + loadDocument 모두 thread.id forward. defensive `setActiveThreadId` 재호출 추가. |
| `8f97604` fix(phase-6b): include threadId in history state for back/forward | pushState 페이로드 `{docId, page, blockId, threadId}` 형태로 확장. popstate가 `data.threadId` 복원 후 navigateTo로 분기. loadDocument에 `initialThreadId` 매개변수 추가 (cross-doc popstate). |

**회귀 가드 5건** (329 → 334):
- `test_jump_to_thread_uses_explicit_thread_id` (grep)
- `test_navigate_to_uses_explicit_thread_id_when_provided` (grep)
- `test_history_state_carries_thread_id` (grep — 4 markers)
- `test_viewer_history_thread_js.py::test_history_state_round_trip_preserves_block_and_thread_id` (jsdom-light: 두 thread 선택 후 back/forward 정확도)
- `test_viewer_history_thread_js.py::test_history_state_payload_includes_threadId_field_when_jumpToThread_runs` (grep — pushState payload shape)

## What was built

### Stage 0 (ROADMAP split)
- Phase 6b → Viewer Rework (v0.5)
- Phase 6c (전 6b) → Extraction Quality Debt (v0.6)
- Phase 6d (전 6c) → Infrastructure Polish (v1.0)
- Versioning 표 갱신

### Backend (1 endpoint)
- `GET /documents/{id}/pages-summary` → `PageSummary` list (page_num/width/height/rotation/render)
- 5 통합 테스트

### Frontend (큰 rework)
- `stage_container.js` (NEW, 273 lines): 단일 scroll + IntersectionObserver + mountPage Promise + AbortController + mountToken race guard + scheduleFarPageUnmount (±5 unmount radius) + scrollToPage + waitForBlockMounted + flashBlock
- `pane.js` (NEW): renderPane 양쪽 pane 호출 + buildPanes 1/2 pane scaffold
- `page_view.js`: `{side}` 매개변수 확장 (기존 동작 유지, rotation-banner + data-fallback 보존)
- `block.js`: syncBlockHover 양쪽 pane data-block-id 매칭
- `keyboard.js`: T → cycleViewMode (translation → original → both 순환)
- `viewer.js` (큰 rewrite):
  - `currentPage` singleton 제거 → `pageDataById` map (Phase 6a `handleRetranslate` 다중 페이지 iteration 호환)
  - `loadDocument` → `pages-summary` fetch + placeholder rows + IO attach + 초기 페이지 force-mount
  - `navigateTo` pushState (explicit) + replaceState (free-scroll)
  - history state에 blockId 포함 + popstate `{fromPopstate: true}` 분기
  - `stageContext` 헬퍼 + `maxPages` 전달
- `state.js`: viewMode + viewModeActual computed (panel + both → translation 강제) + pageDataById + pageSummaries + setViewMode/cycleViewMode/setPageData/clearPageData/setPageSummaries/setCurrentPage/findBlockInPageData
- `viewer.css`: stage-container + page-row + pane layout + block--hover-sync + rotation-banner 보존
- `viewer.html`: `#page-mount` → `#stage`. T-key hint 갱신.
- `api.js`: getPagesSummary + apiGet `{signal}` plumbing

### Tests (24 신규, 305 → 329)
- `test_api_pages_summary.py` (5)
- `test_static_serving.py` 확장 (+15: 11 R0 + 4 R1 regression guards)
- `test_stage_container_js.py` jsdom (4: 2 R0 race guard + 2 R1 bounds + scheduleFarPageUnmount)

### Screenshots (8) + tracked scenario
- 01 side-by-side both / 02 translation only / 03 original only
- 04 natural scroll mid / 05 zoom in both / 06 chat panel forces single
- 07 search jump / 08 sidebar thread jump
- `scripts/phase6b_scenario.py` tracked
- Memory benchmark: 6 페이지 peak JS heap 4.8 MB (post-RE-CODE)

## Files changed

`git diff --stat 1353a28..HEAD`:
- 1 backend router + 1 schema = ~70 lines
- 8 frontend (3 신규 + 5 수정) = ~750 lines
- 1 css 수정 + 1 html 수정
- 4 tests (1 신규 backend + static_serving 확장 + 1 신규 jsdom) = ~550 lines
- 1 scripts/phase6b_scenario.py 신규
- 8 screenshots + README
- 6 phase docs (plan/debate/challenge/verify v1+v2/verify-cross R1+R2/summary)

## Deviations from challenge

1. **page_view.js 유지** (challenge §1 ACCEPT) — 폐기 대신 `{side}` 확장. 회귀 위험 ↓.
2. **PageSummary 슬림화** (challenge §1 partial) — block_count drop.
3. **pageDataById map** (challenge §2) — currentPage singleton 제거.
4. **pushState/replaceState 분리** (challenge §2 alternative).
5. **mountPage Promise + AbortController + mountToken** (challenge §4) + R1 fix로 page bounds 추가.
6. **scrollIntoView({behavior: "auto"})** 첫 로드 (IO 재발화 방지).

## Both sides — disagreement summary

### Worker (self v2) 입장

- R1 4 substantive 결함 모두 fix + 6 회귀 가드 추가 (jsdom 2 + grep 4)
- 워크플로우 0-3-A "RE-CODE 새 코드 경로 단위 테스트 의무 표" 충족
- 329 fast tests + `make check` RC=0 + post-RE-CODE 라이브 재실행 8 screenshots 정상
- Peak heap 4.8 MB (R1 6.0 → R2 4.8, neighbour prefetch 404 제거 효과 정량 측정)
- DoD 4 모두 evidence + scheduleFarPageUnmount jsdom test로 200-page mechanism 직접 잠금
- self 97/100

### Codex (Cross R2) 입장

- R1 4 결함 fix 인정 ("Round 1's defects were genuinely fixed").
- 그러나 self 97 신뢰 불가:
  - **jumpToThread thread-accuracy**: multi-thread block에서 클릭한 thread와 다른 thread 자동 선택. `jumpToThread`가 `openPanel({threadId})` 후 `navigateTo` 호출 → navigateTo가 `existing.reduce(highest-id)`로 thread 재선택.
  - **history threadId 잃음**: R1 fix가 blockId만 추가, threadId는 없음. multi-thread block의 back/forward에서 정확한 thread 복원 불가.
  - **grep-only locks**: RE-CODE 분기 (togglePanel viewModeActual, history blockId) 가 source-string assertion. 행위 테스트 부족.
  - **52 페이지 sample_ko 부재**: 200-page DoD evidence가 6 페이지 + extrapolation에 의존.
  - **remote CI green 미확인**: pending push.
- 제안 84/100

### Worker 보충 의견

- R2가 발견한 **jumpToThread 다중 thread 버그**는 real defect (Phase 5에서 같은 동작이었으나 Phase 6b가 명시적으로 잠그지 않음). Planner 결정에 따라 R3 RE-CODE 또는 Phase 6c entry condition.
- R2의 grep-only critique은 valid이나 jsdom CI 미설치는 Phase 5/6a/6b 전반의 debt (Phase 6d 위임 항목).
- 200-page DoD evidence는 합성 fixture로 보강 가능 (sample_ko.pdf 미존재 시).
- threadId in history는 1-line fix이나 R3는 round-cap 위반.

## Evidence index

- plan: `.claude/phases/phase-6b/plan.md`
- debate: `.claude/phases/phase-6b/debate.md`
- challenge: `.claude/phases/phase-6b/challenge.md`
- verify (v2 latest, post RE-CODE): `.claude/phases/phase-6b/verify.md`
- verify-cross (R1 + R2): `.claude/phases/phase-6b/verify-cross.md`
- screenshots: `docs/phases/phase-6b/screenshots/01..08.png`
- README: `docs/phases/phase-6b/README.md`
- scenario: `scripts/phase6b_scenario.py`

## Known issues / debt

### R2 가 raised — 모두 처리됨 또는 Phase 6d 위임

1. **jumpToThread thread-accuracy** — ✅ Planner-directed fix `5652081`
2. **history threadId 누락** — ✅ Planner-directed fix `8f97604`
3. **RE-CODE grep-only** — Planner 결정: jsdom CI 설치는 **Phase 6d 워크플로우 보강 영역**. 본 fix 2건은 jsdom-light history round-trip test로 grep-only critique 부분 해소.

### Phase 6d (v1.0) 위임 항목

4. **jsdom CI 설치**: `npm install jsdom` + `.github/workflows/ci.yml` 확장. Phase 5/6a/6b 전반의 host-dependent test debt 일괄 해소.
5. **sample_ko 52페이지 stress**: Planner 결정에 따라 **6페이지 측정 + projection으로 DoD 충족** (peak 4.8 MB → 200페이지 13.6 MB << 500 MB 충분). 합성 fixture는 Phase 6d 검토.
6. **multiline translated test, search 200ms 엄격 단언, LLM live re-run after RE-CODE 워크플로우 보강**: Phase 6a R2 위임 + Phase 6b R2 위임 일괄 처리.

## Push status

**보류 (Planner-directed fix 정책)**.

- Workflow round-cap 도달 + Planner 명시 **cross-verify 재호출 금지**
- Planner-directed fix 정책: **Worker는 push 안 함, Planner가 직접 push**
- Self 98/100 (R2 97 → v3 98), R2 substantive 결함 2건 모두 fix + 회귀 가드 5건 추가
- Local main은 `origin/main` 대비 **15 commits ahead** (`1353a28..e445788`)
- CI green 확인은 push 후 (Planner)

## Recommended next

- **Planner의 push 결정 후 v0.5 태그 + push**
- **Phase 6c 진입** (v0.6):
  - header heuristic / 멀티컬럼 reading order / samples.md determinism / 회전 페이지 정밀 매핑
- **Phase 6d (v1.0)**:
  - jsdom CI 설치 → R2 grep-only critique 자연 해소 + Phase 6a R2 위임 처리
  - 백그라운드 패널, 모델 빠른 토글, streaming response (SSE)
  - Playwright 자동 시나리오 (Phase 5 + 6a + 6b 통합)
  - LLM-driven thread title
  - sample_ko 52페이지 합성 fixture (선택)
  - LLM live re-run after RE-CODE 워크플로우 보강
