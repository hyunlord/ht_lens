# Phase 8e-5 — Plan (Image 서빙 품질 정리: 페이지-크롭 + caption 매핑)

Versioning: v2.0-e5 · main에서 분기(`phase-8e-5`) → PR/머지(CI on main/PR).

## Context
8e-4(scroll-sync + dedup) 후 doc1(Murphy PML ch28)에서 **독립된 image 결함 2종** 진단 확정(둘 다 MinerU 추출 단계, 메커니즘 다름). prod 유지, 1.x DB(0004) 불변, 2.0 DB(0007).

## Goal
(1) **검은 배경 다이어그램 열화** 복구 — MinerU가 벡터 PGM 다이어그램을 노드 원 blob만 캡처(화살표·라벨·타원 누락). 페이지-렌더 bbox 크롭으로 완전 복구. (2) **caption↔image 매핑 오류**(ch54) 진단 후 범위에 맞춰 교정.

## Stage 0 실측 (전수 스캔 + Explore로 확정)
### 결함 1 (열화) — 확정
- **열화 3건, 전부 doc1**: ch1(Fig 28.17 DPGM, 5328B), ch84(Fig 28.23a, 5341B), ch85(Fig 28.23b, 9798B). docs 2-5 = 0 (161 chunk 전수 육안).
- **시그니처**: 검은 배경 픽셀(luminance<40, 64×64) 비율 — 열화 0.76/0.89/0.92 vs 정상 ≤0.45(어두운 인물 사진 1건). **임계 0.6 → 3/3 검출, FP 0**(큰 마진).
- bbox·caption 정확. MinerU 크롭 파일만 열화.

### 결함 1 복구 — **핵심 단순화 발견**
- **DB `bbox_json`(=MinerU content_list bbox)는 1000×1000 정규화**임을 검증: `content_list_bbox/1000 × page_size = middle.json bbox`. doc1(576×648)·doc5(504×719) 정확 일치(±1px), doc3 page 범위 내 타당.
- ⇒ **페이지 렌더 크롭 = `bbox/1000 × 렌더_px`로 충분**. page_size·middle.json **불필요**(렌더 px가 page 기하 내포). ch1/ch84 페이지-크롭 → 완전 다이어그램 복구 실증(전수 스캔 Stage 4).
- ⇒ **스키마 변경(migration 0008) 불필요** — prompt의 후보 A(컬럼 추가)/B(middle.json 보존)보다 단순한 **후보 B′(저장된 bbox ÷1000 런타임 de-normalize)** 채택 권장. DB 변경 0.

### 결함 2 (caption 매핑) — 근인 파악
- content_list page4 image 3개: item63(wide top, **무캡션**)→ch53, item64(좌하 DPGM, "Figure 28.19: 2d embedding" 캡션)→ch54, item65(우하 DPGM, "(b) Figure 28.20" 캡션)→ch55.
- 실제: **wide top(ch53)이 진짜 28.19 2d-embedding 플롯인데 무캡션**, "28.19" 캡션은 ch54(DPGM)에 오배치.
- ⇒ **MinerU content_list caption↔image 근접 페어링 오류**. ingest 충실 복사(결함 아님). 페이지-크롭으로 안 풀림 → 별도 교정.
- 단발/패턴 여부 미확정 → **Stage A에서 전 docs caption 정합성 스캔으로 확정**.

### Explore 확정 (ingest/스키마)
- ingest: `ingest_mineru/content_list.py parse_content_list()` — `item["bbox"]`→`bbox_json`, `image_caption`→`caption`, `img_path`(basename→`data/extracts_v2/<doc>/images/`로 복사, 절대경로 저장). **middle.json/page_size 미사용**.
- 모델 `db/models.py Chunk`: 11컬럼(...bbox_json, content, img_path, caption). `bbox` property = bbox_json 디코드.
- alembic head 0007(`db/session.py ALEMBIC_HEAD`), 0005~0007 전부 additive(`op.add_column`/`create_table`, batch 불필요). guard `schema_guard.require_schema_head`.
- 서빙: `api/routers/reflow.py chunk_image()`(`/v2/chunks/{id}/image`), `page_image()`(`page_NNNN.png`), `render_doc_pages()`. 페이지 렌더 docs1-5 존재(doc1 11 PNG).

