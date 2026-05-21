# Phase 4 — Summary

## Status

**PASS_CANDIDATE_93** (Worker self v2) → **DOWNGRADE** (Codex Round 2).
Workflow Stage 5c round-cap(2) 도달. **Push 보류 → Planner escalate.**

## Score

- **Self v2 (RE-CODE 후)**: 93 / 100
- **Self v1**: 92 / 100
- **Cross R1**: REJECT → 제안 73/100 (4 substantive 결함 지적)
- **Cross R2**: DOWNGRADE → 제안 81/100 (R1 결함은 해소, 그러나 verify scope 부족 + 새 stale-status 발견)

Round 2 cross-verify는 **"Round 1's concrete viewer bugs appear fixed"** 를 명시함. RE-CODE가 제대로 작동했음을 인정.

## What was built

Phase 4 = vanilla HTML/CSS/JS viewer frontend. v0.2 마일스톤의 frontend 절반.

### Static viewer assets (`src/ht_lens/api/static/`)
- `index.html`: 문서 카드 리스트 (`DocumentRead` 메타 표시)
- `viewer.html`: sidebar + page-view + Phase 5 우측 슬롯
- `css/{base,viewer}.css`: 디자인 토큰 + 레이아웃 + block 오버레이 (translation 모드 translucent panel, original 모드 transparent)
- `js/api.js`: fetch wrapper + `ApiError`
- `js/state.js`: localStorage zoom/overlayMode + `snapToStep` + subscribe pattern
- `js/index.js` / `js/viewer.js`: 각 페이지 entry point
- `js/components/{page_view,block,sidebar}.js`: 페이지 배경 + block + 사이드바
- `js/utils/{font_fit,keyboard}.js`: canvas.measureText + 이진 탐색 fitting, 키보드 핸들러

### Key design decisions
- **pixel-space intrinsic stage**: `.stage`의 크기는 `page.render.pixel_w` × `pixel_h` 고정, zoom은 CSS `transform: scale`
- **history.pushState** in-place navigation (full reload 폐기) + popstate
- **navToken**: 빠른 ←/→ 시 stale 응답 무시
- **clearViewerDom** on error: 404/오류 시 sidebar+page+header 모두 클리어
- **overlay.dataset.mode**: translation/original CSS scoping (R1 fix; double-render 해소)
- **canvas.measureText + binary search**: per-language 가중치 없는 robust fitting

### Tests (147 → 197 → 224 → 228)
- `tests/integration/test_static_serving.py` (23 + 4 RE-CODE = 27): 정적 자산 마운트 + 참조 자산 resolvable + JS contract markers + R1 fix 회귀 가드
- `tests/integration/test_font_fit_js.py` (4): node subprocess로 알고리즘 검증 (bounds, monotonicity, mixed CJK fits, degenerate inputs)

### Screenshots (5장, `docs/phases/phase-4/screenshots/`)
1. `01-doc-list.png`: 문서 카드
2. `02-page-translation.png`: 페이지 1 번역 모드 (한국어 overlay + translucent panel)
3. `03-page-original.png`: 페이지 1 원본 모드 (R1 fix — block transparent, PDF 원본 그대로)
4. `04-page3-translation.png`: 페이지 3 이동 (history.pushState + multi-page 흐름)
5. `05-invalid-doc-error.png`: `?doc=999` (clearViewerDom 검증 — sidebar/page 모두 클리어)

### Phase 3 debt 5건 처리 (Stage 0)
- ✅ debt 1: `verify_api.sh` multi-doc loop (`87e7d55`)
- ✅ debt 2: `test_api_live_llm` Hangul assertion in `/messages` (`5e3838d`)
- ✅ debt 3: CI shellcheck step (`6f32b71`)
- ✅ debt 4, 5: Phase 3 verify v3에서 이미 해소

CI run `26197172678` green 확인 후 Phase 4 본 작업 진입.

## Files changed

`git diff --stat 84ce625^..HEAD` 기준: **29 files changed, +2133 insertions** (Phase 3 ↔ Phase 4 차이).

