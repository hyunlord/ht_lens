# Phase 8c — Plan: Reflow Viewer (Chunk Reading View)

## Goal
chunk(8a) + 번역(8b)을 sandbox result_v2.html 품질의 reflow reading view로 렌더. 좌우 비교 토글. 1.x viewer 공존, KaTeX(6i) 재사용.

## Scope
**In**:
- chunk reading API `/v2/documents/{id}/reflow` (order_idx 순, type별 데이터)
- figure 이미지 서빙 `/v2/chunks/{id}/image`
- reflow viewer `reflow.html` + chunk render JS (heading/text/equation/image) + KaTeX(applyMath 재사용)
- 좌우 비교 토글 (좌: 원문 PDF page | 우: reflow), **page-level hilight sync**
- v2 doc의 page 이미지 렌더 (8a deferred Page 생성 — PyMuPDF, 좌측 pane용)
- doc7 챕터 working DB ingest+translate(8b mock) → 실 뷰
**Out**: chat/핀/RAG(8d), 실 qwen 번역·table·전체 7docs(8e), figure AI 설명(8d on-demand)

## Approach

### 0) Working DB (결정 A)
real data/ht_lens.db = 0004, chunks 없음, 1.x 데이터 보유. **prod 무손상 위해 별도 dev DB `data/ht_lens_v2.db`**(alembic head 0006, 빈 1.x 테이블 + doc7 chunks). 8c 서버/verify는 이 DB. prod 0004는 8e cutover까지 불변.

### 1) reflow API — `src/ht_lens/api/routers/reflow.py` (신규, prefix `/v2`)
- `GET /v2/documents/{doc_id}/reflow` → ReflowResponse: doc meta + chunks[order_idx]:
  {id, type, text_level, content, translated_text, caption_translated, img_path(→ /v2/chunks/{id}/image), page_idx, bbox}
  - text/heading: translated_text 우선, fallback content
  - equation: content(LaTeX, passthrough)
  - image: img_url + caption_translated
- `GET /v2/chunks/{id}/image` → FileResponse(chunk.img_path), traversal 가드(pages._validate_image_path 패턴 재사용), Cache-Control no-cache(6i 패턴)
- `GET /v2/documents/{doc_id}/page/{page_idx}/image` → 좌측 pane PDF page render PNG

### 2) v2 page render (8a Page 연기분 해소)
- ingest 시점 or serve 시점에 source PDF page → PNG (PyMuPDF, 1.x extract/render 재사용). v2 doc에 Page 행 생성(width/height/bg_image_path/pixel_* 채움 — non-null 충족). page_num = page_idx+chapter_offset.
- 좌측 pane는 이 PNG.

### 3) reflow.html + JS (sandbox seed)
- `src/ht_lens/api/static/reflow.html` (result_v2.html seed) + `js/reflow.js`(신규) + `js/components/chunk_render.js`
- 디자인: Pretendard/Noto CJK, max-width 760, line-height 1.9, 18px, heading 강조, display 수식 박스, figure-box(caption + EN footer)
- **KaTeX 재사용**: vendor/katex + render_markdown.applyMath (8b가 byte-identical $ 보존 → applyMath가 그대로 렌더). marked는 본문 markdown.
- chunk type별: heading→h2/h3(text_level), text→p+applyMath, equation→display 박스+applyMath, image→img+figure-box

### 4) 좌우 비교 (결정 B — page-level sync)
- 토글: 단일 reading(기본) | 좌우 비교
- 좌: page_idx별 원문 PNG(stacked), 우: reflow
- **page-level sync**: chunk 클릭 → 해당 page_idx 원문 PNG로 스크롤 + page 하이라이트. (bbox-box 오버레이는 best-effort: content_list bbox가 page_size pt의 ~1.54x 스케일 → 정합 근사; 픽셀 정확 sync는 8c 범위 외, 문서화)

### 5) 1.x 공존
- 신규 라우트 `/v2/*` + `reflow.html`. 1.x `/documents/*` + `viewer.html` 무수정. URL 분리(충돌 0).
- index.html에 reflow 진입점 링크 추가(선택).

## File-level changes
- `src/ht_lens/api/routers/reflow.py` (new), app.py include
- `src/ht_lens/api/static/reflow.html` (new, seed)
- `src/ht_lens/api/static/js/reflow.js` + `js/components/chunk_render.js` (new)
- `src/ht_lens/api/static/css/reflow.css` (new)
- v2 page render: `src/ht_lens/ingest_mineru/` 또는 reflow.py serve-time render helper
- prototype.py/prototype_reflow.html: 결정 D
- tests: test_reflow_api.py, test_reflow_viewer_js.py(jsdom), test_v2_page_render.py

## Dependencies (new)
없음 (PyMuPDF/KaTeX/marked 전부 기존).

## Test strategy
- test_reflow_api: chunk order_idx 순, type별 필드, image 서빙(traversal 가드), page render 서빙, 404.
- test_reflow_viewer_js (jsdom, Phase 6i 패턴): heading text_level 강조, equation/text KaTeX 렌더(8b $ 정합), figure-box caption, 좌우토글 DOM, pageerror 0.
- test_v2_page_render: Page 행 non-null 충족, PNG 생성.
- regression: 655 green, 1.x viewer/API 무손상.
- E2E(verify): working DB doc7 ingest+translate → reflow API + headless Playwright(KaTeX count, figure, 0 error) + 사용자 URL.

## DoD mapping (ROADMAP 8c)
- doc7 챕터 reflow 읽기 자연스러움(sandbox 품질): reflow.html + 실 doc7 + Playwright + 사용자 확인
- 좌우 비교 hilight sync(chunk bbox): page-level sync 토글 + 클릭 스크롤 (bbox-box best-effort)
- KaTeX 렌더(6i 재사용): applyMath + vendor/katex, test_reflow_viewer_js

## Plan 결정 항목 (확정 2026-05-30)
A. Working DB: ✅ **별도 dev `data/ht_lens_v2.db`** (alembic 0006 + doc7 ingest+translate). prod data/ht_lens.db(0004,1.x) 완전 불변. 8c 서버/verify=dev DB. 최종 topology는 8e.
B. 좌우 sync: ✅ **page-level** (chunk 클릭→원문 page 스크롤+하이라이트). bbox-box는 best-effort 근사+문서화. 픽셀 정밀은 후속(per-page scale factor).
C. viewer 파일명: ✅ **reflow.html**.
D. throwaway prototype: ✅ **제거** (prototype.py + prototype_reflow.html + app.py include). chunk reflow가 대체, 8e에 block 사라짐.

## 위험/완화
- bbox 좌표 ~1.54x 스케일 → 픽셀 sync 어려움 → page-level sync(B). bbox-box는 근사+문서화.
- v2 doc Page 미존재(8a) → 8c에서 PyMuPDF render로 생성(non-null 충족).
- KaTeX $ 정합 → 8b byte-identical 보존 검증됨 + test_reflow_viewer_js로 잠금.
- 긴 챕터 성능 → reflow는 단순 DOM, lazy img loading.
