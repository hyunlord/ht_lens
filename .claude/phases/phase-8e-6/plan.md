# Phase 8e-6 — Plan (repair-manifest ingest 통합) — F2

Versioning: v2.0-e6 · `phase-8e-6` 분기 → PR/머지(CI on main/PR). **GATE 2: 이 plan은 Planner 승인 전 구현 착수 금지.**

## Context
8e-5(doc1 수동 repair) + F1(doc5 caption 교정) 후, **두 MinerU 결함이 양쪽 doc에서 패턴 확정**:
- **defect 1 (이미지 열화)**: 벡터 PGM 다이어그램이 검은 배경 노드 blob만 캡처(화살표·라벨 손실). 시그니처 = 검은 배경 픽셀 비율 >0.6 (열화 0.76–0.92 vs 정상 ≤0.45, 5-doc FP 0). doc1 3건.
- **defect 2 (caption 오배치)**: 다중-이미지 페이지에서 무캡션 패널의 (a)/(b) 라벨이 형제 캡션으로 세로 병합. doc1 page4(3) + doc5 4페이지(8) 확정.

현재 둘 다 **per-doc 수동 manifest**(`repair_seeds/*.json` + `repair-images`). **book2 full(F3, 1370p, multi-panel 수십 페이지 예상)** 진입 전, ingest 파이프라인에 통합해 신규 doc가 수동 manifest 없이 처리되게 해야 함. **GATE 2: plan→debate→challenge→Planner approve 후 구현.**

## Goal
ingest(또는 ingest 직후 단계)에서 (1) 열화 이미지 **자동 검출 + 후보 페이지-클립 생성**, (2) caption 오배치 **자동 검출**(할당은 게이트) → **육안 샘플 게이트**를 거쳐 per-doc `overrides.json`으로 승격. **자동 무조건 적용 금지**(검출 ≠ 적용). 기존 doc1/doc5 결과·정상 이미지 불변.

## Stage 0 실측 (8e-5/F1 + Explore 확정)
- **ingest**: `ingest_mineru/pipeline.py ingest_mineru_output()` (cl_path/images_dir/markdown_path). `content_list.py parse_content_list()` → `item["bbox"]`→`bbox_json`(1000×1000 정규화), `image_caption`→`caption`, `img_path` 복사. middle.json/page_size 미사용.
- **8e-5 재사용 자산** (`src/ht_lens/image_repair.py`):
  - 검출: `black_bg_fraction`/`is_degraded_candidate`(>0.6).
  - 클립: `clip_render_figure(pdf, page_idx, bbox_norm, dest, dpi, pad)` — **소스 PDF `page.rect` 기준 `bbox/1000×page.rect`**(rotation skip). **→ 좌표 plumbing은 origin.pdf만 있으면 해결**(middle.json/page_size 컬럼 불요, 8e-5에서 실증).
  - manifest: `overrides.json`(image/caption override, 안정 evidence page_idx+basename+bbox keyed) + `load/match/save` + `is_safe_basename`/`_valid_bbox` 가드.
  - backfill: `run_image_backfill`(dry-run/apply, allowlist), `build_and_save_overrides`.
  - CLI: `ht-lens repair-images --doc-id --seed --apply/--dry-run`.
- **origin.pdf**: MinerU 출력 `auto/*_origin.pdf`(ingest 시 가용, markdown_path 디렉토리에 상주). F3 book2도 동일.
- **alembic head 0007**, additive 패턴(0005~0007 `add_column`/`create_table`). guard `schema_guard.require_schema_head`.

## 핵심 설계 — 좌표 plumbing 결론 (migration 0008 vs 파일의존)
8e-5 실증상 페이지-클립은 **origin.pdf `page.rect`**만 있으면 됨(`bbox/1000×page.rect`). 그러므로:
- **권장 = 파일의존(C′)**: ingest/repair 시 **origin.pdf로 직접 clip**(이미 `clip_render_figure`가 하는 일). **migration 0008 불요, page_size 컬럼 불요.** 의존성 = "origin.pdf 접근 가능"(MinerU 출력에 상주; markdown_path로 발견).
- **migration 0008(A)는 origin.pdf를 보존 안 할 때만** 필요(page_size + page-point bbox 저장 → 캐시 PNG 크롭). 현재 origin.pdf 보존되므로 **불필요**.
- ⇒ plan은 **C′ 채택 권장**, challenge가 "origin.pdf 비보존 시나리오"를 들면 A 재검토. (DB schema 변경 0 유지 = 8e-5 철학.)