핵심:
- 13 static assets (`src/ht_lens/api/static/{*.html, css/*, js/**}`)
- 2 test files (static_serving + font_fit_js)
- 5 screenshots + README (docs/phases/phase-4)
- 6 phase artifacts (plan, debate, challenge, verify, verify-cross, summary)
- 2 config (`.github/workflows/ci.yml` node step + shellcheck, `.gitignore` 예외)

## Deviations from plan

1. **`font_fit.js`**: plan의 per-language 가중치 알고리즘에서 challenge §1 ACCEPT로 **canvas.measureText + 이진 탐색**으로 전환. Node 환경에서는 estimator fallback.
2. **navigation**: plan의 `window.location.href = ...` full reload에서 challenge §2 ACCEPT로 **`history.pushState`** in-place 전환.
3. **회전 페이지**: plan은 PNG도 표시 안 함 (overlay만 생략)이었으나 challenge ACCEPT로 **PNG 배경은 표시 + banner**로 변경.
4. **Phase 5 hook 예약 제거**: plan의 `state.onBlockClick` 등 미리 만들기에서 challenge §1 PARTIAL ACCEPT로 제거 — Phase 5에서 직접 추가.
5. **빈 block placeholder**: plan의 `[빈 {type} 블록]` 표시에서 challenge §3 ACCEPT로 **transparent + hover outline만**으로 변경.
6. **RE-CODE 추가 변경 (challenge에 없던 R1 fix)**:
   - `navToken` (async race) + `clearViewerDom` (error stale) + `snapToStep` (zoom init)
   - `overlay.dataset.mode` + scoped CSS (double-render 해소)
   - CI에 `actions/setup-node@v4` 추가 (font_fit_js silent skip 방지)
   - `.gitignore`에 phase-4 screenshots 예외 추가

## Both sides — disagreement summary

### Worker (self v2) 입장

- R1 cross-verify의 **4 substantive 결함 모두 fix**: async navigation race, error stale DOM, original-mode double-render, zoom snap-on-init
- 회귀 테스트 4건 추가 + node CI step + 5 screenshots (multi-page + error path 포함)
- R2 자체가 "Round 1's concrete viewer bugs appear fixed"를 명시
- 228 fast tests + 4 node-based algorithm tests 모두 green, `make check` RC=0
- self 93/100은 95 threshold에 못 미치나 모든 substantive 결함 해소된 상태

### Codex (Cross R2) 입장

- R1 substantive 결함 해소 인정. REJECT는 없음.
- 그러나 verify evidence의 강도가 self 93을 정당화하지 못함:
  - **Zoom 키/back-forward 미실 검증**: screenshots에 zoom/popstate 동작 보이지 않음 (코드에는 존재)
  - **Rotated page / partial translation 실 캡처 부재**: challenge §5에서 ACCEPT 했으나 실제 실행 안 됨 (fixture 부재)
  - **Translation-mode panel bleed-through**: 02, 04 screenshot에서 일부 block 가장자리에 영문 텍스트가 비쳐 보임 (panel opacity 0.78이 100% 가리지 않음)
  - **CI remote 미확정**: push 전이라 `actions/setup-node@v4` 효과는 ci.yml만 보고 추론
  - **`doc.status` stale 발견 (신규)**: `index.js`가 표시하는 `doc.status="ready_for_translation"`이 translate 후에도 그대로. ingest 시 설정되고 translate가 업데이트 안 함 (Phase 2/3 cross-phase 이슈를 Phase 4 UI가 새로 노출).
- 제안 81/100.

### Worker 보충 의견

- **Zoom 키/back-forward**: 자동 캡처에 zoom/popstate 액션이 빠진 것은 시간 비용 이슈. 코드 + grep test로 잠금되어 있으나 visual evidence 부재 인정. Phase 5/6에서 자동 UI 회귀 suite 도입 권장.
- **Rotated/partial translation**: fixture 한계가 본질적 원인. Phase 6에서 sample fixture 보강 + 자동 캡처 가능.
- **Panel bleed-through**: opacity 0.78은 의도적 설계 — 완전 불투명(1.0)은 PDF 배경 정보가 완전 가려져 "위치 매핑" 인지가 떨어짐. R2의 비판은 valid (사용자 가독성 관점에서 더 불투명이 나을 수도). Planner 결정 사항.
- **`doc.status` stale (신규 R2 issue)**: 진짜 cross-phase 결함. 그러나 fix 위치는 **Phase 2/3 (translate pipeline)** 이지 Phase 4 viewer가 아님. translate.py가 마지막 commit에서 `Document.status = "translated"`로 update 했어야 함. Phase 4 viewer는 단순히 DB 값 표시. **Phase 5 entry condition으로 흡수 권장** (5분 fix).
- 결론: R2 critique은 valid points이나 R1과 달리 **viewer 본체 결함이 아닌 verify scope + cross-phase 발견**. Round-cap 도달 → Planner 결정.

