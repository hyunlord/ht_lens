# Phase 6c — Plan

## Goal

v0.5 실사용 직후 발견한 5건 즉각 사용성 gap 일괄 처리. v0.6 마일스톤 (Viewer Polish).

## Scope

**In**
- `.env` 자동 로드 (ht-lens 진입 시 `python-dotenv.load_dotenv`)
- `scripts/dev_serve.sh` 보완: `.env` source (이중 안전망)
- 페이지 진입 시 fit-to-width 자동 zoom
- 좌측 사이드바 토글 (버튼 + localStorage 상태)
- 자연 스크롤 다음-페이지 mount 누락 fix
- 메인 메뉴 네비 (viewer 좌상단 ht_lens 텍스트 → index.html 링크)
- Tests:
  - `test_dotenv_load.py` (신규, subprocess + os.environ 검증)
  - `test_static_serving.py` 확장 (사이드바 토글/fit-to-width/로고 링크 grep)
  - `test_stage_container_js.py` 확장 (자연 스크롤 회귀 jsdom)
  - `@pytest.mark.llm` 1건: explain 호출 후 DB model 컬럼 검증
- 6 screenshots: fit / 사이드바 collapsed/expanded / 자연 스크롤 mid / logo back / real-LLM
- 도메인 새 dep 0 (python-dotenv는 이미 pydantic-settings transitive로 lock 안에 있음)

**Out**
- Phase 6d (파일 업로드, 자동 요약, jobs 테이블)
- Phase 6e (핀 디자인, 사이드바 리사이즈, 이미지 확대, streaming, 모델 토글)
- Phase 6f (추출 품질 debt)
- viewMode 동작 변경 (Phase 6b 그대로)
- jsdom CI 설치 (Phase 6e)
- Phase 6a R2 위임 (Phase 6e)

## Approach

### 1) `.env` 자동 로드

#### Fix A (필수, production-correct): `cli.py` 최상단에서 `load_dotenv`

`python-dotenv`는 `pydantic-settings`의 dependency로 lock에 이미 포함. import 가능. pyproject에 직접 dep 추가는 robustness 위해 권장 — 1줄.

```python
# cli.py 최상단
from dotenv import load_dotenv
from pathlib import Path

# CWD 우선 (사용자가 다른 dir에서 호출 가능), repo root fallback.
# override=False — 이미 셸에서 export된 환경변수는 보존 (test 친화적).
_REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(dotenv_path=Path.cwd() / ".env", override=False)
load_dotenv(dotenv_path=_REPO_ROOT / ".env", override=False)
```

`pyproject.toml`에 `python-dotenv >= 1.0` 추가 — transitive 의존을 명시 의존으로 격상.

#### Fix B (dev convenience): `scripts/dev_serve.sh`에서 `.env` source

```bash
if [[ -f "$REPO_ROOT/.env" ]]; then
  set -a
  source "$REPO_ROOT/.env"
  set +a
fi
```

`uv run ht-lens serve` 호출 직전에 추가. (A)가 production-correct이고 (B)는 셸 진입 시점에서 보이게 — 둘 다 적용.

#### 검증
- `pgrep ht_lens.api` PID의 `/proc/PID/environ`에 `LLM_PROVIDER=openai_compat` 등 보임
- 새 thread + explain 호출 → DB `messages.model` = `qwen3.6-27b`
- 라이브 호출 latency 3~30초 (mock 0.02s 아님)

#### 회귀 테스트
- `test_dotenv_load.py::test_cli_import_populates_llm_env`:
  - 임시 `.env` 작성 후 `subprocess.run(["uv","run","python","-c","import ht_lens.cli; import os; print(os.environ.get('LLM_PROVIDER'))"], cwd=tmp)` → 출력 검증
- `test_dotenv_load.py::test_env_override_false_preserves_explicit_env`:
  - 미리 `LLM_PROVIDER=mock`을 환경에 두고 `.env`에 `openai_compat` 두기 → `mock` 유지 (override=False)

### 2) fit-to-width 자동 zoom

#### 알고리즘 (`utils/viewport.js` 신규)
```js
export function computeFitZoom({ pageWidthPt, stageWidthPx, scale, viewMode }) {
  // pageWidthPt: PDF point width (서머리에서 옴, 612 = letter)
  // scale: render scale (pixel/pt, 보통 2.78)
  // viewMode: 'translation' | 'original' | 'both'
  const paneCount = viewMode === 'both' ? 2 : 1;
  const naturalPx = pageWidthPt * scale * paneCount;
  const margin = 32 + (paneCount - 1) * 16; // .stage-container padding + .page-row gap
  const target = (stageWidthPx - margin) / naturalPx;
  // Clamp to [0.25, 2.0] and snap to nearest ZOOM_STEPS.
  return Math.max(0.25, Math.min(2.0, target));
}
```