## 핵심 결정 — caption 자동 탐지·교정: F2 포함(opt-1) vs 별도 분리(opt-2)
| 축 | opt-1 (F2에 포함) | opt-2 (별도 phase/수동 유지) |
| -- | ----------------- | ---------------------------- |
| 범위 | ingest서 무캡션-패널 + 병합캡션("(a)…(b)…") 형제 **자동 탐지** → 후보. **할당은 게이트**(spatial 순서 추정은 제안만) | F2는 이미지 열화만. caption은 `repair_seeds` 수동(F1 방식) |
| book2 full 비용 | multi-panel 수십 페이지 → 자동 탐지로 후보 일괄 수집(수동 manifest 부담↓) | 수십 페이지 수동 audit = 큰 부담 |
| 위험 | 라벨↔이미지 할당은 **해석 잔존**(세로 순서 휴리스틱 오류 가능) → 자동 할당 위험. 탐지만이면 안전 | 자동화 0 → 위험 낮으나 확장성 나쁨 |
| 휴리스틱 신뢰 | 탐지(무캡션+병합캡션 공존)는 비교적 견고; 할당(어느 패널=어느 라벨)은 불안정 | N/A |
| 게이트 설계 | **2단 게이트**: 탐지 후보 + 제안 할당 → 사람이 할당 확정/수정 → 적용 | 사람이 전부 수동 |
| 권장 | **하이브리드**: F2가 caption 오배치 **탐지+제안만**(자동 적용 0), 할당 확정은 육안 게이트. 순수 자동 할당은 배제 | — |

**plan 권장**: defect-1(이미지)은 탐지+클립+게이트 완전 자동화. defect-2(caption)은 **탐지+제안까지만 F2 포함**(할당은 게이트, 자동 적용 금지) — book2 수동 부담은 줄이되 해석 위험은 사람이 차단. 순수 caption 자동-할당은 명시적으로 Out. **이 옵션 채택 여부 = Planner 결정**(debate/challenge로 검증).

## Scope
**In (8e-6)**
- **A. ingest 검출 훅**: `ingest_mineru_output` 직후(또는 별도 `ht-lens detect-repairs --doc-id`) image chunk에 `is_degraded_candidate`(>0.6) 적용 → 열화 후보. 다중-이미지 페이지에서 무캡션+병합캡션 형제 → caption 오배치 후보(탐지+제안).
- **B. 후보 manifest + 육안 게이트**: 후보를 **`overrides.candidates.json`**(pending)로 기록(클립 미리보기 생성). `repair-images --review` 또는 기존 dry-run/apply로 사람이 확정 → `overrides.json` 승격. **자동 serving 진입 금지**.
- **C. 자동 페이지-클립**: 확정된 열화 후보 → `clip_render_figure`(origin.pdf, C′). 좌표 plumbing = origin.pdf page.rect(스키마 0).
- **D. 회귀 방지**: 기존 doc1(3 image+3 caption)·doc5(8 caption) manifest 결과 불변; 검출기가 정상 158 image 안 건드림(후보로만, 게이트).

**Out**
- caption **자동 할당 적용**(해석 잔존 → 게이트 필수). migration 0008(C′로 회피, challenge가 뒤집으면 재검토). 1.x. book2 추출(F3). pixel-perfect overlay.

## Approach (개요 — 세부는 승인 후)
1. `detect-repairs` 경로(ingest 통합 or 후속 CLI): doc의 image chunk + origin.pdf → 열화 후보(black_bg) + caption 오배치 후보(무캡션∧형제 병합캡션) → `overrides.candidates.json`(+ 클립 미리보기 PNG, 제안 caption 분할).
2. **육안 샘플 게이트**: 후보 리스트(+미리보기) 사람 확인 → 승인분만 `overrides.json` 승격(image override + 확정 caption). manifest-first(자동 serving 0).
3. 서빙은 기존 8e-5 경로(`chunk_image`/`get_reflow`가 `overrides.json` 조회) 그대로 — 변경 최소.
4. book2(F3)는 이 경로로 후보 자동 수집 → 게이트 통과분만 적용.

