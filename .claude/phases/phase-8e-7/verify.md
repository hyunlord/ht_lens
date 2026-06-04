# Phase 8e-7 — Verify (self)

Scope: split-extract **병합 ingest** 도구 — N개 분할 MinerU 출력을 offset 병합해 **단일
content_list + namespaced images + full-PDF provenance**로 만든 뒤 **기존
`ingest_mineru_output()` 재사용**(병렬 ingest 경로 0). 8a invariant(schema/overwrite/
rollback/1.x/이미지 정리) 자동 승계. **DB schema 변경 0, 기존 단일 `ingest-mineru` 동작
불변.** 실 book2 추출은 8e-7 머지 후 F3 재개(합성 hermetic 테스트로 검증). 마지막 code
commit(`3317247`) 이후 작성, 추적 트리 clean.

## 5-A. Automated checks
| Check    | Command | Result |
| -------- | ------- | ------ |
| Lint     | `uv run ruff check src tests` | All checks passed! |
| Format   | `uv run ruff format --check .` | clean |
| Type     | `uv run mypy src/` | Success: no issues in **87** source files |
| Test     | `uv run pytest -q` | **861 passed, 8 skipped, 0 failed** (820s); 3 snapshots |
| Focused  | merge unit(7) + merge cli(4) + 기존 mineru ingest | 17+ passed |
| CI       | GitHub Actions | pending push |

861 = 8e-6의 850 + 11 신규(7 merge unit + 4 merge cli).

## 5-B. Functional checks (합성 hermetic — 실 book2 불요)
### 설계 적합 (challenge R1–R6)
| 결정 | 구현 |
| ---- | ---- |
| R1 병렬 ingest 폐기 | `build_merged_output` → 임시 MinerU-shaped dir → 기존 `ingest_mineru_output` 1회. 신규 ingest 로직 0 |
| R2 page_offset = part origin.pdf page_count | `discover_part`가 origin.pdf page_count; offset 누적. max+1 금지 |
| R3 full-PDF provenance | merged dir에 `<stem>_origin.pdf`=full PDF, markdown_path 그곳 |
| R4 경계 검증 | `offset_items` page_idx ∈ [0,page_count) reject, 비-int reject |
| R5 split = ops | CLI 미신설(merge만 자산); split은 PyMuPDF 1회성 |
| R6 namespace 이미지 | `part<NNN>__base`, merged content_list img_path rewrite |

### 핵심 정합 (단위 + 통합)
| Check | Evidence |
| ----- | -------- |
| 경계 연속 | part1(3p, page2) + part2(page0) → merged [2,3] 연속(offset=part1 page_count) |
| page_idx 단조 | merged 2-part → reflow page_idx 정렬 == 자기 자신 |
| chunk 수 = Σ파트 | 2-part(2 text + 2 image) → 4 chunks |
| 빈 파트 offset | part1 0 chunk·page_count 3 → part2 page1 → 4(offset 유지) |
| all-empty reject | all-chrome merged → ingest zero-chunk reject(exit≠0) |
| 이미지 namespace 충돌 0 | 두 파트 `fig1.jpg`(다른 bytes) → `part000__`/`part001__` 둘 다 보존·서빙 200 |
| provenance=full PDF | 단위(origin page_count=full) + **통합: 병합 doc에 `detect-repairs` exit 0**(part origin 아닌 full 해소) |
| 단일=기존 동치(회귀) | 1-파트 multi → page_idx [0,1] 불변, 기존 `ingest-mineru` 경로 영향 0 |
| 기존 ingest 무회귀 | `test_mineru_ingest.py`(단일 ingest, 1x/mineru 공존) green |

### 무영향
- **DB schema 0**(신규 doc는 F3 재개 시 추가; 8e-7은 도구). 1.x DB·prod 무관(읽기/번역 경로 무변경).
- 기존 `ingest-mineru` 동작·시그니처 불변(병합은 신규 함수/커맨드).

## 5-C. Regression check (신규 코드 경로 → 테스트)
| 신규 경로 (grep) | 잠금 테스트 |
| ---------------- | ----------- |
| `offset_items` (offset/OOB/non-int/namespace) | `test_offset_items_*` (3) |
| `build_merged_output` (경계/dup/빈파트/provenance) | `test_build_merged_output_*` (4) |
| `discover_part` (origin.pdf page_count) | merge cli 통합 경유 |
| `ingest-mineru-multi` CLI | `test_ingest_multi_*` (4): 2-part/single-equiv/provenance/all-chrome |
| 이미지 namespace 충돌 | dup-basename 단위 + 통합 |

기존 contract 무변경: 단일 `ingest-mineru`·`/v2`·1.x 불변. 17+ focused / 861 full green.

## 5-D. Scoring (100, self-assessment)
| Item       | Score / Max | Evidence |
| ---------- | ----------- | -------- |
| 독창성     |   14 / 15   | merge→기존 ingest 재사용(8a invariant 승계, 회귀 위험 회피) + full-PDF provenance + namespace |
| 완결성     |   33 / 35   | R1~R6 전부 구현 + 11 테스트(경계/단조/Σ/빈파트/충돌/provenance/회귀); 실 book2는 F3 재개 |
| 안정성     |   29 / 30   | 861/0, mypy 87; 0 DB schema·단일 ingest 불변·OOB/all-empty reject; −1 CI pending |
| 확장성     |   19 / 20   | N-파트 일반(book2 외 대용량 재사용); origin.pdf offset robust; 단일 manifest 무관 |
| **Total**  | **95 / 100**|          |

## 5-E. Self verdict
- [x] **PASS_CANDIDATE (≥95)** — challenge R1~R6 충실 구현, 핵심 정합(경계/단조/provenance/회귀) 테스트 잠금, 0 DB·단일 ingest 불변. cross-verify Round 1 진행.
- [ ] FAIL → RE-CODE
- [ ] FAIL → RE-PLAN