## Evidence index

- plan: `.claude/phases/phase-4/plan.md`
- debate: `.claude/phases/phase-4/debate.md` (Codex Round 0)
- challenge: `.claude/phases/phase-4/challenge.md` (decision PASS, 10 plan revisions)
- verify (v2 latest): `.claude/phases/phase-4/verify.md`
- verify-cross (R1 + R2): `.claude/phases/phase-4/verify-cross.md` (R2가 최신)

## Known issues / debt (Phase 5+ 또는 Planner directed fix 대상)

### R2 raised — Phase 5 entry로 흡수 권장

1. **`Document.status` stale**: translate pipeline이 `Document.status`를 업데이트 안 함. UI가 `ready_for_translation`을 영구 표시. Fix: `translate/pipeline.py`에서 batch 끝에 `Document.status = "translated"` 업데이트 (5분 작업, Phase 2b 사후 fix).
2. **Translation-mode panel bleed-through**: opacity 0.78에서 일부 텍스트 비침. opacity 0.92로 올리거나 background 색을 더 진하게.
3. **Zoom/back-forward visual evidence 부재**: 자동 캡처에 zoom 단계 + popstate 시연 추가.
4. **Rotated/partial-translation screenshot 부재**: fixture 추가 후 캡처.

### Phase 4 본체 잔여 한계

5. **Playwright UI 회귀 suite 부재**: 현재는 grep + 수동 screenshot. Phase 6에서 dedicated suite 도입.
6. **block hover delay 없음 (즉시 outline)**: UX 노이즈 가능성, Phase 5에서 검토.
7. **사이드바 텍스트만**: 페이지 썸네일은 Phase 5/6에서.
8. **반응형 / 모바일 미지원**: desktop only (의도).

## Push status

**보류 (Planner escalate)**. 사유:
- Workflow Stage 6: "Round 2 disagreement → push 보류, Planner escalate"
- Self 93 < threshold 95, R2 DOWNGRADE (제안 81/100)
- R1 substantive bugs는 모두 해소되었으나 R2 verify scope critique 미해소
- 현재 local main이 `origin/main` 대비 **9 commits ahead** (`84ce625..9c3fd4a`)
- `git push` 전까지 작업 보존

Planner 결정 옵션:
- (a) **R2 zoom/back-forward/bleed-through 미세 fix** (Planner-directed): 자동 캡처 스크립트 보강 + panel opacity 조정 + `Document.status` Phase 2/3 fix (cross-phase) → verify v3 → push
- (b) **그대로 push 승인** (Worker self-score 신뢰 + R1 bugs 모두 해소)
- (c) **추가 RE-CODE** (workflow round-cap 어김 — 비권장)

## Recommended next

- **Planner 결정 후**:
  - 옵션 (a): `Document.status` fix가 Phase 4 외 변경이지만 R2가 새로 발견했으므로 같은 push에 묶기 합리적. 자동 캡처 보강은 새로운 helper 스크립트가 필요할 수도 (Phase 6 자동화 suite와 합치는 게 cleaner).
  - 옵션 (b): summary.md "Known issues" 4건을 Phase 5 entry condition으로 명시 후 진행.
- **Phase 5 (chat panel + pins) 진입 전**:
  - `Document.status` fix (5분)
  - Block 클릭 hook을 `state.onBlockClick`로 추출 (Phase 4 challenge 결정으로 미루었던 것)
  - Sidebar에 페이지 썸네일 추가
  - 자동 UI 회귀 suite (Playwright) 도입 검토
- **Phase 6 (검색/export)에서 다룰 항목**:
  - 회전 페이지 정밀 매핑
  - 모바일 반응형
  - Block hover delay UX tuning
