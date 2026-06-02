# Phase 8e-4 — Plan (scroll-sync + nested image dedup) — 비교 모드 완성

## Context
v2.0 cutover(main `b712a17`, CI green) + docs 2-5 page render backfill 완료. 비교 모드 잔여 2문제(진단 확정) 수정. main에서 분기(`phase-8e-4`) → PR/머지(CI on main/PR).

## Goal
(A) 비교 모드 **scroll-sync**: 우측 reflow 스크롤 → 좌측 PDF page 자동 추종(IntersectionObserver, 우측→좌측, 비교 모드 한정). (B) **nested image dedup**: MinerU가 multi-panel figure를 panel 크롭 + 전체 크롭으로 중복 추출 → caption 있는 전체만, caption 없는 nested panel 드롭(render 필터, 비파괴).

## Stage 0 실측 (확정)
- (A) `reflow.js`: chunk el에 `dataset.pageIdx`/`chunkId`. `buildPdfPane`=distinct page당 `.pdf-page[data-page-idx]`. `syncToChunk(el)`=비교 모드면 좌측 page로 scrollIntoView — **chunk 클릭 시에만**(`el.onclick`). **IntersectionObserver/scroll 리스너 0** → 연속 sync 없음.
- (B) doc1 page2 Figure 28.18: chunk30(**CAP**, [156,84,855,475])이 27/28/29(**nocap** panel)를 bbox 포함 → 4개 다 렌더 = 중복. **전수: doc1만 nested 3개(panel)**, docs 2-5는 0(단일 크롭). 같은 doc page4(53 nocap + 54/55 CAP)는 **side-by-side 별 figure**(비포함) → 건드리면 안 됨.
- `get_reflow`(reflow.py)가 order_idx 순 전 chunk → `ReflowChunk`(bbox/caption/type/page_idx 보유). render-filter 위치.
- 컬럼: `caption`(image_caption 아님). baseline reflow 테스트 green.

## 사용자 결정 (확정, prompt 모호하면)
- scroll-sync = **우측→좌측만**(읽기 흐름; 양방향 무한루프 회피).
- dedup = **render 필터**(비파괴, DB 보존; ingest 재마이그레이션 X).
- containment = **완전 포함만**(부분 겹침 X) — page4 side-by-side 오판 방지.
- pixel-perfect bbox overlay = **defer**(page-level 유지, 별도).

## Scope
**In (8e-4)**
- **A. scroll-sync**(frontend `reflow.js`): IntersectionObserver로 우측 chunk 가시성 추적 → 현재(상단) chunk의 page_idx 변화 시 좌측 `.pdf-page` scrollIntoView. **비교 모드일 때만** 활성(읽기 모드 no-op). 좌측 scroll은 우측 observer 미트리거(다른 컨테이너)라 루프 없음 + 안전 flag. jsdom 테스트.
- **B. nested dedup**(backend `reflow.py` render 필터): `_drop_nested_panel_images(chunks)` — 같은 page에서 image A(caption 있음)가 image B(caption 없음)를 **완전 포함**하면 B 드롭. `get_reflow` 응답 구성 전 적용. **DB 무변경**(비파괴). 일반 로직(doc 무관; nested 있는 곳만 작동). 단위 테스트.

**Out**
- ingest 재마이그레이션/DB 변경(render 필터로). pixel-perfect bbox overlay(defer). 양방향 sync(우→좌만). 1.x. 8f.

## Approach
### A. scroll-sync (reflow.js)
- `load()`서 chunk append 후 `initCompareSync(paneReflow, panePdf, layout)` 호출.
- IntersectionObserver(root=paneReflow, rootMargin top-biased 예: `"0px 0px -70% 0px"`, threshold 0): 상단 교차 chunk = 현재. 현재 chunk의 `pageIdx`가 직전과 다르면 → 좌측 `.pdf-page[data-page-idx=idx]` scrollIntoView(block:nearest, behavior:smooth).
- `layout.dataset.mode==='compare'` 아니면 scroll skip(observer는 유지/또는 mode 토글 시 connect/disconnect). 마지막 동기 page 캐시(중복 scroll 방지).
- 기존 click `syncToChunk` 유지(클릭 점프). observer는 연속 추종 추가.
- 성능: Aggarwal 3338 chunk observe — IO는 네이티브 효율적; 필요시 chunk만(이미지/heading 경계) 관찰 축소 검토.

