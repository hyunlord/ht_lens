# Phase 8e-4 — Challenge

Codex가 핵심 2개를 잡음: (1) **IntersectionObserver는 jsdom서 검증 불가**(§2.7) + root=`#content` 오류(§2.4, 실 scroll=`.pane--reflow`), (2) dedup 가정 위험(captionless 정상 figure, malformed bbox, equal bbox). 둘 다 accept → **IO 폐기, throttled scroll-handler + page-offset 이진탐색**(결정적·jsdom 테스트 가능, §4.2) + dedup 엄격화. **PASS with revisions**.

## Debate responses
### 1. Over-engineering
- **accept (IO→scroll-handler, page sentinel)**: 3338 chunk observe 대신 **page 경계(각 page 첫 chunk)만** offset 추적 + `.pane--reflow` throttled scroll → 현재 page 이진탐색. 관찰 대상=page 수. (§1.1/§4.1)
- **accept (루프 가드 제거)**: 우→좌 단방향, left→right 경로 없음 → safety flag/loop 테스트 폐기. last-page 캐시(중복 scroll 방지)만 유지. (§1.2)
- **accept (dedup 좁게)**: helper명 `_drop_captionless_images_contained_by_captioned`. image-only·same-page·**captioned가 captionless를 strict 포함**만. 일반 layout 수리 엔진 아님. (§1.3/§4.4)

### 2. Hidden assumptions
- **accept (CRITICAL, scroll 컨테이너)**: `paneReflow=$("content")`=article. 실 scroll=`.pane--reflow`(부모, overflow:auto). scroll 리스너+offset 기준 = **`.pane--reflow`**. (§2.4)
- **accept (CRITICAL, IO 미검증)**: jsdom은 layout/IO 없음 → IO 폐기. scroll-handler의 **순수 선택 함수**(`pickCurrentPage(boundaries, scrollTop)` 이진탐색)를 synthetic offset으로 단위 테스트. (§2.7)
- **accept (caption 가정 위험)**: captionless가 **captioned에 포함될 때만** 드롭. standalone captionless figure(비포함)는 유지. (§2.5)
- **accept (bbox 좌표/malformed)**: bbox None/len≠4/NaN/inverted(x1<x0,y1<y0) → **드롭 안 함**(skip). 동일 좌표계 가정 실패 시 안전. (§2.6/§3.12)

### 3. Edge cases
- **accept (현재 chunk 결정성)**: 다중 교차/tall chunk 모호 → scroll-handler가 **page 경계 offset 이진탐색**으로 "scrollTop 이하 최대 offset page" 결정. IO entry 정렬 불요. (§3.8/§3.9)
- **accept (mode 토글 즉시 sync)**: single→compare 전환 시 **즉시** 현재 page sync(다음 scroll 이벤트 대기 X). (§3.10)
- **accept (reload disconnect)**: `load()` 재호출 시 이전 핸들러/offset 리셋(stale 방지). (§5.4)
- **accept (equal bbox)**: `contains`=**strict**(a가 b를 enclose ∧ a.area > b.area). equal bbox는 nested 아님 → **유지**(테스트 잠금). Fig28.18 panel은 strict 작음. (§3.12)
- **accept (captionless standalone)**: 포함하는 captioned 없으면 유지. (§3.11)

### 4. Alternative approaches
- **accept (scroll-handler)**: throttled `.pane--reflow` scroll + precomputed page offset 이진탐색 → 결정적·테스트 용이(§4.2). IO 폐기.
- **accept (ReflowChunk 후 필터)**: dedup을 ORM Chunk 대신 **`ReflowChunk` 구성 후** 적용 — 이미 파싱된 `bbox`(`_bbox_or_none`) 재사용, bbox 파싱 중복 회피. (§4.3)
- **accept (helper 명명)**: `_drop_captionless_images_contained_by_captioned`. (§4.4)

### 5. Missing tests — 채택(scroll-handler 적응)
1. `pickCurrentPage`가 `.pane--reflow` 기준 offset 이진탐색(다중 page서 topmost). (§5.1/5.2 적응)
2. mode single→compare 즉시 현재 page sync. (§5.3)
3. reload 후 이전 boundary가 새 좌측 못 건드림(리셋). (§5.4)
4. dedup: standalone captionless(비포함) 유지. (§5.5)
5. dedup: malformed/inverted/None bbox → 드롭 0. (§5.6)
6. dedup: equal bbox captioned/captionless → 유지(strict). (§5.7)
7. dedup: panel 숨겨도 DB 무변경 → `/v2/chunks/{id}/image`·chat 정상. (§5.8, 비파괴 검증)
8. dedup: doc1 page2(30 CAP ⊃ 27/28/29 nocap) → 27/28/29 drop, 30 유지; page4 side-by-side 유지.

## Plan revisions
- **A-R1** IO 폐기 → **throttled scroll-handler(`.pane--reflow`) + page-boundary offset 이진탐색**(`pickCurrentPage` 순수 함수, jsdom 테스트).
- **A-R2** scroll/offset 기준 = `.pane--reflow`(article 아님).
- **A-R3** 루프 flag/테스트 제거(우→좌 단방향), last-page 캐시만.
- **A-R4** 결정적 현재 page = scrollTop 이하 최대 boundary offset.
- **A-R5** single→compare 토글 즉시 현재 page sync.
- **A-R6** reload 시 리셋(stale 방지).
- **B-R1** `_drop_captionless_images_contained_by_captioned`(좁게, image·same-page).
- **B-R2** strict 포함(area>) + malformed/inverted/None bbox skip(드롭 0).
- **B-R3** captionless는 **captioned에 포함될 때만** 드롭(standalone 유지).
- **B-R4** equal bbox 유지(strict). **B-R5** `ReflowChunk` 후 필터(파싱 bbox 재사용). **B-R6** 비파괴(DB·chat·image 무영향).

## DoD checklist
| DoD | Status | Evidence |
| --- | ------ | -------- |
| 비교 좌우 추종 | 계획 | scroll-handler 우→좌 + `pickCurrentPage` 단위 + 라이브 doc1 |
| Fig28.18 중복 제거 | 계획 | strict containment 필터 + doc1 단위(27/28/29 drop) |
| 정상 figure 보존 | 계획 | side-by-side·standalone·equal·malformed 유지 단위 |
| 읽기 모드 무영향 | 계획 | compare-only sync jsdom |
| 비파괴(DB/chat) | 계획 | /chunks/{id}/image·chat 정상(§5.8) |
| 1.x 무손상 | 계획 | frontend/render만, DB 0 |

## Risk register
| Risk | L | I | Mitigation |
| ---- | - | - | ---------- |
| IO jsdom 미검증 | (해소) | — | scroll-handler 순수 함수 단위 테스트 |
| scroll 컨테이너 오류 | (해소) | 고 | `.pane--reflow` 기준 |
| dedup 정상 figure 오삭제 | 중 | 고 | strict 포함+caption 비대칭+포함시만+malformed skip+테스트 |
| equal bbox 모호 | 저 | 중 | strict(>)로 유지, 테스트 잠금 |
| 3338 chunk 성능 | 저 | 중 | page 경계만 추적 + throttle |
| 1.x | 저 | 고 | DB/migration 0, 비파괴 |

## Decision
- [x] **PASS → proceed to code** (A-R1~6, B-R1~6). IO→scroll-handler(테스트 가능·결정적), dedup 엄격화(strict·malformed·포함시만·비파괴). RE-PLAN 불요(설계 핵심 유지, 하드닝).
- [ ] RE-PLAN
