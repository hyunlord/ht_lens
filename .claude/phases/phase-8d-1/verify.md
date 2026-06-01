# Phase 8d-1 — Verify (self) — v2 (post RE-CODE, verify-cross R1)

마지막 code commit: `08e54be test(phase-8d-1): load() integration ... (verify-cross R1)` (직전 `4807705` fix). 작성 직전 `git status` = clean. 2026-05-31. v2 = cross-verify R1 DOWNGRADE(~79) 대응 — 실 결함 2개 fix + 테스트/증거 보강.

## 5-A. Automated checks (실측, CI-equivalent)
| Check | Command | Result |
| ----- | ------- | ------ |
| Lint | `uv run ruff check .` | All checks passed |
| Format | `uv run ruff format --check .` | 184 files already formatted |
| Type | `uv run mypy src` | Success: no issues found in 79 source files |
| Test | `uv run pytest -m "not llm and not slow" -q` (coverage 포함, **--no-cov 제거** — R1 §1) | **692 passed, 1 skipped, 7 deselected in 570.21s** |
| Coverage | 위 명령 (pyproject `--cov=ht_lens`) | TOTAL **75%** (신규 코드=JS이라 py-cov 밖; reflow.py 불변) |
| shellcheck | CI `shellcheck scripts/*.sh` | 8d-1은 `scripts/*.sh` 무변경 → N/A(로컬 미설치, CI 전용) |
| CI | prototype-reflow — GitHub CI는 8e cutover까지 미발생 | n/a(이 branch) |

테스트 회계: 677 → v1 691(+14) → **v2 692(+1 RE-CODE: load 통합)**. 8d-1 신규 15: `test_reflow_enrich_js`(5) + `test_reflow_sections_js`(9) + `test_reflow_load_js`(1). 기존 `test_reflow_viewer_js`(10) 회귀 green.

## 5-B. verify-cross R1 DOWNGRADE → 처리 (실 결함 2 + gap 3)
| R1 항목 | 종류 | 처리 | Evidence |
| --- | --- | --- | --- |
| §4 sections.js가 order_idx 정렬, ReflowChunk엔 미노출(undefined→NaN) | **실 결함** | order_idx 의존 제거 → API 응답 순서 신뢰(reflow API가 order_idx로 이미 정렬) | `4807705`; test_load(order_idx 없는 응답으로 트리/선택 작동) |
| §4 heading이 자기 섹션번호를 self-ref로 wrap | **실 결함** | load()에서 heading은 enrichInline 미호출(title은 prose 아님) | `4807705`; test_load(headingSelfRef==0, dataSec==28.4) |
| §4 TOC 토글 미테스트 | gap | 토글 hidden→open + aria 검증 | test_load(hiddenBefore/After, aria) |
| §4 load() 통합 미테스트 | gap | fetch-stub + 실 reflow.html 통합 테스트 | test_reflow_load_js (build→enrich→toc→toggle) |
| §1 --no-cov로 CI coverage 우회 | 증거 | coverage 포함 재실행(692, 75%) | 5-A |
| §4 "no XSS" 과한 일반화 | 정직 | 5-D 한정(신규는 DOM-only; 기존 에러 sink는 pre-existing 부채) | 5-D |
| §2 테스트 fixture가 order_idx로 mismatch 가림 | 증거 | sections fixture에서 order_idx 제거(ReflowChunk shape 일치) | `08e54be` H/T 팩토리 |

## 5-C. Regression check (RE-CODE — CLAUDE.md 필수)
RE-CODE는 **제거(order_idx 정렬) + 분기 가드(heading enrich skip) + 테스트 추가**. 새 production 함수/state field **도입 0**(제거·가드만). 변경별 잠금:
| RE-CODE 변경 | 새 코드 경로 | 잠금 단위 테스트 |
| --- | --- | --- |
| sections.js: order_idx 정렬 제거 → 입력(문서) 순서 신뢰 | buildSectionTree/computeSectionChunks가 array 순서 사용 | test_load_builds_enriches_toc_without_order_idx (order_idx 없는 응답) + 기존 sections 9(fixture order_idx 제거 후 green) |
| reflow.js: heading enrich skip | heading은 enrichInline 미호출(자기참조 0) | test_load (headingSelfRef==0) |
| 신규 test_reflow_load_js | load() 전체 흐름 + 토글 | 자체 |

