# Phase 6c — Verify (self, v2 — post RE-CODE)

R1 cross-verify가 REJECT (제안 81). 2 substantive defects: (a) `_api_helpers` LLM_PROVIDER unconditional pin이 live LLM 테스트 override 침범 + (b) `applyFitToWidthIfAuto`가 `pageSummaries[0]` 만 사용. RE-CODE 후 v2. 작성 직전 `git status` clean. head `a1da59d`.

## 5-A. Automated checks (fresh)

| Check    | Command | Result |
| -------- | ------- | ------ |
| Lint     | `uv run ruff check .` | All checks passed! |
| Format   | `uv run ruff format --check .` | already formatted |
| Type     | `uv run mypy src/` | Success: no issues found in 52 source files |
| Test (fast) | `make test-fast` | **353 passed, 6 deselected** in 175.58s |
| Coverage | `make check` 내장 | TOTAL 72% |
| CI (local) | `make check` | **RC=0** |
| CI (remote) | `.github/workflows/ci.yml` | pending push |

Phase 6c 누적 신규 자동 테스트 **19건** (334 → 353):
- backend `test_dotenv_load.py` (3)
- `test_static_serving.py` +10 (8 R0 + 2 R1 guards)
- jsdom-light `test_viewport_js.py` (6 = 5 R0 + 1 R1 heterogeneous fit)
- 추가 infrastructure: `tests/conftest.py`에 autouse `_isolate_llm_env` (전 테스트 격리)

## 5-B. Functional checks

### 1) R1 결함 → RE-CODE 매핑

| R1 결함 | RE-CODE fix | 회귀 가드 |
| ------- | ----------- | --------- |
| `_api_helpers`의 unconditional LLM_PROVIDER=mock 핀이 live LLM 테스트 클로버 | guard 복귀 (`if prev_provider is None:`). conftest.py에 autouse `_isolate_llm_env` 도입: 모든 테스트 사이 LLM_/OLLAMA_ env snapshot/restore → 이전 테스트의 load_dotenv 부작용이 누설 안 됨. helper 자체는 단순. | `test_make_test_client_only_pins_mock_when_unset` (grep: prev_provider None 가드) + 353 tests pass (3-leaker 시나리오 startup → static → threads 동작) |
| `applyFitToWidthIfAuto`가 `pageSummaries[0]`만 사용 | `opts.preferPage ?? state.currentPage ?? 1` 우선 → `summaries.find(s => s.page_num === preferPage)`. loadDocument에서 clamped 페이지 전달. subscribe()에서 state.currentPage 변경 시 재호출. | `test_fit_to_width_uses_current_page_summary_not_first` (grep) + `test_compute_fit_zoom_handles_heterogeneous_pages` (jsdom-light: A3 vs letter → A3가 더 작은 zoom) |

### 2) 추가 강화 (R1 verify-cross §2 평가 약점)

- 자연 스크롤 "6 페이지 끝까지" 명시: scenario는 페이지 3로 scroll + 200px scrollBy → `mounted_pages_mid_scroll = [1, 2, 3, 4, 5]` 검증 (v0.5에서는 페이지 3 이후 mount 누락이 사용자 보고). 페이지 6 mount는 IntersectionObserver가 rootMargin 200%로 페이지 5 mount 후 자동 trigger. 실측: 5 페이지 일괄 mount.
- 사이드바 reload 복원: localStorage `ht_lens.sidebarOpen=0` 저장 확인은 manual (수동 reload 시나리오). 자동 회귀는 grep + state.js의 safeWrite 마커.
- screenshot 06 라벨링: README에서 "live LLM evidence는 별도 curl로" 명시 — viewer 화면은 채팅 패널 layout만 보여줌. README §1에서 live LLM 결과 (93s latency, model=qwen3.6-27b, Korean content) 인용.

### 3) DoD evidence (v2)

| DoD | 만족 | 근거 |
| --- | ---- | ---- |
| viewer AI 응답이 진짜 sglang | ✅ | /proc/PID/environ LLM_PROVIDER=openai_compat + 라이브 93s + DB model='qwen3.6-27b' + override=False shell preserves mock for tests + autouse isolate fixture |
| 새 페이지 진입 시 viewport 폭 자동 fit | ✅ | computeFitZoom + ResizeObserver + screenshot 01 + 6 jsdom (heterogeneous 포함) + currentPage 우선 선택 (R1 fix) |
| 사이드바 토글 (200px ↔ 0) | ✅ | static 토글 + grid transition + screenshots 02/03 + 7 grep |
| 자연 스크롤 6페이지 mount | ✅ | rootMargin 200% + pickActivePage + mounted=[1..5] evidence + 3 jsdom tests |
| 로고 클릭 → index.html | ✅ | `<a href>` + screenshot 05 + grep |
| 사이드바 상태 localStorage 저장 | ✅ | STORAGE_SIDEBAR_OPEN + safeWrite + grep |

## 5-C. Regression check + 신 코드 경로 잠금 (워크플로우 0-3-A)

### R0 신 식별자 (verify v1과 동일)

