# Phase 8e-5 — Challenge

Codex가 핵심을 정확히 잡음: (1) **broad detector → allowlist**(확정 3건만), (2) **hard-coded API 규칙/basename override → 안정 증거 keyed manifest**, (3) **cached PNG 크롭 → 소스 PDF 직접 clip-render**(rotation/cropbox/DPI 견고), (4) 1000-정규화는 contract 아님 → **per-page 검증**, (5) Stage A는 일반 스캐너가 아니라 **bounded audit + 알려진 교정셋**, (6) caption 교정이 8e-4 dedup(page4)과 상호작용. 대부분 accept → **PASS with revisions**(목표 불변, 접근 경화).

## Debate responses
### 1. Over-engineering
- **accept (broad detector → allowlist)**: 이 phase는 **확정 3건(ch1/84/85) 명시 교정**. `black_bg_fraction`은 후보 manifest **생성용 audit 보조**로만, 최종 교정셋은 사람-검토된 allowlist. 일반 검출 서빙 경로 미투입.
- **accept (Stage A 축소)**: 전 docs 일반 휴리스틱 스캐너 defer. Stage A = **content_list 인접성 audit 리포트 + ch53/ch54 알려진 교정**만. 패턴 정량화는 보조 집계로 첨부하되 fix 로직 아님.
- **accept (로직 위치)**: `black_bg`/크롭/backfill = **`scripts/` 또는 별도 모듈**(API 라우터 아님). 라우터는 **manifest 조회만**.
- **accept (육안 게이트 → manifest-first dry-run)**: 비대화형 워크플로우 호환. backfill `--dry-run`(변경 예정 manifest 작성, 이미지 미기록) → 사람이 **manifest 아티팩트 검토** → `--apply`(검토된 항목만 기록). 대화형 일시정지 없음.
- **accept (render-time hard-coded 교정 → manifest)**: `(doc,chunk)→caption` API 조건문 금지. **manifest 기반**(안정 증거 keyed) 교정.

### 2. Hidden assumptions
- **accept (1000-정규화 비-contract)**: blind 가정 금지. backfill 시 **per (doc,page) 검증** — `bbox/1000 × page_size(소스 PDF page.rect) ∈ page 사각형` 확인, 실패 시 skip+log. manifest에 **해소된 page-point bbox + 증거** 저장 → serve-time 재계산 없음.
- **accept (page 렌더 기하 가정)**: cached PNG 대신 **소스 PDF 직접 clip-render**(아래 §4)로 cropbox/DPI/page_idx drift 회피.
- **accept (basename 충돌/문서 간 override)**: override는 **(doc_id, page_idx, 원본 basename, bbox) 복합 키 manifest**로 — basename 단독 존재 매칭 금지. 같은 doc 범위로 스코프.
- **accept (stale override)**: manifest 항목에 **원본 img_path basename + bbox(+선택 hash)** 증거 포함 → 현 chunk와 불일치 시 override 미적용. 재ingest 후 자동 무효.
- **accept (chunk id 불안정)**: hard-coded `chunks.id` 금지. manifest는 **page_idx + 원본 basename + bbox**(재현 가능 증거)로 매칭.
- **accept (docs 6-7 범위 명시)**: ROADMAP 8e=7 docs이나, 8e 킥오프 결정으로 **book2 full defer, 챕터(doc1=book2_ch28)만** 마이그레이션 → 현 2.0 표면 = **5 docs (papers×3 + aggarwal + book2_ch28)**. "정상 158 무회귀"는 이 5-doc 표면 전체. summary에 명시.

### 3. Edge cases
- **accept (inverted/degenerate bbox)**: `page_crop_box`가 `x1<=x0 ∨ y1<=y0` → None(skip). 단위 테스트.
- **accept (정규화 경미 이탈)**: ε 정의(예: [-5, 1005] 허용 후 clamp; 그 밖 skip). clamp는 page 사각형으로.
- **accept (rotation)**: 소스 페이지 `page.rotation≠0`이면 **clip 좌표 변환 적용 또는 skip+log**(silent crop 금지). 기존 `test_rotated_page.py` 패턴으로 잠금.
- **accept (검출기 한계)**: 흰 배경 벡터 단편 miss / 검은 배경 정상(차트·현미경) FP 가능 → **그래서 allowlist + manifest 검토 게이트**. 검출기는 후보 제시만.
- **accept (caption 파싱 한계)**: `(a) Figure 28.20`, `Fig.`, 다중 참조, 멀티라인 → Stage A audit는 best-effort, **교정은 검토된 manifest 항목만**(파서 신뢰에 의존 안 함).
- **accept (CRITICAL: caption 교정 × dedup 상호작용)**: caption을 ch54→ch53로 옮기면 page4의 "captioned" 판정이 바뀌어 `_drop_captionless_images_contained_by_captioned` 동작 변동 가능 → **명시 테스트**(교정 후 page4 image 드롭/중복 없음). 적용 순서(교정→dedup) 의도적 고정.
- **accept (media type 일관성)**: 소스 PDF clip 산출 PNG를 `.png` basename으로 저장 → `chunk_image`가 served path suffix로 media type 결정(기존 `_MEDIA`). 원본 `.jpg`↔override `.png` 불일치 테스트.