#### 호출 시점 (단일 - debate에서 확정)
- 문서 첫 진입 시 (loadDocument 끝에서)
- 사이드바 토글 시 (stage width 변경)
- viewMode 변경 시 (paneCount 변경)
- viewport resize 시 (rAF 디바운스 200ms)

#### state 정책
- 자동 fit은 `state.zoom`을 변경하지만 **localStorage 저장 안 함** (session-only)
- 사용자가 Ctrl+↑↓로 명시적 변경 시만 localStorage 저장
- `setZoom(z, {persist: true})` vs `setZoomAutoFit(z)` 두 헬퍼

#### 회귀 테스트
- `test_static_serving.py`: `computeFitZoom` 마커 + 호출 grep
- jsdom-light: `computeFitZoom({pageWidthPt:612, stageWidthPx:1200, scale:2.78, viewMode:'translation'})` → ~0.69

### 3) 사이드바 토글

#### UI (`sidebar.js` 수정 + `viewer.css`)
- 사이드바 상단에 `<button class="sidebar-toggle">◀</button>` (열림 시) / `▶` (닫힘 시)
- 닫힘: `aside.sidebar` width 0, 토글 버튼만 viewer 좌상단에 fixed로 표시
- CSS transition 0.2s
- stage-container width는 grid-template-columns가 자동 처리

#### State (`state.js`)
- `state.sidebarOpen: boolean` (기본 true)
- localStorage key `ht_lens.sidebarOpen`
- `setSidebarOpen(open)` / `toggleSidebar()` 헬퍼

#### 단축키
- **없음** (Cmd+\은 충돌 우려). 버튼 클릭만.

#### 사이드바 닫힘에서 토글 버튼 어디?
- 닫힘 시 `position: fixed; top: 12px; left: 8px; z-index: 50` — viewer 좌상단 모서리
- 열림 시 사이드바 안의 `.sidebar-header` 안에 inline

#### 회귀 테스트
- grep: `sidebar-toggle`, `setSidebarOpen`, `toggleSidebar`, `STORAGE_SIDEBAR_OPEN`
- viewer.css: `.sidebar--collapsed`, `.sidebar-toggle`

### 4) 자연 스크롤 다음 페이지 mount 누락 fix

#### 가설 진단 (코드 review)
Phase 6b `stage_container.js`의 `attachIntersectionObserver`:
- rootMargin: `100% 0px 100% 0px` (위/아래 한 화면 분)
- threshold: `[0, 0.25, 0.5, 0.75, 1]`

문제 가능성:
- (i) 페이지가 매우 큰 경우 (pixel_h ≈ 2200px) viewport가 1000px이면 한 화면 = 1000px ≪ 2200px → rootMargin이 부족할 수 있음
- (ii) IO entry의 `intersectionRatio`가 매우 작아서 `visibility` map의 "best" 페이지 갱신이 늦음 → currentPage가 늦게 바뀜 → 이웃 prefetch가 늦게 도움
- (iii) `unmountPage` race가 빠른 스크롤에서 다음 페이지 mount를 abort시킬 수 있음 (현재 RE-CODE 1 fix 이후에도)

#### Fix 방향
1. **rootMargin을 viewport 높이의 200%로** (`200% 0px 200% 0px`) — 1.5~2 페이지 미리 마운트
2. **active page 결정 로직 보강**: ratio 외에 viewport 중심점에 가장 가까운 페이지 추적
3. **scroll 이벤트 listener 보조**: IO + scroll 둘 다 사용 — scroll 시 viewport 중심점 페이지를 currentPage로

진단을 plan author가 한 다음 fix 방향 결정 (debate §4). plan은 **(1) + (2)** 우선 채택. (3)은 debate에서 검토.

#### 회귀 테스트
- jsdom-light: 6 페이지 mount/unmount 시뮬레이션 — 가짜 scrollTop을 0 → end로 이동시키면서 mountPage 호출 순서 검증
- 수동 evidence: screenshot 04 (page 3-4 visible mid-scroll)

### 5) 로고 → index.html

