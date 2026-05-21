# Phase 4 — Plan

## Goal

Phase 3 FastAPI 위에 vanilla HTML/CSS/JS 정적 viewer를 올려, 실제 문서 한 권을 브라우저에서 자연스럽게 읽을 수 있는 UI를 만든다. 페이지 배경 PNG + block absolute 오버레이 + 키보드 네비 + 원본/번역 토글 + 줌. v0.2 마일스톤의 frontend 절반.

## Scope

**In**
- `src/ht_lens/api/static/` 안에 viewer 자산 (HTML 2 + CSS 2 + JS 7)
- `index.html` (문서 리스트) + `viewer.html` (단일 페이지 뷰)
- vanilla ES2022 modules (빌드 도구 없음, JS dep 없음)
- 좌측 사이드바 (페이지 번호 리스트) + 중앙 페이지 뷰
- 키보드: ←/→ (페이지 이동), T (번역 토글), Ctrl/Cmd+↑↓ (줌 단계)
- 줌: 50/75/100/125/150/200% (state.zoom; localStorage persist)
- block hover outline + click console.log (Phase 5 hook 자리)
- bbox 기반 폰트 fitting (`utils/font_fit.js`)
- 회전 페이지: rotation != 0 일 때 "지원 안 함" 안내 (Phase 6에서 정밀 매핑)
- TestClient integration test로 정적 자산 마운트 검증
- 수동 스크린샷 3장 + `docs/phases/phase-4/README.md`

**Out**
- Phase 5: 우측 채팅 패널, 핀, 질문 리스트
- Phase 6: 회전 페이지 정밀 매핑, 검색, export, 자동 UI 회귀 테스트
- JS 빌드 도구 (vite/esbuild/webpack)
- 외부 JS lib (markdown 등)
- React/Vue/Svelte
- Python dep 추가
- 페이지 썸네일
- 반응형 / 모바일

## Approach

### 1. 파일 구조

```
src/ht_lens/api/static/
  index.html
  viewer.html
  css/{base,viewer}.css
  js/
    api.js          # fetch wrapper
    state.js        # zoom, overlayMode (localStorage)
    index.js        # index.html 진입점
    viewer.js       # viewer.html 진입점
    components/
      page_view.js  # 페이지 배경 + 오버레이
      block.js      # 단일 block (fitting 포함)
      sidebar.js    # 페이지 리스트
    utils/
      font_fit.js   # bbox 폰트 계산
      keyboard.js   # 키 핸들러
```

### 2. URL 라우팅

- `/static/index.html` → 문서 리스트
- `/static/viewer.html?doc=N&page=M` → 페이지 뷰
- query 파싱은 `new URL(window.location)` (vanilla)
- 페이지 이동은 `window.location.href = ...`로 reload (SPA history API 미사용; 단순/안정 우선)

### 3. `index.html` — 문서 리스트

1. 헤더 "ht_lens" 타이틀
2. main 카드 그리드, 각 카드 = `<a href="viewer.html?doc=N&page=1">` (filename, src→tgt, num_pages, status, created_at)
3. `js/index.js`: `apiGet("/documents")` → 카드 렌더. 빈 리스트면 "no documents yet" + CLI hint. 에러 → 친화 메시지.

### 4. `viewer.html` — 페이지 뷰

레이아웃:
```
┌──────────┬─────────────────────────────────┬──────┐
│ sidebar  │ page-view                       │ side │
│ (200px)  │ (flex 1; 페이지 비율 유지)      │ slot │
└──────────┴─────────────────────────────────┴──────┘
```

- 우측 슬롯 `<aside class="right-slot" hidden>` (Phase 5 자리만)
- 헤더에 `{filename} · page {n}/{total}` + 키 hint

`js/viewer.js`:
1. URL query에서 `doc`, `page` 파싱 + 1 이상으로 clamp
2. `apiGet(/documents/{doc})` + `apiGet(/documents/{doc}/pages/{page})` 병렬 호출
3. rotation != 0 → "회전 페이지 미지원 (Phase 6)" 메시지 표시
4. `page_view`에 `(doc, page)` 넘김
5. `sidebar`에 `(doc, currentPage, totalPages)` 넘김
6. `attachKeyboard({...})` 부착

### 5. `page_view` 컴포넌트

- `<img class="page-bg" src="/documents/{id}/pages/{n}/image">`
- `<div class="overlay">` (position relative, page-bg와 동일 크기)
- `await img.decode()` 후 overlay 그림 — layout 확정 후
- zoom 적용은 `.stage { transform: scale(state.zoom); transform-origin: top left }`

좌표 계산:
- `scale_x = renderedPxWidth / page.width` (PDF point)
- `scale_y = renderedPxHeight / page.height`
- block: `left = bbox[0]*scale_x`, `top = bbox[1]*scale_y`, `width = (bbox[2]-bbox[0])*scale_x`, `height = (bbox[3]-bbox[1])*scale_y`

### 6. `block` 컴포넌트

- absolute div, `.block` + type modifier (`.block--text|image|header|table`)
- 모드별 표시 텍스트:
  - translation: `block.translated_text || block.original_text`
  - original: `block.original_text`