### 4. Alternative approaches
- **accept (manifest)**: `data/extracts_v2/<doc>/overrides.json` — `image_overrides`(원본 basename/page_idx/bbox → fixed 파일) + `caption_overrides`(page_idx/basename → 교정 caption). `chunk_image`·`get_reflow`가 조회. 감사 가능·재ingest 안전.
- **accept (PyMuPDF 직접 clip)**: `page.get_pixmap(clip=Rect)` — 정규화 bbox → page-point 변환(`bbox/1000 × page.rect`) 후 고DPI clip. cached PNG 크롭(검증된 fallback)보다 고품질·결정적. 소스 PDF = MinerU 출력의 `*_origin.pdf`(doc1: `doc7_chapter_990-1000_origin.pdf`) 사용.
- **accept (allowlist backfill)**: 확정 3건만 복구 + 다른 것 무변경 검증. 일반 검출은 docs 6-7·더 많은 dark-negative 확보 후 별도 audit 도구.
- **accept (caption 교정 위치)**: 지속 fix는 ingest/`content_list.py` 또는 재ingest-side manifest 쪽. 이 phase는 **manifest(비파괴)**; ingest 통합은 후속.

### 5. Missing tests — 채택
1. `page_crop_box` inverted/degenerate(`[10,10,5,20]`,`[10,10,10,20]`,`[10,10,20,10]`) → None.
2. rotated-page: clip 좌표 미적용 silent crop 금지(기존 fixture).
3. fixed override가 **같은 doc 범위**로 한정(타 doc basename 미적용).
4. override 경로 traversal/비-이미지 suffix 거부(신규 경로 구성).
5. stale override: manifest 증거(원본 basename/bbox) 불일치 시 미적용.
6. caption 교정 × dedup(ch53/54/55 page4) — 드롭/중복 없음, 순서 의도.
7. caption 스캔 subfigure prefix(`(b) Figure 28.20`)·`Fig.` 약어.
8. backfill `--dry-run` 미기록 / `--apply`는 검출·allowlist 항목만 기록.
9. 5-doc 범위 명시(`docs 6-7 제외 사유` 또는 라이브 5-doc 무회귀).

## Plan revisions (after debate)
- **R1** broad detector → **allowlist(ch1/84/85, 안정 증거로 식별)**; `black_bg`는 audit 보조.
- **R2** 교정 = **manifest**(`overrides.json`, 복합 키 안정 증거) — hard-coded chunk id / basename-단독 / API 조건문 금지.
- **R3** 복구 = **소스 PDF(`*_origin.pdf`) PyMuPDF clip-render**(정규화 bbox→page.rect 변환). cached PNG 크롭은 fallback.
- **R4** **per (doc,page) 1000-정규화 검증**(bbox/1000×page_size ∈ page rect), 실패 skip+log. rotation≠0 skip/변환+log. inverted/degenerate skip.
- **R5** backfill/검출/크롭 로직 **`scripts/` 또는 모듈**; 라우터는 manifest 조회만. `--dry-run/--apply`(manifest-first, 비대화형).
- **R6** caption 교정 manifest를 `get_reflow`에서 적용 + **dedup 상호작용 테스트**(page4). 적용 순서 고정.
- **R7** Stage A = bounded audit 리포트 + ch53/ch54 교정셋(일반 스캐너 defer).
- **R8** 범위 = **5-doc(현 2.0 표면)** 명시, docs 6-7(book2 full) defer 사유 summary 기재.

## DoD checklist
| DoD | Status | Evidence |
| --- | ------ | -------- |
| ch54 진단(단발/패턴) | 계획 | Stage A audit 리포트 + content_list 인접성 |
| 좌표 유틸(스키마 0) | 계획 | `bbox/1000×page.rect` + per-page 검증, 단위 |
| 복구셋 allowlist(3건) | 계획 | manifest(안정 증거), audit black_bg 보조 |
| ch1/84/85 PDF clip 복구 | 계획 | 라이브 reflow 우측 = 완전 다이어그램 |
| ch54 caption 교정 | 계획 | manifest + reflow 응답 정합 + dedup 무영향 |
| 정상(5-doc) 무회귀 | 계획 | 라이브 `/image` 200 + 육안 샘플 |
| rotation/edge 안전 | 계획 | inverted/rotated/traversal/stale 단위 |
| CI green | 계획 | jsdom+pytest+mypy+ruff push 후 |
| 1.x/prod 무손상·롤백 | 계획 | DB 변경 0; manifest/파일 삭제로 롤백 |

## Risk register
| Risk | L | I | Mitigation |
| ---- | - | - | ---------- |
| 1000-정규화 미성립 | 중 | 고 | per-page 검증(page.rect 대조)+skip/log; manifest에 해소 bbox 저장 |
| rotation/cropbox 오크롭 | 중 | 고 | page.rotation 변환/skip+log, rotated fixture 테스트 |
| basename 충돌/stale override | 중 | 고 | 복합 키 manifest(page_idx+basename+bbox), 불일치 미적용 |
| caption 교정이 dedup 깨뜨림 | 중 | 중 | page4 상호작용 테스트, 순서 고정, manifest 한정 |
| 검출기 FP/FN | 중 | 중 | allowlist + manifest 사람 검토 게이트(서빙 자동검출 아님) |
| 소스 PDF 부재 | 저 | 중 | MinerU `*_origin.pdf` 사용; 없으면 cached PNG 크롭 fallback |
| 1.x/prod | 저 | 고 | main 분기, 추가파일+manifest만, DB/migration 0, 디렉토리 삭제 롤백 |

## Decision
- [x] **PASS → proceed to code** (R1~R8). 목표(열화 복구 + caption 교정) 불변, 접근을 allowlist+manifest+PDF-clip+per-page 검증으로 경화. RE-PLAN 불요.
- [ ] RE-PLAN
