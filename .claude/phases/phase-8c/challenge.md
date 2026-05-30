# Phase 8c — Challenge (debate 대응)

**Decision: PASS** (정제 후 진행). 핵심 접근(chunk reflow + KaTeX 재사용 + 좌우 토글) 건전. Codex 지적 다수 수용 — 특히 render-cache(Page 행 회피) + .jpg validator.

## Debate responses

### 1. Over-engineering
- **Page 행 생성이 1.x pages 테이블과 2.0 얽힘** → **accept (강)**. **Page 행 안 만듦.** 좌측 pane 원문은 **render-cache** `data/extracts_v2/<doc>/pages/page_<idx>.png` (serve-time/setup 시 PyMuPDF 1회 렌더, doc_id+page_idx 키). pages 테이블 무수정. 8a Page 연기분은 "행 생성"이 아니라 "캐시 렌더"로 해소.
- **dev DB가 phase 아티팩트로 하드코딩** → **accept (contract化)**. `HT_LENS_DB_URL=sqlite+aiosqlite:///.../ht_lens_v2.db` 명시 계약. verify는 chunks 존재 확인 후 진행(빈 1.x DB로 false success 방지).
- **reflow.js + chunk_render.js 분리 조기** → **accept**. 8c는 단일 `reflow.js` 모듈. 컴포넌트 분리는 8d(chat/pin) 때.
- **image-serving 중복** → **accept**. 공통 v2 path validator 1개(아래), pages.py 패턴 재사용, parallel 보안 동작 안 만듦.

### 2. Hidden assumptions
- **HT_LENS_DB_URL 안 걸면 1.x DB 조회** → **accept**. verify에서 `SELECT COUNT(*) FROM chunks > 0` 선확인. reflow API는 chunks 없으면 404.
- **source PDF 경로 미저장** → **accept**. v2 ingest는 PDF 경로 미보유. 8c page-render는 **MinerU origin.pdf**(auto/*_origin.pdf, 챕터 PDF) 또는 setup 시 렌더된 캐시 PNG 사용. 경로 없으면 **deterministic 에러**(bogus Page/크래시 금지). test_reflow_page_image_requires_configured_source_pdf.
- **page-level sync가 DoD 재해석** → **accept (Planner 승인 명시)**. 결정 B에서 **Planner가 page-level 명시 승인** + 근거(bbox ~1.54x 정합 risk). 이는 숨은 parenthetical 아닌 **Planner-visible DoD exception**: "chunk bbox sync" → "page-level sync + bbox-box best-effort". pixel 정밀은 후속.
- **.png-only validator가 .jpg figure 깨뜨림** → **accept (critical)**. MinerU figure는 .jpg. v2 validator는 **.jpg/.jpeg/.png 허용** + traversal 가드. test_v2_figure_image_allows_mineru_jpg_and_rejects_traversal.
- **jsdom skip-when-absent → 주 증거 불가** → **accept**. **Playwright가 authoritative viewer 테스트**(real KaTeX CSS/image/scroll/console). jsdom은 순수 함수만(있다면).

### 3. Edge cases
- **table chunk** → **accept**. doc7 챕터 table 0개지만 reflow는 table chunk를 graceful 렌더(escaped pre/markdown). drop/crash 금지. test_reflow_api_preserves_table_chunk_with_fallback.
- **bbox=[] / 누락** → **accept**. page-level sync는 page_idx(항상 존재) 사용. bbox는 선택적 오버레이만. bbox=[] → page-scroll only, JS 예외 0. test.
- **rotated pages** → **partial**. PyMuPDF 렌더가 rotation 반영. bbox 오버레이는 best-effort라 rotation 불일치 허용(page-level은 무관). 문서화.
- **긴 수식/혼합 overflow** → **accept**. display KaTeX `overflow-x:auto`(6i 패턴), 본문 `word-break:keep-all` + 긴 토큰 `overflow-wrap`.
- **image 누락 파일** → **accept**. 엔드포인트 controlled 404, reflow.html alt/placeholder fallback. test.

### 4. Alternative approaches
- **pure read-model + render-cache (Page 행 X)** → **accept** (§1과 동일).
- **two-tier sync 명시 (sync_mode per chunk)** → **accept**. reflow 응답에 per-chunk `bbox`(4-num 또는 null) 포함 → 프론트가 bbox 오버레이 가능 여부 판단. page sync는 항상, bbox 오버레이는 valid bbox일 때만.
- **Playwright authoritative** → **accept** (§2).

### 5. Missing tests — **전부 accept**
translated-rows-only fallback, table chunk fallback, mineru .jpg + traversal, page-image-requires-PDF(deterministic), bbox=[] page-scroll, **Playwright doc7 console-clean + KaTeX + figure + toggle**.

## Plan revisions (after debate)
1. **Page 행 안 만듦** — render-cache `data/extracts_v2/<doc>/pages/`, pages 테이블 무수정.
2. v2 image validator **.jpg/.jpeg/.png** 허용 + traversal.
3. 단일 reflow.js (분리 안 함).
4. Playwright authoritative viewer 테스트.
5. table graceful fallback, bbox=[] scroll-only, image 404 fallback.
6. per-chunk bbox(4-num|null) → two-tier sync.
7. source PDF 부재 시 deterministic 에러.
8. HT_LENS_DB_URL dev-DB 명시 계약 + verify chunks 선확인.

## DoD checklist
| DoD (ROADMAP 8c) | Status | Evidence |
| --- | --- | --- |
| doc7 챕터 reflow 읽기 자연스러움 | planned | reflow.html + 실 doc7 + Playwright + 사용자 확인 |
| 좌우 비교 hilight sync (chunk bbox) | planned (**Planner-approved exception → page-level**) | page sync 토글 + 클릭 스크롤; bbox-box best-effort |
| KaTeX 렌더 (6i 재사용) | planned | applyMath + vendor/katex; Playwright .katex count |

## Risk register
| Risk | L | I | Mitigation |
| --- | --- | --- | --- |
| .jpg validator 누락 | 중 | 높 | .jpg/.jpeg/.png + test |
| source PDF 부재 | 중 | 중 | deterministic 에러 + test |
| bbox 좌표 ~1.54x | 높 | 낮 | page-level sync (Planner 승인) |
| jsdom skip | 중 | 중 | Playwright authoritative |
| 1.x viewer 충돌 | 낮 | 높 | /v2/* + reflow.html URL 분리 |

## Decision
- [x] **PASS → proceed to code** (8 revisions 반영)
- [ ] RE-PLAN
