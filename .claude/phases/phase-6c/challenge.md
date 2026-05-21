# Phase 6c — Challenge

## Debate responses

### 1. Over-engineering

**`.env` 로드 cli + dev_serve + python-dotenv 직접 dep + /proc 검증 — drift 위험** — **PARTIAL ACCEPT**
응답: 로드 지점은 **`create_app()` 직전 단일 위치**로 일원화 (debate §4 ACCEPT). `cli.py`에는 두지 않고 `api/app.py::create_app` 진입부에서 `load_dotenv` 호출. 또는 `llm/factory.py::make_llm_client` 진입부. dev_serve.sh의 `set -a; source .env` 보조는 유지 (Python 진입 전 셸 환경에서 보이게 — debugging 친화). `/proc/PID/environ` 검증은 verify 시점의 manual spot-check로만 사용, 자동 테스트는 `os.environ` 직접 assertion.
**결정**: load_dotenv을 `create_app()` 진입부에 위치. CLI는 wrapper만 (load_dotenv 안 함). dev_serve.sh는 dev convenience로 유지 (모순 없음 — load_dotenv가 idempotent).

**fit-to-width hook 다수 (load+resize+sidebar+viewMode) — DoD 초과** — **PARTIAL ACCEPT**
응답: DoD는 "새 페이지 진입 시" 명시 → loadDocument 종료 시점 1곳만 의무. 그 외 (resize/sidebar/viewMode)는 ResizeObserver 1개로 통합 (debate §4 ACCEPT). 사용자 명시 zoom(Ctrl+↑↓)은 자동 fit을 비활성. 별도 hooks 안 만듦.
**결정**: ResizeObserver on `#stage` 단일 + `loadDocument` 진입 1회 강제. 사용자 zoom 후 ResizeObserver 자동 fit 비활성 플래그.

**자연 스크롤 fix가 변수 너무 많이 바꿈** — **PARTIAL ACCEPT**
응답: 가설은 (1) rootMargin 부족 + (2) currentPage 결정 — **둘 다 합리적**. 그러나 plan author가 **재현 먼저 시도**. 재현 가능하면 정확한 원인 1개만 잡고 fix. scroll listener (3)는 일단 안 함. 코드를 최소화하되 어떤 fix가 됐는지는 verify에 명시.
**결정**: 진단 우선. fix는 작게 (rootMargin 200% 또는 active-page 중심점 결정 중 1개 우선).

### 2. Hidden assumptions

**`cli.py`는 유일 진입점 아님 — `create_app()` 직접 사용 가능** — **ACCEPT (§1 통합)**
응답: load_dotenv를 `create_app` 안으로 이동.

**ZOOM_STEPS와 임의 fit 값 충돌** — **ACCEPT**
응답: fit-to-width는 ZOOM_STEPS에 snap. 단, max는 1.0 (over-zoom 방지). 작은 viewport는 0.5까지 (ZOOM_STEPS 첫 값). 정확한 fit은 못해도 가까운 step → overflow 없음.
**결정**: `computeFitZoom` 결과를 `ZOOM_STEPS` 중 가장 큰 ≤ target 선택. 즉 underflow하되 overflow 안 함.

**/proc/PID/environ Linux-only** — **ACCEPT**
응답: 자동 테스트는 `os.environ` 직접 검증. /proc은 manual verify spot-check만.

**bash `source` vs python-dotenv parsing 차이** — **PARTIAL ACCEPT**
응답: `.env` 형식이 단순한 `KEY=value` 라인만 (현재 .env 검사 완료, 셸 syntax 없음). dev_serve.sh의 source는 OK. 그러나 미래 .env에 quotes/multiline 들어가면 깨질 수 있음 → **load_dotenv가 권위, dev_serve.sh는 debugging 보조**라고 문서화.

### 3. Edge cases

**Deep link `?page=N&block=B` + auto-fit으로 placeholder height 변화 → scroll 위치 빗나감** — **ACCEPT**
응답: `loadDocument` 안에서 순서를 **(a) summary fetch → (b) placeholder rows → (c) auto-fit → (d) scrollToPage → (e) mountPage(targetPage) → (f) flashBlock** 로 고정. auto-fit이 scrollToPage 전에 호출되도록.

**`both` + 채팅 패널 open → viewModeActual='translation', plan은 viewMode 사용** — **ACCEPT**
응답: `computeFitZoom`은 **`viewModeActual`** 사용. paneCount = `viewModeActual === 'both' ? 2 : 1`.

