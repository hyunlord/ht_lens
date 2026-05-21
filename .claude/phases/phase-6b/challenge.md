# Phase 6b — Challenge

## Debate responses

### 1. Over-engineering

**page_view.js 폐기 + 3 신모듈 + viewer bootstrap rewrite — too much surface** — **ACCEPT (major)**
응답: Codex가 정확함. `renderPageView()`는 rotation fallback, overlay `data-mode`, pin 렌더, bbox scaling 모두 owns. 폐기하면 회귀 위험 극대. **Revised approach**: page_view.js를 **유지**하고 가상화 layer만 추가.
- `stage_container.js`: 단일 scroll + IO observer + per-page mount points 관리
- `pane.js`: 작은 wrapper, side(original/translation) 받아 `renderPageView()` 호출
- `page_view.js`: 작은 확장만 — `{side, overlay}` 받아 overlay 모드 명시
- `page_row.js`: stage_container에 inline (별도 모듈 안 만듦, 단순 div wrapper)
**결정**: page_view.js 유지 + 가상화로 wrap. 신 모듈 2개 (stage_container, pane) + page_view 확장.

**PageSummary fields 과다 (block_count, viewMode persist, ?page debounce)** — **PARTIAL ACCEPT**
응답: `block_count`는 placeholder height 계산에 불필요. drop. `rotation`/`render`는 rotation banner + 정확한 placeholder height 위해 유지. viewMode localStorage persist는 사용자 mode 기억 위해 유지 (1줄 변경 + migration guard). `?page` debounce replaceState는 §2의 URL 의미 분리 (debate §2 §4)로 정교화.
**결정**: PageSummary = `{page_num, width, height, rotation, render}` (drop block_count). viewMode persist 유지. URL은 §4 alternative 따름.

### 2. Hidden assumptions

**`currentPage` singleton state가 multi-page에 안 맞음** — **ACCEPT**
응답: 정확한 지적. `findBlockData`, `repaintPage`, `jumpToThread`, `handleRetranslate` 모두 `currentPage.blocks` 의존. Multi-page에서는 `state.pageDataById = {pageNum: pageData}` map으로 교체.
- `findBlockData(blockId)`: 모든 mounted page에서 검색
- `repaintPage(pageNum?)`: 특정 페이지 또는 전체 마운트된 페이지
- `jumpToThread(t)`: pageNum 얻어서 `navigateTo(docId, pageNum, {activateBlockId})`
- `handleRetranslate(blockId)`: pageDataById에서 해당 page entry 찾아 갱신 + 모든 mounted pane 다시 그리기 (양쪽 동일 block_id)
**결정**: state.js에 `pageDataById` 추가, viewer.js의 모든 `currentPage` 참조 제거.

**waitForBlockMounted 폴링 — 2초 timeout assumption** — **ACCEPT (alternative §4 채택)**
응답: 폴링 대신 mountPage가 Promise 반환 + AbortController. 후술.

**URL pushState → replaceState 의미 변경 + popstate 호환 안 됨** — **ACCEPT (alternative §4 채택)**
응답: 명시 navigation은 `pushState` (Phase 4/5 호환), 자유 스크롤은 `replaceState`. 두 의미 분리.
- `navigateTo(docId, page, opts)`: `pushState` 유지 (검색/사이드바 점프 등)
- 자유 스크롤 중 currentPage 변경 → `replaceState` (debounce 500ms)
- popstate: 기존처럼 `navigateTo`로 라우팅

**200 페이지 DoD vs 52 페이지 evidence — pixel dim이 메모리 주범** — **ACCEPT**
응답: sample_ko.pdf 52 페이지 측정 + per-page 메모리 평균 계산 → 200 페이지 extrapolation. PNG size + IO observer ±2 mount budget을 명시. verify.md 5-B에 측정값 + 계산 인용. 200 페이지 합성 가능 여부도 검토 (시간 허락 시).

### 3. Edge cases

**Rotated page의 rotation-banner fallback 보존** — **ACCEPT**
응답: page_view.js를 유지하면 자동 보존. Stress test fixture에 회전 페이지 케이스 추가 — 단순 sample 하나는 회전 없음. sample_ko에 회전 페이지가 있는지 spot check.

**Partial translation의 `data-fallback="original"` 보존** — **ACCEPT**
응답: page_view.js + block.js의 fallback 마커 그대로. both 모드에서도 양쪽 pane 각각 `data-mode` 가지므로 자연스럽게 호환.