grep 증거: `test_load_builds_enriches_toc_without_order_idx`·`headingSelfRef`·`hiddenBefore`가 test_reflow_load_js.py에 실재; sections fixture(H/T 팩토리)에 `order_idx` 부재(ReflowChunk 일치). 회귀: 691→692, 기존 24 jsdom + 전체 회귀 green, 0 회귀.

## 5-D. DoD + 안전 (정직)
| 항목 | Evidence |
| --- | --- |
| 인용/섹션참조 스타일 (A) | enrich 5 + load 통합 (cites=[BJ05], refs=[28.4], 28.116 plain) |
| 섹션 트리/선택/점프 (B) | sections 9 + load(tocLinks≥2) |
| 참조 클릭 stopPropagation | test_ref_click_does_not_trigger_chunk_sync |
| **신규 코드 XSS** | enrich/sections/toc 전부 createElement+textContent (innerHTML 미사용). **단** `reflow.js` load() **에러 경로**의 `innerHTML=e.message`는 **pre-existing(8c)**, 8d-1 무변경 → 부채로 기재(스코프 외, 자가호스팅 저위험). |
| 1.x 무손상 | API/DB/src-py 변경 0; `data/ht_lens.db` blocks=49850 불변; 692 회귀 |

## 5-E. 잔존 한계 (정직)
1. chat/핀/RAG/섹션질문/figure/neighbor 재번역 = **8d-2**(하이브리드 context, 짧은chunk 재번역 locked).
2. backend `sections[]` canonical = 8d-2; 8d-1은 응답순서 신뢰 + secNo 이벤트.
3. 진짜 볼드 = 8e 재추출(has_bold=0). cross-doc 참조 = plain 유지(8d-2 RAG).
4. 시각 자연스러움/픽셀 = 수동(in-suite는 25 jsdom 구조/로직; 6i/8c 선례).
5. load() 에러 경로 innerHTML sink = pre-existing 부채(8d-1 무변경).

## 5-F. Scoring (100, self)
| Item | Score / Max | Evidence (R1 대비 변화) |
| ---- | ----------- | -------- |
| 독창성 | 12 / 15 | DOM-only enrich, 멤버십 disambiguation, original secNo. (R1 confirm 12) |
| 완결성 | 31 / 35 | A+B DoD + 15 테스트 + **load() 통합(라이브 계약)**. 차감: 시각은 본질적 수동. (R1 28→ 통합 추가로 회복) |
| 안정성 | 28 / 30 | ruff/format/mypy + **coverage 692** + 실 결함 2 fix+잠금 + 토글/KaTeX-safe/stopPropagation 전부 테스트. 차감: 픽셀 아닌 구조검증, pre-existing 에러 sink. (R1 24→ 회복) |
| 확장성 | 17 / 20 | **order_idx 의존 제거(실 계약 robust)** + secNo 이벤트 + 모듈 분리. 차감: backend section 8d-2 이연. (R1 15→ 의존 제거로 회복) |
| **Total** | **88 / 100** | 결함 2 fix로 R1 docking 회복; 잔여는 본질적 수동·8d-2 이연. |

## 5-G. Self verdict
- [ ] PASS_CANDIDATE (≥95)
- [x] **submit to cross-verify Round 2 (최종, cap)** (self 88 < 95, 정직). R1 실 결함 2개 fix + 테스트 잠금(load 통합), CI-equiv coverage 실행, XSS 주장 한정. 새 production 함수 도입 0(제거·가드). 잔존은 8d-2(chat/backend)·8e(볼드)·본질적 수동(픽셀). R2가 새 concrete 결함 없으면 push.
- [ ] FAIL → RE-PLAN