**사이드바 토글 버튼 renderSidebar 안에 두면 setCurrentPage 시 unmount/remount** — **ACCEPT (§4 alternative)**
응답: 토글 버튼을 **`viewer.html`의 `app-header` 안에 정적 마운트**. `renderSidebar`는 사이드바 *내부 콘텐츠*만 그림. 토글 버튼은 안정적 stays.
**결정**: viewer.html에 `<button class="sidebar-toggle">` static. viewer.js에서 wiring.

**CWD vs repo root .env 충돌** — **ACCEPT**
응답: CWD 우선 정책 제거. **repo root `.env`만** load. CWD에 다른 .env가 있어도 무시. 또는 `HT_LENS_ENV_FILE` 환경변수로 명시 override.
**결정**: `create_app()` 안에서 repo root `.env`만. `Path(__file__).resolve().parents[2] / ".env"` 한 곳.

### 4. Alternative approaches

**Load .env in api/app.py / llm/factory.py** — **ACCEPT** (§1 통합)
응답: `create_app()` 진입부.

**ResizeObserver vs manual hooks** — **ACCEPT** (§1 통합)
응답: ResizeObserver(#stage).

**사이드바 토글은 viewer.html static** — **ACCEPT** (§3 통합)

### 5. Missing tests

모두 **ACCEPT**:
- `test_create_app_reads_dotenv_without_cli_import`: TestClient 호출만으로 LLM_PROVIDER가 환경에 들어가는지
- `test_auto_fit_preserves_deep_link_target_page`: jsdom-light로 loadDocument 순서 검증
- `test_auto_fit_uses_view_mode_actual_when_panel_open`: jsdom-light computeFitZoom(viewMode='both', panelOpen=true) → translation 단일 폭 사용
- `test_sidebar_toggle_survives_sidebar_rerender_on_current_page_change`: viewer.html static 마운트 + setCurrentPage 발화 후 토글 버튼 여전히 동작
- `test_attach_intersection_observer_mounts_last_page_on_fast_scroll`: jsdom 가짜 IO entries로 마지막 페이지 mount 확인

실용적 접근:
- pure helper (`computeFitZoom`) → jsdom 없이 node import unit test
- DOM 의존 (사이드바 토글 위치, IO entries 흐름) → jsdom 활용
- TestClient + LLM_PROVIDER 환경 검증 → backend 통합 테스트

---

## Plan revisions (after debate)

1. **`.env` 로드 위치**: cli.py 제거 → `api/app.py::create_app` 진입부 단일. CWD 무시, repo root 1곳만.
2. **`python-dotenv`는 transitive 의존**이라 pyproject 명시 추가 권장 — 그대로 유지.
3. **dev_serve.sh source는 dev convenience**로 유지 (Python 진입 전 셸 변수 노출). load_dotenv는 idempotent.
4. **fit-to-width**: ResizeObserver(`#stage`) 1개로 모든 layout 변경 흡수. loadDocument 종료 시점은 명시 호출. `viewModeActual` 사용. `ZOOM_STEPS`에 underflow snap.
5. **사이드바 토글 버튼**: `viewer.html`에 static 마운트 (renderSidebar 밖). 키보드 단축키 없음.
6. **자연 스크롤 fix**: 진단 후 가장 가능성 큰 가설 (rootMargin 200% + active-page 중심점) 둘 다 작은 변경으로. scroll listener (3)는 안 함.
7. **loadDocument 순서 고정**: summary → placeholder → auto-fit → scrollToPage → mountPage → flashBlock.
8. **로고 → index.html**: `<a href>` static, SPA 안 함.
9. **mock → real 검증**: backend integration test로 `LLM_PROVIDER` 환경 노출 검증 + manual DB SELECT.

---

## File-level changes (revised)

| Path | Action | Note |
| ---- | ------ | ---- |
| `pyproject.toml` | MODIFY | + `python-dotenv >= 1.0` (transitive → explicit) |
| `src/ht_lens/api/app.py` | MODIFY | + `load_dotenv(repo_root / ".env", override=False)` 진입부 |
| `scripts/dev_serve.sh` | MODIFY | + `.env` source 안전망 (Python 진입 전 셸 환경 노출) |
| `src/ht_lens/api/static/viewer.html` | MODIFY | `<a class="app-logo">` 링크 + `<button class="sidebar-toggle">` static |
| `src/ht_lens/api/static/js/state.js` | MODIFY | + `sidebarOpen` + `setSidebarOpen` + `toggleSidebar` + `setZoomAutoFit` (persist=false) + `STORAGE_SIDEBAR_OPEN` |
| `src/ht_lens/api/static/js/components/sidebar.js` | MODIFY | 내부 콘텐츠만 (토글 버튼 빠짐) |
| `src/ht_lens/api/static/js/components/stage_container.js` | MODIFY | rootMargin 200% + active-page 중심점 보강 + ResizeObserver wire-up helper |
| `src/ht_lens/api/static/js/utils/viewport.js` | NEW | `computeFitZoom({pageWidthPt, stageWidthPx, scale, viewMode})` |
| `src/ht_lens/api/static/js/viewer.js` | MODIFY | + ResizeObserver(#stage) + fit 호출 + 사이드바 토글 wire-up + loadDocument 순서 fixed |
| `src/ht_lens/api/static/css/viewer.css` | MODIFY | sidebar transition + `.sidebar--collapsed` + `.app-logo` + `.sidebar-toggle` |
| `tests/integration/test_dotenv_load.py` | NEW | create_app + os.environ 검증 + override=False |
| `tests/integration/test_static_serving.py` | MODIFY | 6c grep markers |
| `tests/integration/test_stage_container_js.py` | MODIFY | + active-page 중심점 결정 + 가짜 IO entries 마지막 페이지 mount |
| `tests/integration/test_viewport_js.py` | NEW (jsdom-light) | computeFitZoom unit test (viewMode='both' / 'translation', viewModeActual, ZOOM_STEPS snap) |
| `tests/integration/test_api_live_llm.py` | MODIFY | + LLM_PROVIDER env로 model 검증 (mock 아닌지) |
| `docs/phases/phase-6c/{README.md, screenshots/*}` | NEW | 6 screenshots |

---

## DoD checklist

| DoD item | Status | Evidence |
| -------- | ------ | -------- |
| viewer AI 응답이 진짜 sglang (mock 아님) | planned | load_dotenv in create_app + DB model column 'qwen3.6-27b' + @pytest.mark.llm |
| 새 페이지 진입 시 viewport 폭 자동 fit | planned | loadDocument 순서 고정 + ResizeObserver + ZOOM_STEPS snap + screenshot 01 |
| 사이드바 토글 (200px ↔ 0) | planned | static 버튼 + sidebarOpen + transition + screenshot 02/03 |
| 자연 스크롤 6페이지 끝까지 | planned | rootMargin 200% + active-page 중심점 + jsdom test + screenshot 04 |
| 로고 클릭 → index.html | planned | `<a href>` static + screenshot 05 |
| 사이드바 상태 localStorage 저장 | planned | STORAGE_SIDEBAR_OPEN + safeWrite + reload 시나리오 |

---

## Risk register

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| load_dotenv가 create_app 진입 후라 factory 호출 시점에 늦음 | Medium | mock fallback | create_app 최상단에 load_dotenv (factory 호출 전), backend test로 검증 |
| ZOOM_STEPS snap이 overflow → 가로 scroll | Low | UX | underflow only (≤ target 중 최대값) |
| ResizeObserver가 모든 width 변경에 발화 → 무한 재계산 | Medium | 성능 | 디바운스 200ms + 사용자 zoom 후 비활성 플래그 |
| 사이드바 토글 시 stage width 변화 + auto-fit 충돌 | Low | UX | ResizeObserver가 단일 흐름으로 처리 |
| 자연 스크롤 rootMargin 200% → 메모리 ↑ | Low | DoD 미달 | scheduleFarPageUnmount 그대로 (radius 5) — 메모리 cap 유지 |
| dev_serve.sh source가 .env multiline 깨뜨림 | Low | startup fail | 현재 .env는 단순 형식. load_dotenv 권위. dev_serve는 debugging 보조라고 주석 |
| 로고 클릭 후 다른 doc 진입 시 chat panel state 잘못 복원 | Low | UX | Phase 5 readPanelSnapshot 마이그레이션 가드 그대로 |

---

## Decision

- [x] PASS → proceed to code (plan revisions 9건 적용)
- [ ] RE-PLAN

Codex 비판 17건 중 13 ACCEPT + 4 PARTIAL ACCEPT. Plan revision의 핵심: **(a) load_dotenv를 `create_app`으로 통합**, **(b) ResizeObserver(#stage) 단일**, **(c) 사이드바 토글 버튼 static 마운트**, **(d) loadDocument 순서 고정**.