#### UI (`viewer.html`)
```html
<header class="app-header">
  <a href="/static/index.html" class="app-logo"><h1>ht_lens</h1></a>
  ...
</header>
```

#### CSS (`viewer.css`)
- `.app-logo` text-decoration 없음, hover시 색 약간 변화

#### 동작
- 단순 `<a href>` — popstate 없음, 페이지 전환 (브라우저 native)
- `history.pushState` 안 씀 (서로 다른 SPA entry: viewer ↔ index)
- 클릭 후 index.html에서 다시 같은 doc 클릭 → viewer 재진입 + 모든 state localStorage에서 복원

#### 회귀 테스트
- grep: `app-logo`, `href="/static/index.html"` in viewer.html

### 6) Mock → Real LLM 전환 evidence

#### 검증 시나리오
1. Fix A + B 적용 후 `scripts/dev_serve.sh restart`
2. `pgrep ht-lens` → PID의 `/proc/PID/environ`에 `LLM_PROVIDER=openai_compat` 보임
3. 새 thread 생성 + explain 호출 → DB의 `messages.model` 컬럼 = `qwen3.6-27b`
4. screenshot 06: DB SELECT 결과 또는 viewer 응답 화면

#### `@pytest.mark.llm` 신규
- `tests/integration/test_api_live_llm.py`에 1건 추가 (or 기존 확장):
  - subprocess로 ht-lens serve 띄움 (LLM env propagation 가정)
  - 또는 TestClient + lifespan + LLM_PROVIDER=openai_compat 환경에서 직접 호출
  - assistant message.model이 'qwen3.6-27b'로 시작 확인

### 7) Phase 6b 호환

- `state.js`의 viewMode/viewModeActual/pageDataById 그대로
- `stage_container.js`의 mountToken/AbortController/scheduleFarPageUnmount 그대로
- sidebar.js 확장 (토글 추가) — 기존 onExport/onOpenSearch/onSelectThread/onNavigatePage 그대로
- viewer.js의 stageContext에 `sidebarOpen` 전달 → fit-to-width 계산 시 사용

## File-level changes

| Path | Action | Note |
| ---- | ------ | ---- |
| `pyproject.toml` | MODIFY | + `python-dotenv >= 1.0` (transitive → explicit) |
| `src/ht_lens/cli.py` | MODIFY | + `load_dotenv` 진입부 (CWD + repo root) |
| `scripts/dev_serve.sh` | MODIFY | + `.env` source 안전망 |
| `src/ht_lens/api/static/viewer.html` | MODIFY | `app-logo` 링크 + sidebar-toggle 마운트 |
| `src/ht_lens/api/static/js/state.js` | MODIFY | + sidebarOpen + setSidebarOpen + toggleSidebar + setZoomAutoFit(persist=false) |
| `src/ht_lens/api/static/js/components/sidebar.js` | MODIFY | + 토글 버튼 + collapsed 분기 |
| `src/ht_lens/api/static/js/components/stage_container.js` | MODIFY | rootMargin 200% + currentPage 중심점 결정 보강 + fit-to-width hook |
| `src/ht_lens/api/static/js/utils/viewport.js` | NEW | `computeFitZoom` helper |
| `src/ht_lens/api/static/js/viewer.js` | MODIFY | + fit-to-width 호출 (loadDocument + viewMode/sidebar 변경 + resize) + sidebar 토글 wiring |
| `src/ht_lens/api/static/css/viewer.css` | MODIFY | sidebar transition + collapsed + app-logo |
| `tests/integration/test_dotenv_load.py` | NEW | subprocess 검증 |
| `tests/integration/test_static_serving.py` | MODIFY | + 6c grep markers |
| `tests/integration/test_stage_container_js.py` | MODIFY | + 자연 스크롤 회귀 jsdom |
| `tests/integration/test_api_live_llm.py` (or 새 파일) | MODIFY | + LLM_PROVIDER env로 model 검증 |
| `docs/phases/phase-6c/{README.md, screenshots/*}` | NEW | 6 screenshots |

## Dependencies (new)

| Package | Why |
| ------- | --- |
| `python-dotenv >= 1.0` | `.env` 자동 로드 — 이미 pydantic-settings transitive로 lock에 있음. pyproject에 명시 의존으로 격상 (transitive 깨질 위험 제거). |

## Test strategy

### Unit / fast
- `test_dotenv_load.py`:
  - subprocess가 `.env`의 LLM_PROVIDER를 import 시 환경에 노출
  - `override=False` 동작 (이미 export된 변수 보존)
