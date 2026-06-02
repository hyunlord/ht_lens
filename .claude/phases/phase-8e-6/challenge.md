# Phase 8e-6 — Challenge

Codex가 일관된 방향으로 수렴: **F2를 대폭 단순화** — (1) `overrides.candidates.json`(2차 manifest) 폐기, (2) caption **자동 할당** 폐기, (3) ingest 훅 폐기. 대신 **읽기 전용 `detect-repairs` CLI**가 *리포트 + 초안 seed*를 내고, **`repair_seeds/*.json`이 source-of-truth, `repair-images`가 유일한 overrides 작성자**(8e-5/F1 계약 유지). 대부분 accept → **PASS with revisions(스코프 축소)**. 목표(book2 위해 repair 발견 자동화) 유지, 접근을 seed-중심으로 경량화.

## Debate responses
### 1. Over-engineering
- **accept (2차 manifest 폐기)**: `overrides.candidates.json` 제거. `detect-repairs`는 **리포트(JSON/stdout) + 초안 `repair_seeds/<doc>.json`**만 생성. 사람이 seed 편집 → 기존 `repair-images --seed --apply`가 유일하게 `overrides.json` 작성. (state lifecycle 1개 유지, stale 검증 표면 최소.)
- **accept (caption 자동 할당 폐기)**: F2는 caption 오배치를 **결정적 리포트**로만 — 같은 페이지 image chunk 목록 + bbox + 썸네일 경로 + 현재 caption + 의심 병합캡션 텍스트. **라벨↔이미지 할당은 사람이 seed에 직접 작성**(브리틀 spatial 휴리스틱을 코드에 넣지 않음). book2 수동 부담은 "수십 페이지 전수 육안" → "리포트가 의심 페이지만 추려줌"으로 경감.
- **accept (ingest 훅 폐기)**: `ingest_mineru_output()` 원자성 비오염. **분리 CLI `detect-repairs`**(읽기 전용)로. ingest 트랜잭션 무관.
- **accept (이미지 자동화만 강함)**: defect-1(열화)은 `detect-repairs`가 검출 + 초안 seed `image_allowlist` 채움 + 미리보기 클립 생성 → 사람 확인 → `repair-images --apply`. defect-2(caption)은 리포트까지만.

### 2. Hidden assumptions
- **accept (origin.pdf 발견 불안정)**: `detect-repairs`에 **명시적 `--pdf` 우선**, `markdown_path` 자동발견은 편의 fallback. `markdown_path` None/오류 시 **loud fail(exit 2)**, 빈 리포트 금지.
- **accept (bbox 1000-정규화 가정)**: malformed/`[]`/inverted bbox는 `normalized_bbox_to_page_rect`가 None → **리포트에 invalid bbox 카운트 명시 + skip_reason**. "자동 페이지-클립" DoD = 클립 가능분 + skip 명시 보고(은폐 금지).
- **accept (>0.6 임계 신규 doc)**: book2 dark 그림/heatmap/inverted FP 가능 → **육안 게이트 필수**(자동 serving 0). 추가로 **리뷰 과부하** 우려 → 리포트에 black_frac 값·미리보기 동봉해 사람 판정 비용↓.
- **accept (caption 문법 다양)**: `(a)/(b)`, `Figure 1(a)`, 전각 괄호, `(a)-(c)`, `(i)/(ii)`, 본문 prose 내 `(a)` 등 → **지원 문법 명시 + 미지원은 리포트에 "unmatched"로 표기, 후보 0**(오탐 금지). 자동 할당 안 하므로 파싱 실패가 잘못된 교정으로 이어지지 않음.

### 3. Edge cases
- **accept (same-basename same-page 충돌)**: 미리보기/클립 파일명에 **chunk order_idx(또는 안정 해시) 포함**해 page+basename 동일 시도 구분. 단위 테스트.
- **accept (rotated skip 보고)**: `clip_render_figure` rotation skip → **리포트에 skip_reason='rotated'** 명시, 조용한 미복구 금지. CLI 경고/비0 종료 옵션.
- **accept (dedup 상호작용)**: caption 부여가 `_drop_captionless_images_contained_by_captioned` 판정 바꿀 수 있음(8e-4) → caption 후보가 **nested(서빙서 드롭될) 이미지면 리포트서 제외/표기**(무의미 리뷰 방지). 테스트.
- **accept (reingest stale 후보)**: 초안 seed는 안정 evidence(page_idx+basename+bbox) 기반 → `repair-images` 적용 시 기존 stale-safe 매칭이 dead 후보 거부. 추가 테스트로 잠금.

### 4. Alternative approaches
- **accept (audit-only CLI)**: `ht-lens detect-repairs --doc-id [--pdf]` = 머신 리포트 + 초안 seed. `repair-images --seed --apply`만 overrides 작성. (seed-as-source-of-truth 계약 보존.)
- **accept (caption 결정적 리포트 > 제안)**: 썸네일·bbox·현재 caption·의심 병합텍스트 나열, 사람이 seed 편집.
- **accept (origin 발견 = --pdf 우선)**.
- **accept (C′ fragile fallback = seed에 origin_pdf_path/sha 기록, migration 아님)**: page-size 컬럼/migration 0008 **불요**. 보존 우려는 seed의 PDF 경로 메타로 해소.

