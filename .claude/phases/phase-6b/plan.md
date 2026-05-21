# Phase 6b — Plan

## Goal

Viewer 아키텍처를 단일 페이지 클릭 네비에서 **자연 스크롤 + 좌우 분할 비교 뷰**로 rework. v0.5 마일스톤 (읽기 흐름 자연스러움).

## Scope

**In**
- Backend: `GET /documents/{id}/pages-summary` endpoint + `PageSummary` schema
- Frontend (큰 rework):
  - 단일 scroll container (`stage_container.js`) + intersection observer
  - 페이지 row (`page_row.js`) + dual pane (`pane.js`)
  - View mode 토글: translation / original / both (T 키 순환)
  - 자연 스크롤 + ←→ scrollIntoView 페이지 점프
  - `navigateTo()` 재작성 (검색/사이드바 점프가 lazy mount + scroll)
  - 채팅 패널 열림 → both 모드 강제 single-pane
  - URL `?page=N` debounce 500ms replaceState
  - 폰트 fitting 양쪽 재계산 (zoom 변경 시 200ms debounce)
  - block hover/click 양쪽 pane 동기화 (data-block-id 셀렉터)
  - localStorage migration guard (viewMode 신규 키)
- Tests:
  - `test_api_pages_summary.py`
  - `test_static_serving.py` 확장 (새 JS 모듈 + grep markers)
- Screenshots: 8장
- Memory stress: 52 페이지 sample_ko.pdf peak memory 측정

**Out**
- 새 dep
- Phase 6c (header heuristic, 멀티컬럼, samples.md, 회전 페이지)
- Phase 6d (streaming, 모델 토글, 백그라운드 패널, Playwright suite, jsdom CI, LLM-driven title)
- side-by-side에서 양쪽 다른 페이지 표시 (split view 비전형)
- minimap / scroll indicator

## Approach

### 1) Backend pages-summary endpoint

`src/ht_lens/api/routers/pages.py`에 추가. `PageSummary = {page_num, width, height, rotation, render, block_count}`. 200 페이지 → ~20KB JSON. 용도: 진입 시 placeholder row 만들 때 metadata 일괄 fetch.

### 2) Frontend stage_container

```html
<div class="stage-container" id="stage">
  <div class="page-row" data-page="1" style="min-height: 1144px;">
    <!-- 미마운트 placeholder -->
  </div>
  <div class="page-row" data-page="2" style="min-height: 1144px;">...</div>
  ...
</div>
```

진입 시:
1. `getPagesSummary(docId)` → 전 페이지 metadata
2. row placeholder N개 생성 (height = `render.pixel_h * zoom`)
3. intersection observer로 ±1 화면 가시 페이지 추적
4. 진입 → `mountPage(n)`: 페이지 fetch + pane 렌더 + 폰트 fitting
5. 5+ 거리 → `unmountPage(n)`: pane.overlay innerHTML = ''

### 3) page_row + pane

`page_row.js`: row 생성, viewMode에 따라 pane 1 or 2개 추가
`pane.js`: bg image + overlay (block 마운트 자리)

### 4) intersection observer

- root: stageEl
- rootMargin: `100% 0px 100% 0px`
- threshold: 0
- mount 정책: 가시 또는 ±1 화면 → mount
- unmount 정책: 마운트된 페이지 중 현재 가시 페이지에서 5+ 거리 → unmount (동시 마운트 ≤ 5)

### 5) View mode (translation/original/both)

```js
state.viewMode = "translation";        // localStorage persist
state.viewModeActual = "translation";  // computed
```

T 키 순환: translation → original → both → translation. 채팅 패널 열림 + viewMode=="both" → `viewModeActual="translation"` 강제. 패널 닫힘 → `viewModeActual = viewMode` 복원.

mode 변경 시: 마운트된 모든 row 재구성 + 폰트 fitting 재계산.

### 6) 폰트 fitting 재계산

zoom 변경 또는 viewport resize → requestAnimationFrame 안에서 일괄, debounce 200ms. 마운트된 페이지의 모든 pane에 fitTextToBlock 호출. both이면 비용 2배.

### 7) Page navigation

