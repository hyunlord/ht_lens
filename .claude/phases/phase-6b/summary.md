# Phase 6b — Summary

## Status

**PASS_CANDIDATE_97** (Worker self v2 — post RE-CODE) → **REJECT** (Codex Round 2, 제안 84). Round-cap 도달.

R2가 R1의 4 결함 모두 fix됨 인정 ("Round 1's defects were genuinely fixed"). R2 신규 발견:
- jumpToThread thread-accuracy 버그 (multi-thread block에서 클릭한 thread와 다른 thread 자동 선택)
- history state가 threadId 잃음 (R1 fix는 blockId만 추가)
- RE-CODE branches가 여전히 grep-only (jsdom 행위 테스트 부족)

**Push 보류 → Planner escalate** (자동 push 정책 `self ≥ 95 + cross CONFIRM_PASS` 미충족).

## Score

- **Self v2 (RE-CODE 후)**: 97 / 100
- **Self v1**: 93 / 100
- **Cross R1**: REJECT → 제안 81/100 (4 substantive: togglePanel viewModeActual, popstate blockId, page bounds, scheduleFarPageUnmount untested)
- **Cross R2**: REJECT → 제안 84/100. **"Round 1's defects were genuinely fixed"** 명시.

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

### R2 가 raised — substantive but small scope

1. **jumpToThread thread-accuracy**: multi-thread block에서 클릭한 thread 보장 안 됨. Fix: `jumpToThread` 안의 `navigateTo` 호출 후 `setActiveThreadId(thread.id)` 재호출 + `navigateTo` 안의 auto-select 분기에 `state.activeThreadId` 우선 사용.
2. **history threadId 누락**: pushState payload에 threadId 추가 + popstate restore 시 threadId fallback. 5-10줄 fix.
3. **RE-CODE grep-only**: jsdom CI 도입 시 자연스럽게 해소 (Phase 6d).

### Phase 본체 잔여 한계

4. **200 페이지 실측 부재**: sample_ko.pdf 없음. 합성 fixture로 보강 가능.
5. **jsdom CI 미설치**: Phase 5/6a/6b 전반 debt → Phase 6d 위임.
6. **sample_ko 52페이지 stress**: 미존재 PDF.

## Push status

**보류 (Planner escalate)**. 사유:
- Workflow Stage 6 자동 push 정책: `self ≥ 95 + cross CONFIRM_PASS` (R2 REJECT이므로 비충족)
- Cross-verify round-cap (2 라운드) 도달
- Self 97 vs Codex R2 84 — 13점 차이는 substantive (jumpToThread + threadId history는 real bugs) + verify scope critique 혼합
- R2 자체가 "Round 1's defects were genuinely fixed" 명시 → R0 + R1 본체 작업의 가치 인정
- Local main은 origin/main 대비 12 commits ahead

Planner 결정 옵션:
- **(a) Planner-directed micro-fix 2건** (jumpToThread thread-accuracy + history threadId) → verify v3 → push + v0.5 태그. 가장 합리적.
- **(b) 그대로 push 승인** + v0.5 태그. R2 critique을 Phase 6d/post-release fix로 위임.
- **(c) 추가 RE-CODE** (round-cap 위반 — 비권장).
- **(d) 합성 sample_ko 52페이지 fixture 추가** → memory DoD 실측 evidence + push.

## Recommended next

- **Planner 결정 후**:
  - (a) 선택: 2건 micro-fix → verify v3 (R3 cross-verify 금지) → push + v0.5
  - (b) 선택: 즉시 push + v0.5 + jumpToThread/threadId history는 Phase 6c entry condition
  - (d) 선택: stress fixture 추가 → 200-page direct evidence → push + v0.5
- **Phase 6c 진입 시 흡수**:
  - header heuristic / 멀티컬럼 / samples.md / 회전 페이지 (R2 deferred 영역도 흡수 가능)
- **Phase 6d (v1.0)**:
  - jsdom CI 설치 → R2 grep-only critique 자연 해소
  - + 백그라운드 패널, 모델 토글, streaming, Playwright suite, LLM-driven title