- image: 콘텐츠 없음 (투명, hover outline)
- header: `font-weight: 600` + `× 1.1` 폰트
- table: text와 동일 (table 인식은 Phase 6)
- 빈 block: `[빈 {type} 블록]` (chat_context와 일관)
- hover: `outline: 2px solid var(--accent); cursor: pointer`
- click: `console.log("block clicked", block.id)`만 (Phase 5 hook 자리)

폰트 fitting (`utils/font_fit.js`):
```js
export function computeFontSize(bboxW, bboxH, text, lang) {
  const lineCount = Math.max(1, (text.match(/\n/g) || []).length + 1);
  const heightSize = Math.floor((bboxH / lineCount) * 0.7);
  const avgCharW = lang === "ko" ? 1.0 : lang === "en" ? 0.55 : 0.85;
  const widthSize = Math.floor(bboxW / Math.max(text.length / lineCount, 1) / avgCharW);
  return Math.max(6, Math.min(32, Math.min(heightSize, widthSize)));
}
```

CSS:
```css
.block {
  position: absolute;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: pre-wrap;
  line-height: 1.15;
}
```

bbox 안 안 들어가면 ellipsis로 잘림 시각화. 80% 만족은 verify spot check에서 측정.

### 7. `sidebar` 컴포넌트

```html
<aside class="sidebar">
  <h2>{doc.filename}</h2>
  <ol class="page-list">
    <li><a href="?doc=N&page=K">K</a></li>
    ...
  </ol>
</aside>
```

현재 페이지 = `.page-item--active`. 클릭 시 query 변경 → 새 페이지 reload.

### 8. `state.js`

```js
export const state = {
  zoom: parseFloat(localStorage.getItem("ht_lens.zoom") || "1.0"),
  overlayMode: localStorage.getItem("ht_lens.overlay") || "translation",
};
export function setZoom(z) { state.zoom = z; localStorage.setItem("ht_lens.zoom", z); }
export function toggleOverlay() { ... persist ... }
```

페이지 인덱스/현재 doc는 URL이 source of truth (주소 공유 = 상태 공유).

### 9. `keyboard.js`

```js
export function attachKeyboard({ onPrev, onNext, onToggle, onZoomIn, onZoomOut }) {
  document.addEventListener("keydown", (e) => {
    if (e.target.matches("input, textarea")) return;
    if (e.key === "ArrowLeft") onPrev();
    else if (e.key === "ArrowRight") onNext();
    else if (e.key === "t" || e.key === "T") onToggle();
    else if ((e.metaKey || e.ctrlKey) && e.key === "ArrowUp") { e.preventDefault(); onZoomIn(); }
    else if ((e.metaKey || e.ctrlKey) && e.key === "ArrowDown") { e.preventDefault(); onZoomOut(); }
  });
}
```

마우스 휠 줌은 안 함 (브라우저 native zoom과 충돌 위험; +/- 키도 안 함, Cmd+↑↓로 통일).

### 10. `api.js`

```js
export class ApiError extends Error {
  constructor(status, body) { super(`${status}: ${body}`); this.status = status; }
}
export async function apiGet(path) {
  const r = await fetch(path, { headers: { "Accept": "application/json" } });
  if (!r.ok) throw new ApiError(r.status, await r.text());
  return r.json();
}
```

호출처에서 catch → main 영역에 친화 메시지.

### 11. 회전 페이지 처리 (prompt 결정 (A))

`viewer.js`에서 `page.rotation !== 0` 분기:
```html
<div class="rotation-warning">
  ⚠️ 회전 페이지 (rotation={N}°)는 아직 지원되지 않습니다.<br>
  bbox-to-pixel 매핑 정밀화는 Phase 6에서 다룹니다.<br>
  ← 또는 → 키로 다른 페이지로 이동하세요.
</div>
```

block 오버레이는 그리지 않음. 페이지 배경 PNG도 표시 안 함 (왜곡된 좌표 사용 방지).

### 12. 정적 마운트 정합성

`api/app.py:107-113`에 이미 `app.mount("/static", StaticFiles(...))` 있음 → 변경 불필요. integration test로 새 파일들 마운트 동작 확인.

### 13. 스크린샷 캡처

수동이 기본. headless chromium이 있으면 보너스로 시도:
- `chromium --headless --screenshot=out.png --window-size=1400,900 http://localhost:PORT/...`
- 없으면 verify.md에 절차 명시 후 Human 위임.
- 3장: `01-doc-list.png`, `02-page-translation.png`, `03-page-original.png`
- `docs/phases/phase-4/screenshots/`에 커밋.

### 14. JS 품질 가드

- ES2022 modules (`type="module"`)
- 최상단 `"use strict";` (모듈은 암묵적이지만 명시)
- 모든 함수 JSDoc 한 줄
- 에러는 `console.error` + 사용자 메시지

### 15. Phase 5 미리 준비

- 우측 슬롯 DOM만 (hidden)
- block click 콜백을 `state.onBlockClick` hook으로 → Phase 5는 hook만 교체
- CSS 변수 `--accent`, `--text-secondary`, `--surface` base.css에 정의 → Phase 5 재사용