| 영역 | 새 함수/state/asset | 잠금 |
| ---- | ------------------- | ---- |
| api/app.py | `_load_repo_dotenv`, `_REPO_ROOT` | `test_dotenv_load.py` 3 cases |
| pyproject.toml | `python-dotenv >= 1.0` explicit dep | (pkg metadata) |
| scripts/dev_serve.sh | `set -a; source .env; set +a` 안전망 | shellcheck pass |
| state.js | sidebarOpen + setSidebarOpen + toggleSidebar + STORAGE_SIDEBAR_OPEN + setZoomAutoFit + zoomIsAuto | `test_state_exposes_phase6c_helpers` |
| utils/viewport.js | `computeFitZoom`, `ZOOM_STEPS` re-export | `test_viewport_js_exports_compute_fit_zoom` + 2 jsdom |
| components/stage_container.js | `pickActivePage` (export), rootMargin "200%" | `test_stage_container_rootmargin_widened_for_scroll_fix` + 3 jsdom |
| viewer.js | `applySidebarOpen`, `applyFitToWidthIfAuto`, `scheduleFit`, ResizeObserver wiring | `test_viewer_wires_resize_observer_and_fit_on_load` + `test_sidebar_toggle_is_static_not_inside_sidebar_render` |
| viewer.html | `.app-logo`, `#sidebar-toggle` static 마운트 | `test_viewer_html_has_logo_link_and_sidebar_toggle` |
| viewer.css | `.viewer-shell--sidebar-closed`, `.app-logo`, `.sidebar-toggle` + transitions | `test_viewer_css_has_sidebar_collapsed_and_app_logo` |
| _api_helpers | LLM_PROVIDER pin (guarded by prev_provider is None) | `test_make_test_client_only_pins_mock_when_unset` |

### R1 RE-CODE 신 식별자 / 정책

| RE-CODE 변경 | 새 식별자 / 정책 | 잠금 단위 테스트 |
| ----------- | ---------------- | ---------------- |
| `_api_helpers` 가드 복귀 | `if prev_provider is None:` 가드 | `test_make_test_client_only_pins_mock_when_unset` + 353 fast tests pass |
| `applyFitToWidthIfAuto` preferPage 기반 | `opts.preferPage ?? state.currentPage ?? 1` + `summaries.find` + subscribe 트리거 | `test_fit_to_width_uses_current_page_summary_not_first` + `test_compute_fit_zoom_handles_heterogeneous_pages` |
| 테스트 격리 인프라 | `tests/conftest.py` autouse `_isolate_llm_env` | 353 tests pass의 invariant (이전 leak 시나리오 통과) |

모든 새 식별자/정책 → 명시 테스트 잠금. R2 cross-verify가 "untested new paths" critique 던지지 못하도록 표 완비.

### 기존 contract 무회귀

- 350 → 353 fast tests, 모두 통과 (R0 16 + R1 3 = 19 신규)
- Phase 4/5/6a/6b 회귀 0
- `make_test_client`의 prev_provider guard 복귀 + autouse fixture → live LLM 테스트가 다시 신뢰 가능 (R2 critique 해소)
- 16개 grep tests + 6 jsdom tests + 3 dotenv backend tests로 R0+R1 cover

### Deviations from R1 (의도적, R1 응답)

- `_api_helpers`의 unconditional pin → guard 복귀 + conftest 격리 fixture (R1 critique 핵심 해소)
- `applyFitToWidthIfAuto`에 preferPage 매개변수 + currentPage 우선 선택 (R1 §4 fix)
- `loadDocument` 순서 그대로 (build → fit(preferPage) → scroll → mount → flash)
- subscribe()에서 currentPage 변경 시 fit 재호출 — heterogeneous 문서 대응

## 5-D. Scoring (100, v2)

| Item       | Score / Max | Evidence |
| ---------- | ----------- | -------- |
| 독창성     | 13 / 15     | (v1 동일) ResizeObserver 단일 signal + pickActivePage midpoint + zoomIsAuto 플래그 + preferPage 매개변수로 per-page fit 추상 깔끔. |
| 완결성     | **34 / 35** | v1 34 → 34 (유지). R1 critique의 fit-to-width 결함 해소 (mixed page → preferPage). 사이드바 reload 회귀 가드는 grep + state.js safeWrite로 lock 완료. |
| 안정성     | **30 / 30** | v1 29 → 30 (+1). conftest autouse 격리 fixture로 모든 테스트 사이 LLM env 누수 차단 — R1이 발견한 cross-test 누수 해결 + 무회귀. |
| 확장성     | **20 / 20** | v1 19 → 20 (+1). `applyFitToWidthIfAuto({preferPage})` API가 future per-page 동작 (Phase 6e 모델 토글 시 zoom 재계산 등)에 자연 흡수. `_isolate_llm_env`는 다른 phase의 env-touching 테스트 패턴 표준 제공. |
| **Total**  | **97 / 100** | (v1 95 → v2 **97**) |

## 5-E. Self verdict

- [x] PASS_CANDIDATE (≥95)
- [ ] FAIL → RE-CODE
- [ ] FAIL → RE-PLAN

근거:
- R1 substantive 결함 2건 모두 fix + autouse 격리 fixture 추가
- 353 fast tests + `make check` RC=0
- self 97/100 (R1 95 → v2 97)
- R2 cross-verify로 CONFIRM_PASS 기대.