- `test_static_serving.py` 확장:
  - viewport.js `computeFitZoom` export 마커
  - state.js `sidebarOpen` / `setSidebarOpen` / `toggleSidebar` / `STORAGE_SIDEBAR_OPEN` / `setZoomAutoFit`
  - sidebar.js `sidebar-toggle` 클래스 + `onToggle` 호출
  - stage_container.js rootMargin 변경 (`200%`) + active-page 중심점 결정 마커
  - viewer.html `app-logo` 링크 + 사이드바 토글 마운트
  - viewer.css `.sidebar--collapsed` + `.app-logo` + transition
- `test_stage_container_js.py` jsdom 확장:
  - 합성 6 페이지 mount/unmount 시나리오에서 mountPage 호출이 정확히 6번 (boundary 가드 + IO 시뮬)
  - active page 중심점 결정 (가짜 entries 입력 → bestPage 검증)

### Live LLM (`@pytest.mark.llm`)
- explain 호출 후 DB 메시지의 model 필드 `qwen3.6-27b` (또는 model_name이 시작하는 값) 검증

### Manual (verify 5-B)
- DB model column SELECT (mock cutoff 직전/후 비교)
- 6 page sample_mixed.pdf로 자연 스크롤 끝까지
- 사이드바 토글 + reload (localStorage 복원)
- 로고 클릭 → index.html
- 6 screenshots

## DoD mapping

| DoD item | How to satisfy | Evidence plan |
| -------- | -------------- | ------------- |
| viewer AI 응답이 진짜 sglang (mock 아님) | cli load_dotenv + dev_serve source + factory에서 LLM_PROVIDER=openai_compat 진입 | screenshot 06 + DB SELECT 검증 + @pytest.mark.llm test |
| 새 페이지 진입 시 자동 viewport 폭 fit | computeFitZoom + loadDocument 종료 시 호출 | screenshot 01 + grep test |
| 사이드바 토글 동작 (200px ↔ 0) | sidebarOpen state + CSS transition + 버튼 | screenshot 02 (collapsed) + 03 (expanded) + grep |
| 자연 스크롤 6페이지 끝까지 | rootMargin 200% + active page 중심점 보강 | screenshot 04 + jsdom test |
| 로고 클릭 → index.html | app-logo `<a href>` 링크 | screenshot 05 + grep |
| 사이드바 상태 localStorage 저장 | STORAGE_SIDEBAR_OPEN + setSidebarOpen 안에서 safeWrite | grep + 수동 reload 시나리오 |

## 미결정 사항 (debate 검토 대상)

1. **dotenv 로드 위치**: cli.py 최상단 (지금 plan) vs api/app.py lifespan — lifespan은 factory가 이미 import된 후라 늦을 수 있음. cli.py가 더 빠름.
2. **fit-to-width 알고리즘 max/min clamp 값**: 2.0 / 0.25 vs Phase 4 ZOOM_STEPS 한계 (0.5 / 2.0). 첫 진입은 0.25까지 허용 (작은 viewport 대비).
3. **사이드바 토글 단축키**: 없음 (plan). Cmd+\ 추가는 debate에서 결정.
4. **자연 스크롤 fix 우선 (1)+(2) vs (3) scroll listener 추가**: (1)+(2)만 plan. scroll listener는 IO와 race 가능.
5. **로고 링크 SPA vs hard reload**: hard reload (`<a href>`). SPA는 Phase 6e.
6. **fit-to-width 시 localStorage 보존**: 자동은 session-only. 수동 zoom만 저장.
7. **`@pytest.mark.llm` test 위치**: 기존 `test_api_live_llm.py` 확장 vs 신규 파일.
8. **mock vs real 검증 자동화**: subprocess로 `ht-lens serve` 띄우는 건 너무 무거움 → DB row 검증으로 cap.
9. **dev_serve.sh의 source vs cli.py dotenv 중복**: 둘 다 (이중 안전망). dev_serve의 source는 비-uv 호출 시 친화적.
10. **viewMode 변경 시 fit-to-width 자동 재호출**: plan 채택 (paneCount 변경).
11. **사이드바 닫힘 상태에서 단축키 Cmd+B 채팅 토글**: viewMode/사이드바 독립이라 영향 없음 — Phase 5 동작 유지.

debate에서 Codex가 위 영역 (dotenv 시점, fit-to-width 무한 루프 위험, IO+scroll race, 사이드바 토글 시 fit 재계산 race 등) 찌를 가능성.
