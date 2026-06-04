# Phase 8e-7 — Verify (self) — v2 (post cross-verify R1)

Scope: split-extract **병합 ingest** 도구 — N개 분할 MinerU 출력 offset 병합 → 단일
content_list + namespaced images + full-PDF provenance → **기존 `ingest_mineru_output()`
재사용**(병렬 ingest 0). **DB schema 0, 기존 단일 `ingest-mineru` 불변.**

Round: v1 95(`bb5aa1c`) → **R1 DOWNGRADE 91-92**("not a reject"; full-PDF 검증·overwrite
테스트·JSON 에러 경로) → RE-CODE(`4d39042`) → v2. HEAD `4d39042` 이후 작성, 추적 트리 clean.

## R1 findings → resolution
| R1 issue | Resolution | Lock |
| -------- | ---------- | ---- |
| §4#1 full-PDF page_count가 Σpart와 미검증(잘못된 PDF→오clip) | `build_merged_output`이 `Σ part.page_count == source_pdf.page_count` 아니면 reject | `test_build_merged_output_rejects_page_count_mismatch`, `test_ingest_multi_wrong_source_pdf_exits` |
| §4#2 overwrite multi-CLI 테스트 부재 | `--overwrite` 재실행 = 교체(중복 아님), 미사용 시 2회차 reject | `test_ingest_multi_overwrite_replaces_not_duplicates` |
| §4#3 part JSON 파싱 raw 예외 누수 | `json.loads` try/except → `IngestError`(기존 단일 ingest와 동일) | `test_build_merged_output_rejects_malformed_part_json` |

## 5-A. Automated checks
| Check    | Command | Result |
| -------- | ------- | ------ |
| Lint     | `uv run ruff check src tests` | All checks passed! |
| Format   | `uv run ruff format --check .` | clean |
| Type     | `uv run mypy src/` | Success: no issues in **87** source files |
| Test     | `uv run pytest -q` | **865 passed, 8 skipped, 0 failed** (697s); 3 snapshots |
| Focused  | merge unit(9) + merge cli(6) + 기존 mineru ingest | 21+ passed |
| Coverage | (phase별 수치 게이트 없음 — 기존 pytest-cov 설정만) | n/a |
| CI       | GitHub Actions | pending push |

865 = v1의 861 + 4 신규 R1 테스트.

## 5-B. Functional checks (합성 hermetic)
### 설계 적합 (challenge R1-R6) — 전부 유지 (v1 §5-B)
merge→기존 ingest 재사용 / page_offset=part origin.pdf page_count / full-PDF provenance /
경계 검증(OOB/non-int) / split=ops / 이미지 part-namespace.

### R1 강화 (operator 계약)
| Check | Evidence |
| ----- | -------- |
| full-PDF 검증 | Σ part page_count != source_pdf page_count → reject(단위 + CLI wrong-pdf) |
| overwrite | multi 재실행 --overwrite → 단일 doc 교체(doc2 404); 미사용 2회차 reject |
| JSON 에러 정규화 | 손상 part content_list → `IngestError`(raw JSONDecodeError 누수 0), CLI exit≠0 |

### 핵심 정합 (v1 유지) + 무영향
경계 연속/page_idx 단조/Σchunk/빈파트 offset/all-empty reject/namespace 충돌 0/provenance=full
PDF(detect-repairs exit 0)/단일=동치. **DB schema 0, 단일 `ingest-mineru`·`test_mineru_ingest`
green, 1.x·prod 무관.**

## 5-C. Regression check (RE-CODE 가드)
| 신규/변경 경로 (grep) | 잠금 테스트 |
| --------------------- | ----------- |
| `build_merged_output` full-PDF page-count 검증 | `..._rejects_page_count_mismatch`, `..._wrong_source_pdf_exits` |
| `build_merged_output` json try/except | `..._rejects_malformed_part_json` |
| `ingest-mineru-multi --overwrite` | `..._overwrite_replaces_not_duplicates` |
| (R1 기존) offset/namespace/provenance/경계 | v1 테스트 유지 |

R1-fix 영역 회귀 재확인: 21+ focused / 865 full green. 단일 ingest·`/v2`·1.x 무변경. 기존 11 테스트 + 4 신규.

## 5-D. Scoring (100, self-assessment — 정직)
| Item       | Score / Max | Evidence |
| ---------- | ----------- | -------- |
| 독창성     |   14 / 15   | merge→기존 ingest 재사용(8a invariant 승계) + full-PDF provenance + namespace |
| 완결성     |   33 / 35   | R1~R6 + full-PDF 검증·overwrite·JSON 정규화 착지; 실 book2는 F3 재개 |
| 안정성     |   29 / 30   | 865/0, mypy 87; operator 계약 검증(page-count)·JSON 정규화·단일 ingest 불변·0 DB; −1 CI pending |
| 확장성     |   19 / 20   | N-파트 일반 + page-count 검증으로 견고; book2 외 재사용 |
| **Total**  | **95 / 100**|          |

## 5-E. Self verdict
- [x] **PASS_CANDIDATE (≥95)** — R1 3건(full-PDF 검증/overwrite/JSON) 전부 해소+테스트 잠금, 핵심 정합 유지, 0 DB·단일 ingest 불변. cross-verify Round 2(final) 진행.
- [ ] FAIL → RE-CODE
- [ ] FAIL → RE-PLAN

## 5-F. Post-R2 addendum (`d62c277`)
cross-verify **R2 = CONFIRM_PASS (95)**. R2 minor residual #1 polished: corrupt/
invalid `--source-pdf`(Typer는 존재만 검사)의 `fitz.open` raw 예외를 `IngestError`로
래핑(JSON 정규화와 동일 철학) + 단위 테스트. R2 residual #2(동일 page_count의 다른 PDF는
page_count만으론 미탐지)는 **operator-contract 한계로 문서화**(summary Known issues) — Codex가
"document rather than fix"로 합의. 전체 **866 passed**(865+1), ruff/mypy clean, 추적 트리 clean.