**Async race: mountPage 후속 unmount, cycleViewMode 도중 fetch 등** — **ACCEPT**
응답: stage_container에 페이지별 `mountToken` 도입 (Phase 4의 `navToken` 패턴 재사용).
- `mountPage(n)`: token 생성 + AbortController. fetch 응답 시 토큰 검증.
- `unmountPage(n)`: 토큰 invalidate + AbortController.abort
- `cycleViewMode()`: 모든 마운트된 페이지 잠시 unmount → mode 변경 → 재마운트 (token bump)
- `openPanel()` 중 navigation race: 기존 `navToken` + `panelToken` 그대로 사용

### 4. Alternative approaches

**Keep page_view.js, virtualize around it** — **ACCEPT** (§1 통합)

**pushState vs replaceState 분리** — **ACCEPT** (§2 통합)

**Promise + AbortController for mountPage** — **ACCEPT**
응답: `mountPage(n)` returns Promise<void> that resolves when bg + blocks + fontFit done. `navigateTo`는 `await mountPage(target)` 후 `flashBlock`. AbortController는 fetch 취소용.

### 5. Missing tests

모두 **ACCEPT**:
- `test_pages_summary_preserves_rotation_and_render_dims_per_page` ✅
- `test_pages_summary_handles_mixed_page_sizes` ✅
- (jsdom) `test_stage_container_js::test_mount_page_ignores_stale_fetch_after_unmount` — token + AbortController 가드 ✅
- (jsdom) `test_viewer_history_js::test_explicit_navigation_pushes_history_but_scroll_updates_replace_state` — grep + jsdom mock ✅ (full DOM simulation 비용 vs grep으로 잠금, 우선 grep 기반)
- (jsdom) `test_viewer_multpage_js::test_retranslate_updates_target_block_in_all_visible_panes` ✅
- (jsdom) `test_viewer_multpage_js::test_jump_to_thread_waits_for_mount_then_opens_panel_on_target_page` ✅
- (jsdom) `test_viewer_multpage_js::test_translation_pane_marks_original_fallback_when_translation_missing` ✅
- (jsdom) `test_viewer_multpage_js::test_rotated_page_row_shows_rotation_banner` ✅

전부 jsdom으로 풀 시뮬은 비용 큼. 실용적 접근:
- pure helper 함수 (예: `computeFarPagesToUnmount`, `extractPageDataForBlock`)는 jsdom 없이 node에서 import 단위 테스트
- DOM 의존 (stage_container, viewer) 핵심 분기는 grep 마커로 잠금 + 수동 verify 5-B 시나리오 자세히
- 가장 위험한 1-2건만 full jsdom: `mountPage stale fetch` + `retranslate multi-pane sync`

---

## Plan revisions (after debate)

1. **page_view.js 유지** + `stage_container.js`로 가상화 layer 추가 (drop page_view 폐기)
2. **신 모듈 축소**: stage_container.js + pane.js 두 개만 신규 (page_row.js drop, page_view.js 확장)
3. **state.pageDataById map** 도입 — `currentPage` singleton 제거. handleRetranslate / findBlockData / jumpToThread 모두 map 기반 재작성
4. **PageSummary 슬림화**: drop `block_count`
5. **URL 의미 분리**: navigateTo는 pushState (Phase 4/5 호환), 자유 스크롤 currentPage 변경은 replaceState debounce 500ms
6. **mountPage Promise + AbortController + mountToken**: 폴링 제거, token-based race guard (Phase 4 navToken 패턴 재사용)
7. **회귀 가드 강화**: rotation banner + data-fallback="original" 보존 명시
8. **테스트 강화**:
   - backend: `test_api_pages_summary.py`에 rotation + mixed sizes
   - jsdom: 신규 2 케이스 (stale fetch + retranslate multi-pane)
   - grep: viewer.js, state.js, keyboard.js, viewer.css의 핵심 마커
9. **200 페이지 DoD evidence**: 52 페이지 측정 + per-page memory extrapolation
10. **block hover 동기화**: JS event 방식 그대로 (plan §10)

---

## File-level changes (revised)