## 사용자 결정 (prompt) + plan 권장
- **선별 수정 (b)** 확정: 정상 158개 무손상, 열화만 페이지-크롭.
- **좌표**: prompt 후보 A(권장)였으나 Stage 0 발견으로 **B′(bbox÷1000, 스키마 변경 0) 권장** — debate/challenge에서 검증.
- **서빙**: **1회성 backfill**(결정적·prod 안전) 권장 — 크롭 이미지를 관리 위치 저장 + 서빙 시 우선.
- **결함 2**: Stage A 결과에 따라 — 단발이면 **render-time 교정**(비파괴, 8e-4 dedup 철학), 패턴이면 알려진 것만 교정 + 나머지 escalate.

## Scope
**In (8e-5)**
- **A. ch54 caption 진단**: content_list 인접성 + 전 docs "Figure N.M" caption ↔ 인접 image bbox 정합 스캔 → 단발/패턴 + Stage C 범위 확정.
- **B. 좌표 유틸**(스키마 변경 0): 저장 `bbox_json`÷1000 → 페이지 렌더 px 크롭 유틸. **전 docs/page에서 1000-정규화 성립 검증**(미성립 doc은 fallback/skip + 로그).
- **C. 열화 검출 + 페이지-크롭 서빙**: 검출기(검은 배경 >0.6) → 열화 chunk를 페이지-렌더 bbox 크롭으로 교체 서빙. backfill로 크롭 이미지 생성 + 서빙 경로 우선순위. 결함 2 교정(범위 따라).
- **D. 검증/회귀**: 열화 3건 복구 + ch54 정합 + 정상 158 무회귀 + 테스트.

**Out**
- migration 0008/스키마 변경(B′로 회피; 단 challenge가 A 선호 시 재검토). pixel-perfect overlay(defer). 1.x. 8f. book2 full 1370p(후속, 통합되면 자동 커버). MinerU GPU 재추출(비권장).

## Approach
### B. 좌표 유틸 (reflow.py, 순수 함수)
- `def page_crop_box(bbox_norm, render_w, render_h, pad=20) -> tuple[int,int,int,int] | None`: `[x0/1000*W, y0/1000*H, x1/1000*W, y1/1000*H]` + 패딩 clamp. bbox None/len≠4/정규화 범위(>1000+ε 또는 음수) 이탈 → None(skip).
- **검증 스텝**: 전 docs image chunk에 대해 `bbox/1000` 가 [0,1] 범위인지 확인(이탈 = 비정규화 doc → fallback). doc별 page render 존재 확인.

### C. 검출 + 크롭 서빙 (reflow.py + backfill)
- `def black_bg_fraction(path) -> float`: 64×64 grayscale, luminance<40 비율.
- `def is_degraded_diagram(chunk, render_exists) -> bool`: image ∧ `black_bg_fraction > 0.6` ∧ bbox 정규화 유효 ∧ 페이지 렌더 존재.
- **backfill CLI**(1회성): 전 image chunk 스캔 → 검출 → 페이지-크롭 생성 → `data/extracts_v2/<doc>/images_fixed/<basename>` 저장. **육안 샘플 게이트**(검출 목록 로그, 사람 확인 후 적용).
- 서빙: `chunk_image()`가 `images_fixed/<basename>` 존재 시 우선(없으면 기존 `img_path`). **DB 무변경(파일 override)**. 롤백 = images_fixed 삭제.
- **결함 2 교정**: 단발이면 `get_reflow`에서 알려진 (doc,chunk)→caption 재배치(render-time, 비파괴). 패턴이면 Stage A가 규칙 제시 → 알려진 건만 + summary에 잔여 escalate.

### A. caption 정합 스캔 (진단)
- content_list 재파싱: 각 image item caption "Figure N.M" 추출 + 같은 page image bbox 세로 인접성(caption 위/아래 image) 검사. 번호 순서 ↔ 등장 순서 불일치 플래그. 전 5-doc 집계.

