# Phase 4 — Challenge

## Debate responses

### 1. Over-engineering

**File split 과도** — **PARTIAL accept**
Codex 주장: components/utils 폴더 분리 + Phase 5 hook 자리 잡기가 scope creep.
응답: viewer.html은 페이지 뷰 + 사이드바 + 키보드 + 폰트 fitting을 모두 다루므로 200~300줄 단일 파일은 가독성 떨어짐. 그러나 `state.onBlockClick` 같은 Phase 5 hook 예약은 미리 만들지 않고 Phase 5에서 직접 추가하기로 변경. components/utils 분리는 유지.
**결정**: components/utils 폴더 유지, Phase 5 hook 예약 제거.

**index.html dashboard scope creep** — **REJECT**
Codex 주장: 문서 리스트는 roadmap deliverable에 없음.
응답: viewer는 단일 페이지 URL을 받지만 진입 경로가 필요. 카드 5개 필드는 `DocumentRead`가 이미 제공하는 데이터의 단순 표시. 완전히 빼면 사용자가 `?doc=1` 같은 URL을 외워야 하는 비용 발생. 유지.

**`utils/font_fit.js` layout engine 과도** — **ACCEPT**
Codex 주장: per-lang 가중치, header 배수 등 speculative.
응답: 더 단순한 알고리즘으로 대체. `canvas.measureText` + 이진 탐색으로 실제 텍스트 폭을 측정해 bbox에 맞춤 (debate §4의 alternative 채택). per-lang 하드코딩 가중치 폐기. header 배수는 CSS에서 `font-weight: 600`만 적용, 폰트 크기는 동일 알고리즘.
**결정**: canvas.measureText 기반 fitting + per-lang 가중치 제거.

### 2. Hidden assumptions

**Full reload가 "줌·이동 부드러움" 깨뜨림** — **ACCEPT**
Codex 주장: ←/→ 매번 전체 reload + PNG refetch.
응답: `history.pushState` 채택. viewer.html은 SPA shell, page data만 in-place 업데이트. PNG는 같은 URL이면 브라우저 캐시 (Phase 3에서 `Cache-Control: max-age=2592000`).
**결정**: history.pushState로 전환. popstate handler로 브라우저 back/forward 지원.

**언어 가중치 단일 신뢰** — **ACCEPT** (§1과 함께 해소)
canvas.measureText로 실제 측정하므로 per-lang 가중치 폐기.

**회전 페이지 silent black hole** — **PARTIAL accept**
Codex 주장: warning만 표시하고 page-bg PNG를 빼면 "한 권 자연스럽게" 깨짐.
응답: PNG 배경은 그대로 표시 (사용자가 페이지 자체는 볼 수 있음). overlay만 그리지 않음. PNG 위에 작은 banner "회전 페이지: 텍스트 오버레이 미지원 (Phase 6)".
**결정**: rotated page는 PNG-only + banner, overlay 생략.

**`translated_text || original_text` silent fallback** — **ACCEPT**
응답: `translated_text`가 null이면 block에 `data-fallback="original"` 표시 + CSS dotted underline. 사용자가 "이 block 미번역" 인지.
**결정**: fallback 시 시각 표시 추가.

### 3. Edge cases

**bbox sanity check 없음** — **ACCEPT**
응답: `page_view.js`에서 block 렌더 전 `bbox` 검증. (a) 4 floats, (b) `x0 < x1`, `y0 < y1`, (c) `x0 >= 0`, `y0 >= 0`, (d) `x1 <= page.width + tolerance`, `y1 <= page.height + tolerance` (10% tolerance). 위반 시 skip + `console.warn`.
**결정**: 추가.

**`pre-wrap` 멀티라인 ellipsis 신뢰성 부족** — **ACCEPT (canvas.measureText로 해소)**
응답: canvas.measureText로 폰트 결정 시 wrapping 시뮬레이션해서 bbox에 들어가는 최대 사이즈 찾기. CSS `text-overflow: ellipsis`는 fallback (6px clamp + 잘림).
**결정**: 이진 탐색 + line wrapping.

**`[빈 {type} 블록]` noise** — **ACCEPT**
응답: viewer는 빈 block에 placeholder 표시 안 함. transparent. hover outline만. chat_context의 placeholder는 LLM input 목적이라 별개.
**결정**: 빈 block은 transparent.

### 4. Alternative approaches

**`history.pushState`** — **ACCEPT** (§2와 같음)

**`pixel_w`/`pixel_h` intrinsic 좌표계** — **ACCEPT**
응답: `.stage` `width: pixel_w; height: pixel_h`로 고정 → block 좌표는 `bbox * (pixel_w / page.width)`로 한 번만 계산 → zoom은 `.stage { transform: scale(zoom) }`. browser layout 재측정 불필요.
**결정**: pixel-space intrinsic stage.