| Path | Action | Note |
| ---- | ------ | ---- |
| `src/ht_lens/api/routers/pages.py` | MODIFY | + pages-summary |
| `src/ht_lens/api/schemas.py` | MODIFY | + PageSummary (no block_count) |
| `src/ht_lens/api/static/js/components/stage_container.js` | NEW | scroll + IO + per-page mount/unmount + token race guard |
| `src/ht_lens/api/static/js/components/pane.js` | NEW | side-aware renderPageView wrapper |
| `src/ht_lens/api/static/js/components/page_view.js` | **MODIFY (keep)** | + `{side, overlay}` 인자, 기존 동작 유지 |
| `src/ht_lens/api/static/js/components/block.js` | MODIFY | hover sync (data-block-id 셀렉터 양쪽 토글) |
| `src/ht_lens/api/static/js/components/sidebar.js` | MODIFY | active page 추적 (current logic 유지) |
| `src/ht_lens/api/static/js/state.js` | MODIFY | viewMode + viewModeActual + pageDataById + helpers |
| `src/ht_lens/api/static/js/viewer.js` | MODIFY (큰) | currentPage singleton 제거 + stage_container 통합 + navigateTo 재작성 (pushState + waitForMount Promise) + handleRetranslate multi-page |
| `src/ht_lens/api/static/js/api.js` | MODIFY | + getPagesSummary |
| `src/ht_lens/api/static/js/utils/keyboard.js` | MODIFY | T cycle + ←→ scrollPageBy |
| `src/ht_lens/api/static/css/viewer.css` | MODIFY | stage-container + page-mount + pane layout |
| `src/ht_lens/api/static/viewer.html` | MODIFY | div#stage |
| `tests/integration/test_api_pages_summary.py` | NEW | basic + rotation + mixed sizes |
| `tests/integration/test_static_serving.py` | MODIFY | new modules + grep markers (viewMode, pageDataById, mountPage, AbortController, pushState/replaceState, rotation-banner, data-fallback) |
| `tests/integration/test_stage_container_js.py` | NEW | jsdom: mountPage stale-fetch token guard |
| `tests/integration/test_viewer_retranslate_multipage_js.py` | NEW | jsdom: retranslate updates all mounted panes |
| `docs/phases/phase-6b/{README.md, screenshots/*}` | NEW | 8 screenshots |

---

## DoD checklist

| DoD item | Status | Evidence |
| -------- | ------ | -------- |
| 200 페이지 스크롤 부드러움 + 메모리 < 500MB | planned | 52 페이지 sample_ko 측정 + per-page extrapolation + DevTools 스크린샷 |
| 좌우 비교 페이지/zoom/scroll 동기화 | planned | single scroll container 자동 동기, page mount per page row, screenshots 01/05 |
| block hover/click 양쪽 동기 반영 | planned | JS event 양쪽 토글 (data-block-id), screenshot 01 hover state |
| 검색/사이드바 점프 정확 | planned | navigateTo + mountPage Promise + flashBlock, screenshots 07/08 |

---

## Risk register

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Multi-page state 누락 (currentPage 잔존) | High | Phase 4/5/6a 회귀 | pageDataById 도입 + grep + jsdom tests |
| mountPage race (stale fetch) | Medium | UI 불일치 | mountToken + AbortController + jsdom test |
| Rotation banner 회귀 | Medium | 회전 page 깨짐 | page_view.js 유지 + rotation banner grep 테스트 |
| Partial translation 회귀 (data-fallback) | Medium | both 모드 오해 | page_view.js 유지 + 마커 그대로 + screenshot 검증 |
| Memory > 500MB | Low | DoD 미달 | ±2 mount + 5+ unmount, 52 페이지 측정으로 정량 |
| URL pushState/replaceState 혼동 | Low | back 버튼 깨짐 | 분리 + popstate 가드 + grep test |
| 폰트 fitting 양쪽 비용 | Low | zoom 디바운스 부족 | 200ms debounce + RAF + 마운트된 페이지에만 |
| 사이드바 active page 부정확 | Low | 작은 UX | IO 가시성 최대 페이지 추적 + replaceState |

---

## Decision

- [x] PASS → proceed to code (plan revisions 10건 적용)
- [ ] RE-PLAN

Codex 비판 18건 중 16 ACCEPT + 2 PARTIAL ACCEPT. Plan revision의 핵심은 **page_view.js 유지하면서 가상화 layer만 추가** + **pageDataById map** + **mountToken/AbortController**. 신 모듈 surface가 plan의 3개 → 2개로 감소. 회귀 위험 대폭 감소.