## File-level changes

| Path | Action | Note |
| ---- | ------ | ---- |
| `src/ht_lens/api/static/index.html` | NEW | 문서 리스트 |
| `src/ht_lens/api/static/viewer.html` | NEW | 페이지 뷰 |
| `src/ht_lens/api/static/css/base.css` | NEW | reset + 변수 + 글로벌 |
| `src/ht_lens/api/static/css/viewer.css` | NEW | sidebar + page-view 레이아웃 |
| `src/ht_lens/api/static/js/api.js` | NEW | fetch wrapper |
| `src/ht_lens/api/static/js/state.js` | NEW | 전역 state + localStorage |
| `src/ht_lens/api/static/js/index.js` | NEW | index 진입점 |
| `src/ht_lens/api/static/js/viewer.js` | NEW | viewer 진입점 |
| `src/ht_lens/api/static/js/components/page_view.js` | NEW | 페이지 + 오버레이 |
| `src/ht_lens/api/static/js/components/block.js` | NEW | block 렌더 |
| `src/ht_lens/api/static/js/components/sidebar.js` | NEW | 페이지 리스트 |
| `src/ht_lens/api/static/js/utils/font_fit.js` | NEW | bbox 폰트 |
| `src/ht_lens/api/static/js/utils/keyboard.js` | NEW | 키보드 |
| `tests/integration/test_static_serving.py` | NEW | TestClient |
| `docs/phases/phase-4/README.md` | NEW | 스크린샷 설명 |
| `docs/phases/phase-4/screenshots/*.png` | NEW | 3장 |

## Dependencies (new)

| Package | Why |
| ------- | --- |
| (none) | Phase 4는 frontend만. Python/JS 외부 lib 없음. |

## Test strategy

### Integration (TestClient, fast)
- `tests/integration/test_static_serving.py`:
  - `/static/index.html` 200 + text/html + 핵심 마커 ("viewer.html?doc=")
  - `/static/viewer.html` 200 + text/html
  - `/static/css/base.css` 200 + text/css
  - `/static/css/viewer.css` 200
  - `/static/js/api.js` 200 + application/javascript
  - `/static/js/viewer.js` 200
  - `/static/js/components/page_view.js` 200
  - `/static/js/utils/font_fit.js` 200
  - `/static/.gitkeep` 200 (Phase 3 회귀 가드)
  - 존재하지 않는 경로 404
  - directory traversal 시도 → 거부 (StaticFiles 자체 차단)

### 수동 검증 (verify.md 5-B)
- 브라우저 `/static/index.html` 진입
- 문서 리스트 표시 → 첫 문서 클릭 → viewer
- 페이지 렌더링 (배경 PNG + 오버레이)
- ←/→ T Cmd+↑↓ 동작
- 콘솔 에러 0
- 스크린샷 3장 캡처
- 폰트 fitting spot check (한국어 1, 영문 1 페이지에서 잘림 비율 ≤ 20%)

### JS unit test 없음
빌드 없는 vanilla. Phase 5/6에서 늘어나면 도입.

## DoD mapping

| DoD item | How to satisfy | Evidence plan |
| -------- | -------------- | ------------- |
| 실제 문서 한 권을 자연스럽게 읽을 수 있음 | viewer.html + nav + sidebar + overlay | 수동 + 스크린샷 |
| 한/영 폰트 fitting 80% 이상 만족 | `utils/font_fit.js` per-lang 가중 | spot check (verify 5-B) |
| 줌·이동 부드러움 | CSS transform: scale + 페이지 reload | 수동 |
| 배경 PNG + block absolute 오버레이 | `page_view.js` + `block.js` | integration test + 스크린샷 |
| 키보드 네비/토글/줌 | `keyboard.js` | 수동 |
| block hover/click | `block.js` hover + console.log | 수동 (콘솔 확인) |

## 미결정 사항 (debate 검토 대상)

1. **사이드바 페이지 리스트 UI**: 텍스트 number list — plan 채택. 카드/미니맵은 cost > benefit.
2. **줌 단계**: 50/75/100/125/150/200 — plan 6단계.
3. **block hover delay**: 즉시 — plan 채택.
4. **줌 시 폰트 fitting 재계산**: zoom 변경 시 CSS transform만 (재계산 X) — plan 채택. 텍스트 선명도는 transform scale로 충분.
5. **이미지 블록 표시**: invisible + hover outline — plan 채택.
6. **로딩 상태**: 간단 inline "loading..." — plan 채택.
7. **에러 페이지**: main 영역에 친화 메시지 — plan 채택.
8. **반응형**: desktop only — plan 채택.
9. **state persistence**: zoom + overlayMode만 localStorage — plan 채택. doc/page는 URL.
10. **viewer/index 공유 코드**: api.js + state.js로 자연스럽게 모임 — 별도 분리 안 함.

debate에서 Codex가 위 영역의 약점 (특히 4, 7, 폰트 fitting 임계값) 찌를 가능성 큼.
