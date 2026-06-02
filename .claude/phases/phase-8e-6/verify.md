# Phase 8e-6 — Verify (self) — v2 (post cross-verify R1)

Scope: F2 = 읽기 전용 `detect-repairs` audit CLI + 검출기(열화 / caption 오배치).
신규 doc repair 발견 자동화, 적용은 사람 게이트(draft seed → `repair-images`가 유일
overrides writer). **0 DB/schema/migration, ingest 무수정, 1.x 불변.**

Round: v1 93(`f23b2d9`) → **R1 DOWNGRADE 88-90** (order 충돌·repo 오염·skip 증거·doc5
증거) → RE-CODE(`84732b3`) → v2. HEAD `84732b3` 이후 작성, 추적 트리 clean.

## R1 findings → resolution
| R1 issue | Resolution | Lock |
| -------- | ---------- | ---- |
| §4#1 same-basename 미리보기 충돌(order_by_base가 last로 collapse) | `DegradedCandidate.order_idx`; 미리보기명 = page+order(basename map 폐기) | `test_detect_degraded_images_same_basename_same_page_distinct_identity`, `test_detect_repairs_same_basename_same_page_distinct_previews` |
| §4#2 기본 --out이 tracked repo 오염(`repair_seeds/book.detected.json`) | 기본 draft = gitignored `<extracts>/<doc>/repair_draft.detected.json`; 명시 --out만 verbatim. stray 삭제 | `test_detect_repairs_default_out_does_not_touch_repo` |
| §4#3 `_skipped`가 basename만(식별 불가) | page_idx/order_idx/bbox 포함 | (CLI 코드 + 리뷰) |
| §4#4 doc5 4-page 재탐지 증거 없음 | 라이브 detect-repairs doc5 → [109,223,257,339]; docs 2/3/4/5 degraded FP 0 | 아래 5-B |

## 5-A. Automated checks
| Check    | Command | Result |
| -------- | ------- | ------ |
| Lint     | `uv run ruff check src tests` | All checks passed! |
| Format   | `uv run ruff format --check .` | clean |
| Type     | `uv run mypy src/` | Success: no issues in **86** source files |
| Test     | `uv run pytest -q` | **847 passed, 8 skipped, 0 failed** (751s); 3 snapshots |
| Focused  | image_repair(36) + repair_cli(8) | 44 passed |
| CI       | GitHub Actions | pending push |

847 = v1의 844 + 3 신규 R1 테스트.

## 5-B. Functional checks (live)
### R1 §4#4 — doc5 재탐지 + FP 0 (detect-repairs, tmp extracts, prod 무영향)
| doc | degraded | caption-mispair pages |
| --- | -------- | --------------------- |
| 2 | 0 | 0 |
| 3 | 0 | **2** (신규 후보 — 미리뷰; 게이트 필수 입증) |
| 4 | 0 | 0 |
| 5 | 0 | **[109, 223, 257, 339]** = F1 4페이지 정확 재탐지 |
| (1) | **3** | [4] (8e-5/F1 기지 결함) |

- **degraded FP 0** (doc1만 3건). caption 탐지가 doc5 4페이지를 DB 기준 재탐지(F1은 manifest override라 DB caption 미변경 → 재탐지 정상). doc3 2건은 **미리뷰 후보**(report-only) — 자동 적용 0, 사람 검토 대상(게이트 가치 입증).

### 설계 적합 (GATE 2 승인)
| 결정 | 구현 |
| ---- | ---- |
| #1 caption report-only | `_caption_mispair_candidates` 리포트만; captions 사람 편집 |
| #2 C′(migration 0) | origin.pdf page.rect; draft에 origin_pdf{path,sha256} |
| #3 분리 read-only CLI | `detect-repairs`(ingest 무수정) |
| #4 단일 writer | draft seed + 미리보기만; `repair-images`가 유일 overrides writer |

### 회귀 (8e-5/F1 불변)
doc1 `/v2/chunks/1/image`=image/png(fixed clip); doc5 ch1947="(a) Parallel design"; `test_repair_seeds.py` doc1(3+3)/doc5(8) 유효; 1.x mtime 2026-05-28 불변; schema 0.

## 5-C. Regression check (RE-CODE 가드)
| 신규/변경 경로 (grep) | 잠금 테스트 |
| --------------------- | ----------- |
| `DegradedCandidate.order_idx` / `detect_degraded_images` 입력 (page,order,path,bbox) | `test_detect_degraded_images`(order_idx), `..._same_basename_same_page_distinct_identity` |
| `detect-repairs` 미리보기 page+order 명명 | `test_detect_repairs_same_basename_same_page_distinct_previews` |
| 기본 --out gitignored | `test_detect_repairs_default_out_does_not_touch_repo` |
| `_skipped` page/order/bbox | CLI 코드 |
| `detect_caption_mispairs` | flag/no-FP/single/nested 단위 + 라이브 doc5 |

기존 contract 무변경(`/v2`·1.x·기존 CLI). 8e-5/F1 manifest·서빙 불변. 44 focused / 847 full green.

## 5-D. Scoring (100, self-assessment)
| Item       | Score / Max | Evidence |
| ---------- | ----------- | -------- |
| 독창성     |   14 / 15   | report-only audit + order_idx 식별 + C′ provenance + 단일 writer |
| 완결성     |   33 / 35   | 4 설계 구현 + doc5 4페이지 재탐지 + FP 0 라이브; book2 실측은 F3 |
| 안정성     |   29 / 30   | 847/0, mypy 86; order 충돌·repo 오염·skip 증거 해소; 0 DB/ingest/1.x; −1 CI pending |
| 확장성     |   19 / 20   | order 식별로 book2 대규모 안전; 단일 manifest lifecycle; 검출기 순수 |
| **Total**  | **95 / 100**|          |

## 5-E. Self verdict
- [x] **PASS_CANDIDATE (≥95)** — R1 4건 전부 해소+테스트/라이브 잠금(doc5 재탐지·FP 0·order 식별·repo 무오염). cross-verify Round 2(final) 진행.
- [ ] FAIL → RE-CODE
- [ ] FAIL → RE-PLAN