키보드:
- ←/→: 현재 페이지 ±1, `scrollIntoView({behavior: "smooth", block: "start"})`
- Home/End: 첫/마지막

intersection observer가 active page 추적 → `state.currentPage` 갱신 → 사이드바 active + URL `?page=N` debounce 500ms replaceState.

### 8) navigateTo 재작성

```js
async function navigateTo(docId, pageNum, opts = {}) {
  const { activateBlockId = null } = opts;
  if (state.activeDocId !== docId) {
    window.location.href = `viewer.html?doc=${docId}&page=${pageNum}` +
      (activateBlockId ? `&block=${activateBlockId}` : "");
    return;
  }
  if (activateBlockId) state.activeBlockId = activateBlockId;
  const row = stageEl.querySelector(`.page-row[data-page="${pageNum}"]`);
  row?.scrollIntoView({ behavior: "smooth", block: "start" });
  if (activateBlockId) {
    await waitForBlockMounted(activateBlockId, 2000);
    flashBlock(activateBlockId);
  }
}
```

`waitForBlockMounted`: 폴링 50ms × 40 (2초 cap). IO signal 정교화는 debate에서.

### 9) Chat panel 충돌

`openPanel()`: `state.viewMode === "both"`이면 viewModeActual="translation" 강제 + 모든 마운트된 row 재구성.
`closePanel()`: viewModeActual = viewMode 복원.

### 10) Block hover/click 양쪽 동기화

`block.js` mouseenter/mouseleave에서 같은 `data-block-id` 양쪽 pane 모두 toggle. plan 결정: JS event (CSS `:has()`는 디버깅 어려움).

block click → 기존 `ht-lens:block-click` CustomEvent (Phase 5 호환).

### 11) URL persistence

localStorage `viewMode` 키 추가 (translation/original/both). migration guard (Phase 5 `readPanelSnapshot` 패턴): 키 없으면 기본 "translation".

### 12) 메모리 가드

stress test: 52 페이지 sample_ko.pdf 끝까지 스크롤 → Chrome DevTools Performance peak < 500MB. 동시 마운트 ≤ 5.

### 13) 회귀 가드

- `page_view.js` 폐기 (stage_container로 흡수)
- block.js의 hover/click handler 확장 (Phase 5 CustomEvent 유지)
- viewer.js bootstrap 재작성 (`navToken`/`panelToken`/`discardPanel/closePanel/togglePanel` 패턴 유지)
- Phase 5 chat panel 시나리오 그대로 작동
- Phase 6a 검색/export/재번역 그대로 작동 (검색 결과 클릭은 새 `navigateTo`에 맞춤)
- LLM client 영역 변경 0 (enable_thinking=false 그대로)

### 14) 신 식별자 (워크플로우 0-3-A 의무 — R0부터 lock 표 포함 예정)

| 영역 | 새 함수/state |
| ---- | -------------- |
| state.js | `viewMode`, `viewModeActual`, `setViewMode`, `cycleViewMode`, `pageMetaById` |
| api.js | `getPagesSummary` |
| stage_container.js | `mountPage`, `unmountPage`, `mountPageIfNeeded`, `scheduleFarPageUnmount` |
| page_row.js | `createPageRow`, `updatePageRowForMode` |
| pane.js | `createPane`, `renderPaneContent`, `clearPaneContent` |
| viewer.js | `navigateTo` 재작성, `waitForBlockMounted`, `flashBlock` |
| keyboard.js | T → `cycleViewMode`, ←/→ → `scrollPageBy` |
| Backend | `GET /documents/{id}/pages-summary`, `PageSummary` |

## File-level changes