## File-level changes (예상 — 승인 후 확정)
| Path | Action | Note |
| ---- | ------ | ---- |
| `src/ht_lens/image_repair.py` | 수정 | caption 오배치 탐지기(`detect_caption_mispair`) + 후보 manifest(candidates) 빌더 |
| `src/ht_lens/cli.py` | 수정 | `detect-repairs`(후보 생성) / `repair-images --review`(게이트 승격) |
| `src/ht_lens/ingest_mineru/pipeline.py` | (검토) | ingest 직후 후보 자동 생성 훅(옵션; 분리 CLI가 더 안전할 수도 — challenge) |
| (migration) | **없음(C′)** | origin.pdf page.rect 사용 |
| `tests/...` | 신규 | 탐지기(열화/caption 오배치), 후보→승격 게이트, 회귀(doc1/doc5 불변) |

## Dependencies (new)
| Package | Why |
| ------- | --- |
| (없음) | PIL/fitz 기존; 8e-5 모듈 재사용 |

## Test strategy
- 검출기: 합성 black 이미지>0.6 / 정상<0.5(기존). caption 오배치 탐지: 무캡션+병합캡션 형제 → 후보 플래그; 정상 multi-panel(전부 라벨) → 후보 0.
- 게이트: 후보 manifest dry-run 무서빙; 승인분만 overrides.json 승격(자동 적용 0).
- 회귀: doc1(3+3)/doc5(8) 기존 manifest 재생성 동일; 정상 chunk 서빙 불변; 검출기 FP 0(5-doc).
- 전체 836+ green, mypy/ruff clean, 1.x 불변.

## DoD mapping
| DoD | How | Evidence |
| --- | --- | --- |
| 검출기 ingest 통합, 3/3 재검출 FP 0 | black_bg>0.6 후보 생성 | 단위 + doc1 3건 재검출 |
| 자동 페이지-클립(좌표 plumbing) | origin.pdf page.rect clip(C′, 스키마 0) | 단위 + 라이브 |
| 육안 샘플 게이트 | candidates→review→overrides 승격 | 게이트 테스트(자동 적용 0) |
| caption 탐지+제안(자동 할당 X) | 무캡션+병합캡션 탐지, 할당 게이트 | 단위 + doc5 패턴 재탐지 |
| 기존 doc1/doc5 불변 | 동일 manifest 재생성 | 회귀 테스트 |
| additive migration(1.x 무손상) | C′=migration 0 | schema diff 0 |
| CI green | jsdom+pytest+mypy+ruff | push 후 |

## 위험 / 완화
- **검출기 신규 doc FP**(book2 어두운 사진/현미경) → **육안 게이트 필수**(자동 serving 0); 후보 미리보기 사람 확인.
- **caption 할당 해석 오류** → **자동 할당 배제**, 탐지+제안만; 사람이 확정.
- **origin.pdf 비보존**(C′ 의존성) → book2 등 origin.pdf 보존 확인; 없으면 migration 0008(A) fallback.
- **ingest 훅이 ingest 실패 유발** → 후보 생성은 ingest와 **분리**(별도 CLI) 검토(ingest 트랜잭션 비오염) — challenge에서 결정.
- **회귀**(기존 manifest) → doc1/doc5 재생성 동일성 테스트.
- **1.x** → schema 0, frontend/서빙 무변경.

## 결정 필요 (debate/challenge·Planner — GATE 2)
1. **caption: opt-1(탐지+제안 F2 포함) vs opt-2(별도/수동)** — plan 권장 = 하이브리드(탐지+제안, 할당 게이트). Planner 확정.
2. **좌표: C′(origin.pdf, 스키마 0) vs A(migration 0008)** — 권장 C′; origin.pdf 비보존 우려 시 A.
3. **검출 위치: ingest 훅 통합 vs 분리 CLI(`detect-repairs`)** — 분리 CLI가 ingest 트랜잭션 안전(권장), 자동성은 약간↓.
4. **게이트 형식**: candidates.json + 미리보기 → `repair-images --review` 승격 흐름 OK?