**`canvas.measureText` + binary search** — **ACCEPT** (§1과 같음)

### 5. Missing tests

**`test_viewer_html_references_resolvable_assets`** — **ACCEPT**
응답: viewer.html / index.html에서 `<script src>`와 `<link href>` 추출 → 각 path가 200 응답하는지.
**결정**: 추가.

**`test_index_empty_state_for_no_documents`** — **PARTIAL accept**
응답: 서버 측 `[]` 응답은 `test_api_documents`에서 커버. index.html이 `[]` 처리하는지는 JS 동작 (TestClient 불가). index.js에 "no documents" 문구 마커가 코드에 있는지 grep test.
**결정**: grep 기반 정적 검증 + 수동 절차.

**`test_viewer_handles_invalid_query_and_missing_page`** — **PARTIAL accept**
응답: 같은 이유. viewer.js에 query clamp 로직 grep test.
**결정**: grep + 수동.

**`test_font_fit_mixed_cjk_long_ascii_does_not_overflow_bbox`** — **ACCEPT**
응답: node가 있으면 subprocess + JS 직접 실행. canvas.measureText는 node에 없으므로 알고리즘 테스트용 fallback (단순 char-width 추정)을 module에 별도 export → 그걸로 monotonicity + bbox respect 검증.
**결정**: `tests/integration/test_font_fit_js.py` node 있으면 실행, 없으면 skip.

**Rotated/partial-translation fixture** — **ACCEPT**
응답: verify.md 5-B에 rotated page + partial translation 시나리오 추가.
**결정**: verify에 명시 + 가용 fixture 한도.

---

## Plan revisions (after debate)

1. **`history.pushState`로 in-place 페이지 이동** (전체 reload 폐기 + popstate handler)
2. **`pixel_w`/`pixel_h` intrinsic 좌표계** (`.stage` scale로 zoom)
3. **`utils/font_fit.js`**: canvas.measureText + 이진 탐색, per-lang 가중치 폐기, 단순 fallback 알고리즘은 module에서 별도 export
4. **회전 페이지**: PNG 배경 표시 + banner, overlay 생략
5. **fallback 시각 표시**: `translated_text == null` block에 dotted underline
6. **bbox sanity check**: 4-float + 양수 + 페이지 bounds (10% tolerance)
7. **빈 block**: placeholder 텍스트 제거 (transparent)
8. **Phase 5 hook 예약 제거**: `state.onBlockClick`은 Phase 5에서 추가
9. **테스트 추가**:
   - viewer.html / index.html `<script src>` `<link href>` 200 확인
   - index.js "no documents" 마커 grep
   - viewer.js query clamp 마커 grep
   - `test_font_fit_js.py` node 있을 때 algorithm 검증
10. **verify.md 5-B**: rotated page + partial translation 시나리오 명시

---

## DoD checklist

| DoD item | Status | Evidence |
| -------- | ------ | -------- |
| 실제 문서 한 권을 자연스럽게 읽을 수 있음 | planned | 수동 + 스크린샷 |
| 한/영 폰트 fitting 80% 이상 만족 | planned | spot check + font_fit_js test |
| 줌·이동 부드러움 | planned | pushState + CSS scale + 수동 |
| 배경 PNG + block absolute 오버레이 | planned | integration + 스크린샷 |
| 키보드 네비/토글/줌 | planned | 수동 |
| block hover/click (패널 자리) | planned | hover outline + console.log |

---

## Risk register

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| canvas.measureText로 측정한 폰트가 실제 렌더와 미세 차이 | Medium | 일부 block 잘림 | ellipsis fallback + 6~32px clamp |
| pushState 후 브라우저 back/forward 깨짐 | Low | UX | popstate 핸들러 추가 |
| Rotated page만 있는 PDF에서 빈 화면 | Low | 사용 불가 | PNG 배경은 항상 표시 |
| Block hover outline이 텍스트 가독성 해침 | Low | 미세 | hover 시 outline만 (배경 변경 X) |
| `localStorage` 비활성 환경 | Low | persist 안 됨 | try/catch + in-memory fallback |
| node 시스템 binary 부재 → font_fit_js test skip | Medium | 자동 검증 약화 | skip 명시 + 수동 spot check |

---

## Decision

- [x] PASS → proceed to code (plan revisions 10건 적용)
- [ ] RE-PLAN (reason: )

Codex 비판 13건 중 8건 ACCEPT, 4건 PARTIAL ACCEPT, 1건 REJECT (index.html dashboard). Plan revision 10건 반영해 코드 단계 진입.