| Path | Action | Note |
| ---- | ------ | ---- |
| `src/ht_lens/api/routers/pages.py` | MODIFY | + pages-summary |
| `src/ht_lens/api/schemas.py` | MODIFY | + PageSummary |
| `src/ht_lens/api/static/js/components/stage_container.js` | NEW | scroll + IO |
| `src/ht_lens/api/static/js/components/page_row.js` | NEW | row 1 or 2 panes |
| `src/ht_lens/api/static/js/components/pane.js` | NEW | single pane |
| `src/ht_lens/api/static/js/components/block.js` | MODIFY | hover sync |
| `src/ht_lens/api/static/js/components/page_view.js` | DELETE | 흡수됨 |
| `src/ht_lens/api/static/js/components/sidebar.js` | MODIFY | active page 추적 (no breaking) |
| `src/ht_lens/api/static/js/state.js` | MODIFY | viewMode + helpers |
| `src/ht_lens/api/static/js/viewer.js` | MODIFY | rework |
| `src/ht_lens/api/static/js/api.js` | MODIFY | + getPagesSummary |
| `src/ht_lens/api/static/js/utils/keyboard.js` | MODIFY | T cycle + ←→ scroll |
| `src/ht_lens/api/static/css/viewer.css` | MODIFY | dual-pane layout |
| `src/ht_lens/api/static/viewer.html` | MODIFY | div#stage |
| `tests/integration/test_api_pages_summary.py` | NEW | endpoint tests |
| `tests/integration/test_static_serving.py` | MODIFY | new modules + markers |
| `docs/phases/phase-6b/{README.md,screenshots/*}` | NEW | 8 screenshots |

## Dependencies (new)

| Package | Why |
| ------- | --- |
| (none) | Phase 5 vendor 그대로 |

## Test strategy

### Backend (fast)
- `test_api_pages_summary.py`:
  - 6 페이지 doc → 6 entries
  - 페이지 순서 정렬
  - block_count 정확
  - 404 unknown doc
  - render metadata 정합성 (dpi/pixel/scale)

### Static (grep markers)
- `test_static_serving.py` 확장:
  - 새 JS 모듈 (stage_container, page_row, pane) 200
  - viewer.js의 `navigateTo` 재작성 + `waitForBlockMounted` 마커
  - state.js의 `viewMode`/`viewModeActual`/`cycleViewMode` 마커
  - keyboard.js의 `cycleViewMode` 호출 마커
  - viewer.css의 `.stage-container`/`.page-row`/`.pane` 마커
  - block.js hover sync 마커

### Manual (verify 5-B)
- 6 페이지 sample_mixed.pdf: 모든 mode + 스크롤 + zoom + 검색 + 사이드바 점프
- 52 페이지 sample_ko.pdf: 자연 스크롤 부드러움 + 메모리 측정
- 8 screenshots
- 회귀 체크: Phase 5 채팅 + Phase 6a 검색/export/재번역

## DoD mapping

| DoD item | How to satisfy | Evidence plan |
| -------- | -------------- | ------------- |
| 200 페이지 스크롤 부드러움 + 메모리 < 500MB | IO + ±2 마운트 + 5+ unmount | 52 페이지 측정 + DevTools 스크린샷 |
| 좌우 비교 페이지/zoom/scroll 동기화 | 단일 scroll container + same row | screenshot 01/05 |
| block hover/click 양쪽 동기 반영 | JS event 양쪽 토글 | screenshot 01 hover + click 후 chat panel |
| 검색/사이드바 점프 정확 | navigateTo 재작성 | screenshot 07/08 |

## 미결정 사항 (debate 검토 대상)

1. rootMargin 100% — 미마운트 갑작 등장 방지 vs 메모리. 후보: 50%/200%
2. unmount 거리 5 — 너무 가까우면 깜빡임. 너무 멀면 메모리
3. mode 순환 순서 translation → original → both
4. zoom 디바운스 200ms — both 모드 2배 비용 대응
5. block hover JS event vs CSS `:has()` — plan: JS event
6. page-row placeholder 높이 진입 시 일괄 vs lazy — plan: 일괄
7. scrollIntoView smooth vs instant — plan: smooth
8. navigateTo lazy mount 대기 — plan: polling 50ms × 40
9. chat panel viewMode 자동 복귀 — plan: yes
10. stage_container vs page_view 관계 — plan: page_view 폐기
11. dual-pane 50/50 vs aspect ratio — plan: 50/50

debate에서 Codex가 IO race / scroll sync 끊김 / 폰트 fitting 비용 / page row placeholder 정확도 / chat panel 강제 UX 등 찌를 가능성.