### 5. Missing tests — 채택
1. `detect-repairs` origin.pdf 없음/`markdown_path` None → **exit 2 loud**(빈 리포트 금지).
2. `overrides.candidates.json` 폐기 → 대신 **초안 seed/리포트가 reflow·chunk_image 서빙에 무영향**(별도 파일).
3. reingest 후 stale 후보 → `repair-images` 승격 거부(기존 stale-safe).
4. caption 오배치: text-chunk 캡션 → 의도적 탐지 or "unsupported, 후보 0" 문서화.
5. caption: 본문 prose 내 `(a)(b)` → **오탐 0**.
6. 미리보기 same-basename same-page → 파일명 충돌 0.
7. rotated 페이지 열화 → 리포트 skip_reason 명시(조용한 누락 금지).

## Plan revisions (after debate)
- **R1** `overrides.candidates.json`(2차 manifest) **폐기**. `detect-repairs` = 읽기전용 리포트 + 초안 `repair_seeds/<doc>.json`. `repair-images`가 유일 overrides 작성자.
- **R2** caption: **자동 할당 폐기**. 리포트(썸네일/bbox/caption/병합텍스트)만 → 사람이 seed 편집. 지원 문법 명시 + unmatched 표기.
- **R3** ingest 훅 폐기 → **분리 CLI**(읽기전용, ingest 원자성 무관).
- **R4** origin.pdf: **`--pdf` 우선** + markdown 자동발견 편의; 없으면 exit 2 loud. C′ 유지(migration 0). fragile 시 seed에 origin_pdf 경로 기록(migration 아님).
- **R5** 리포트에 invalid-bbox/ rotated skip_reason/ black_frac/ dedup-drop 예정 **명시**(은폐 금지).
- **R6** 미리보기 파일명 = page+order_idx(or hash)로 충돌 방지.
- **R7** DoD "자동 페이지-클립" = detect→초안 seed(image_allowlist)+미리보기 → 게이트 → `repair-images --apply`(기존). caption은 리포트까지.

## DoD checklist (revised)
| DoD | Status | Evidence |
| --- | ------ | -------- |
| 열화 자동 검출(>0.6), 3/3 재검출 FP 0 | 계획 | `detect-repairs` doc1 → 3 후보; 5-doc FP 0 |
| 초안 seed + 미리보기 → 게이트 | 계획 | 리포트/seed 생성, 서빙 무영향 테스트 |
| 자동 페이지-클립(C′, migration 0) | 계획 | origin.pdf page.rect; invalid/rotated skip 보고 |
| caption 오배치 **리포트**(할당 X) | 계획 | doc5 4페이지 재탐지 리포트; prose 오탐 0 |
| 기존 doc1/doc5 manifest 불변 | 계획 | 재생성 동일 회귀 |
| origin.pdf 없음 loud fail | 계획 | exit 2 테스트 |
| additive(migration 0, 1.x 무손상) | 계획 | schema diff 0 |
| CI green | 계획 | jsdom+pytest+mypy+ruff |

## Risk register
| Risk | L | I | Mitigation |
| ---- | - | - | ---------- |
| 검출기 신규 doc FP/리뷰 과부하 | 중 | 중 | 육안 게이트 + 리포트에 black_frac·미리보기(판정 비용↓) |
| caption 할당 해석 오류 | (해소) | — | 자동 할당 폐기, 리포트만, 사람 seed 편집 |
| origin.pdf 발견 실패 | 중 | 중 | --pdf 우선 + loud fail(exit 2) |
| reingest stale 후보 | 저 | 중 | 안정 evidence 매칭 + 거부 테스트 |
| 기존 manifest 회귀 | 저 | 고 | doc1/doc5 재생성 동일 테스트 |
| dedup 상호작용 | 저 | 중 | nested-drop 예정 후보 리포트 제외/표기 |
| 1.x | 저 | 고 | schema 0, 서빙 무변경, 읽기전용 CLI |

## Decision
- [x] **PASS with revisions → (단, 구현은 GATE 2 Planner 승인 후)**. R1~R7로 스코프를 seed-중심 audit CLI로 축소. 목표(book2 repair 발견 자동화) 유지. RE-PLAN 불요(핵심 유지·경량화).
- [ ] RE-PLAN

## Planner 결정 (GATE 2)
debate가 plan의 4개 open decision을 다음으로 수렴 — 승인 요청:
1. **caption: opt-2 강화(리포트만, 자동 할당 X)** ← debate 권고(원 plan의 "탐지+제안"보다 더 축소). OK?
2. **좌표: C′(migration 0)**, fragile 시 seed에 origin_pdf 기록. OK?
3. **검출 위치: 분리 CLI `detect-repairs`**(ingest 훅 X). OK?
4. **게이트: 초안 seed + 미리보기 → 사람 편집 → `repair-images --apply`**(2차 manifest 없음). OK?