## File-level changes (예상)
| Path | Action | Note |
| ---- | ------ | ---- |
| `src/ht_lens/api/routers/reflow.py` | 수정 | `page_crop_box`, `black_bg_fraction`, `is_degraded_diagram`; `chunk_image` images_fixed 우선; (결함2) render-time caption 교정 |
| `src/ht_lens/cli.py` 또는 `scripts/` | 신규 | 1회성 backfill 커맨드(검출→크롭→images_fixed, 육안 게이트 로그) |
| `tests/unit/test_*` | 신규 | page_crop_box(정규화/패딩/clamp/skip), black_bg_fraction(열화 vs 정상 임계), is_degraded |
| `tests/integration/test_reflow_api.py` | 신규 | images_fixed 우선 서빙, caption 교정 endpoint |
| (스키마) | **없음** | B′ 채택 시 migration 0008 불요 |

## Dependencies (new)
| Package | Why |
| ------- | --- |
| (없음) | PIL 이미 사용(렌더), 크롭·grayscale 순수. |

## Test strategy
- **B 단위**: page_crop_box — 알려진 bbox(doc1 ch1 [420,91,595,313], render 960×1080)→예상 px, 패딩/clamp, bbox None/이탈 skip.
- **C 단위**: black_bg_fraction — 열화 3 파일 >0.6, 정상 샘플 <0.5. is_degraded 조합(검은 배경 아님/페이지 렌더 없음 → False).
- **통합**: images_fixed 존재 시 `/v2/chunks/{id}/image`가 크롭 서빙(없으면 원본). 정상 chunk는 원본 그대로(무회귀). 결함2: 교정된 caption이 reflow 응답 반영, 미교정 정상 불변.
- **회귀**: 800 + 신규. ruff/format/mypy clean. 1.x DB blocks 49850 불변. 정상 158개 `/image` 200 + 육안 샘플.

## DoD mapping
| DoD | How | Evidence |
| --- | --- | --- |
| ch54 진단(단발/패턴) | content_list 인접성 + 전docs caption 정합 스캔 | Stage A 집계 |
| 좌표 plumbing(additive) | bbox÷1000 유틸(스키마 변경 0) + 전docs 정규화 검증 | 단위 + 라이브 크롭 |
| 검출기 3/3, FP 0 | black_bg>0.6 | 단위(열화3 vs 정상) |
| ch1/84/85 페이지-크롭 복구 | bbox 크롭 backfill + 우선 서빙 | 라이브 reflow 우측 = 완전 다이어그램 |
| ch54 매핑 교정 | render-time/데이터 교정(범위 따라) | reflow 응답 정합 |
| 정상 158 무회귀 | 선별(검출된 것만) | 육안 샘플 + /image 200 |
| CI green | jsdom+pytest+mypy+ruff | push 후 |
| 1.x/prod 무손상, 롤백 | frontend/파일 override만, DB 변경 0 | blocks 49850; images_fixed 삭제로 롤백 |

## 위험 / 완화
- **1000-정규화 미성립 doc** → Stage B 검증 스텝(전 docs bbox/1000 ∈ [0,1]); 이탈 doc 크롭 skip + 원본 유지 + 로그. (doc1만 열화라 실질 위험 작음.)
- **검출기 신규 doc FP**(어두운 사진) → backfill 육안 게이트(검출 목록 사람 확인 후 적용); on-the-fly 아닌 backfill이라 안전.
- **결함 2 패턴이 큼** → Stage A로 먼저 범위 확정; 크면 알려진 건만 교정 + escalate(재추출 부르는 매핑 로직 수정은 이 phase 밖).
- **결함 2 데이터 변경 vs additive 원칙** → **render-time 교정(비파괴)** 우선 → DB 무변경 유지(8e-4 dedup과 동일 철학).
- **backfill 산출물 prod 반영** → images_fixed는 추가 파일(기존 img_path 불변); 서버 재시작으로 반영, 롤백=디렉토리 삭제.
- **1.x** → main 분기, frontend+render+추가파일만, DB/migration 0.

## 결정 필요 (debate/challenge·Planner)
- **B′(bbox÷1000, 스키마 변경 0) vs prompt 후보 A(migration 0008)**: Stage 0 발견상 B′ 권장(단순·비파괴). challenge가 A 선호 시(정규화 가정 불안정 등) 재검토.
- **결함 2 교정 깊이**: render-time 단발 교정 vs ingest 매핑 로직 수정(후속). Stage A 결과로 확정.
- **backfill 위치/서빙 우선순위**: `images_fixed/` override vs reflow 응답 img_url 분기.