### B. nested dedup (reflow.py)
- helper: image chunks를 page별 그룹 → 각 page에서 (A.caption truthy) ∧ (B.caption falsy) ∧ `contains(A.bbox, B.bbox, tol)` → B.id drop set. bbox None은 skip.
- `contains(a,b)`: `a.x0<=b.x0 ∧ a.y0<=b.y0 ∧ a.x1>=b.x1 ∧ a.y1>=b.y1` (tol 소량) ∧ a!=b. 완전 포함만.
- `get_reflow`: chunks 빌드 시 drop set 제외. order_idx 순서 보존.

## File-level changes (예상)
| Path | Action | Note |
| ---- | ------ | ---- |
| `src/ht_lens/api/static/js/reflow.js` | 수정 | initCompareSync(IntersectionObserver) |
| `src/ht_lens/api/routers/reflow.py` | 수정 | `_drop_nested_panel_images` + get_reflow 적용 |
| `tests/integration/test_reflow_*_js.py` | 신규/수정 | scroll-sync jsdom(compare-only, page 추종, 루프 없음) |
| `tests/integration/test_reflow_api.py` 등 | 신규 | dedup(포함→드롭, side-by-side 보존, caption 규칙, bbox None) |

## Dependencies (new)
| Package | Why |
| ------- | --- |
| (없음) | IntersectionObserver=브라우저 네이티브, dedup=순수 파이썬 |

## Test strategy
- **dedup 단위**: doc1 page2 모사(30 CAP contains 27/28/29 nocap) → 27/28/29 drop, 30 유지. page4 모사(side-by-side, 비포함) → 전부 유지. caption 있는 것끼리/없는 것끼리 비포함 → 유지. bbox None → skip(드롭 안 함). order 보존.
- **scroll-sync jsdom**: 비교 모드서 chunk 가시성 변경(page_idx 바뀜) → 좌측 page scrollIntoView 호출. 읽기 모드 → 호출 안 함. 같은 page 연속 → 중복 scroll 없음. 좌측 scroll이 우측 observer 미트리거(루프 없음).
- **회귀**: 782 + 신규. ruff/format/mypy clean. 1.x blocks 49850.

## DoD mapping
| DoD item | How | Evidence |
| --- | --- | --- |
| 비교 모드 좌우 추종 | IntersectionObserver 우→좌 | jsdom + 라이브 doc1 스크롤 |
| Figure 28.18 중복 제거 | bbox-containment render 필터 | doc1 reflow image 15→12(표시) + 단위 |
| 정상 figure 보존 | 완전 포함만 | page4 side-by-side 유지 단위 |
| 읽기 모드 무영향 | compare-only sync | jsdom |
| 1.x 무손상 | frontend/render만, DB 무변경 | blocks 49850 |

## 위험 / 완화
- **scroll-sync 무한루프** → 우→좌 단방향 + 좌측은 별 컨테이너(우측 observer 미트리거) + last-page 캐시 + 안전 flag.
- **dedup 오판(정상 인접 figure)** → **완전 포함만**(부분 겹침 X) + caption 비대칭(CAP가 nocap 포함) 조건. page4 side-by-side 테스트로 잠금.
- **IO 성능(3338 chunk)** → 네이티브 효율; 필요시 관찰 대상 축소. rootMargin로 단일 현재 chunk만.
- **읽기 모드 sync 켜짐** → mode 가드(compare만 scroll).
- **render 필터가 chat/embedding 영향** → 비파괴(DB 유지); panel은 caption 없어 미임베딩, figure context는 caption 있는 전체 사용 → 무영향.
- **1.x** → main 분기, frontend+reflow render만, DB/migration 0.

## 결정 필요 (해결됨)
- 우→좌(확정), render 필터(확정), 완전 포함(확정), pixel defer(확정).
