# Phase 8c — Verify (self) — v2 (post RE-CODE)

마지막 code commit: test(phase-8c): close R1 coverage gaps. git status = 코드 무변경. 2026-05-30. v2 = verify-cross R1 DOWNGRADE 대응(테스트 보강).

## 5-A. Automated checks
| Check | Command | Result |
| --- | --- | --- |
| Lint | `uv run ruff check .` | All checks passed |
| Format | `uv run ruff format --check .` | clean |
| Type | `uv run mypy src` | Success: no issues found in 79 source files |
| Test | `uv run pytest -m "not llm and not slow" -q --no-cov` | 674 passed, 1 skipped, 7 deselected in 603.95s |
| CI | prototype-reflow — GitHub CI는 8e cutover까지 미발생, 로컬 CI-equivalent green | n/a |

테스트 회계: 655 → v1 670(+15) → v2 674(+4 RE-CODE) = +19. 8c: 13 test_reflow_api + 7 test_reflow_viewer_js(jsdom, syncToChunk 포함).

## 5-B. verify-cross R1 DOWNGRADE 4 gap → 처리
| R1 gap | 처리 | Evidence |
| --- | --- | --- |
| traversal test name만 있고 미검증 | 실제 traversal 분기 호출 | test_chunk_image_traversal_rejected (img_path '..' → 500) |
| syncToChunk(compare 이벤트) 미테스트 | full-DOM jsdom 하니스 | test_sync_to_chunk_compare_highlights_page (active chunk + page hl) |
| page_image SUCCESS 경로 미테스트 | 캐시 PNG 200 | test_page_image_success_serves_cached_png (200 image/png + no-cache) |
| render_doc_pages negative만 | 실 PDF 렌더 + 파일명 검증 | test_render_doc_pages_positive (page_0000/0001.png == page_image 규약) |

## 5-C. DoD 검증 (ROADMAP 8c)
| DoD | Evidence |
| --- | --- |
| doc7 챕터 reflow 읽기 자연스러움 (sandbox 품질) | 실 Playwright E2E (dev DB doc7 103 chunk): 16 headings/57 paragraphs/15 figures/87 KaTeX/15 display, console error 0(favicon만), 스크린샷 = result_v2.html 품질 재현. (번역 mock '[KO]', 실 qwen 8e.) |
| 좌우 비교 hilight sync | **Planner-approved page-level**: 토글 11 PDF 페이지, **syncToChunk in-suite 테스트**(active+hl) + Playwright(active=1,hl=1). bbox 4-num/null 노출(two-tier). |
| KaTeX 렌더 (6i 재사용) | applyMath + vendor/katex; test_reflow_viewer_js(equation/text) + Playwright 87 .katex |

## 5-D. Regression check (RE-CODE)
RE-CODE는 **테스트 추가만**(production 코드 무변경). 기존 15 테스트 + 4 신규 = 19 green. full regression 670→674, 회귀 0. 잠금: `_validate_v2_image` traversal, `syncToChunk`, `page_image` 200, `render_doc_pages` 파일명 규약(page_image와 coupling).

## 5-E. 1.x 공존/무손상
/v2/* + reflow.html 신규. 1.x /documents/* + viewer.html 무수정. prototype 제거=throwaway. full regression 655 영역 green. prod data/ht_lens.db(0004) 불변(8c=dev DB).

## 5-F. 잔존 한계 (정직)
1. 번역 mock — 실 qwen 8e. 2. bbox pixel sync 미구현(page-level only, Planner 승인; per-page scale 후속). 3. Playwright는 수동 E2E(in-suite는 API+renderChunk+syncToChunk jsdom; 6i 선례). 4. render-cache 운영 채움 경로(CLI)는 8e 마이그레이션에서 와이어(render_doc_pages 함수는 존재+테스트).

## 5-G. Scoring (self)
| Item | /Max | 근거 |
| --- | --- | --- |
| 독창성 | 12/15 | reflow + two-tier sync + render-cache(Page 회피). |
| 완결성 | 32/35 | DoD 3/3 + 19 테스트(R1 gap 4 폐쇄) + 실 E2E. 차감: Playwright in-suite 아님, 실 qwen/table(8e). |
| 안정성 | 28/30 | mypy/ruff clean, traversal/page-success/render-positive/sync 전부 잠금, .jpg validator, hermetic env, 1.x 공존. 차감: bbox는 page-level(승인). |
| 확장성 | 16/20 | /v2 분리, render-cache, env-config. 차감: render-cache CLI 미와이어(8e), 단일 JS 모듈(8d 분리), bbox pixel 후속. |
| **Total** | **88/100** | |

## 5-H. Self verdict
- [ ] PASS_CANDIDATE (≥95)
- [x] **submit to cross-verify Round 2 (최종, cap)** (self 88 < 95, 정직). R1 4 gap 전부 폐쇄(테스트 추가). DoD 3/3 + 실 E2E 사용자 품질. 잔존은 8e(실 qwen/render-cache CLI)·후속(bbox pixel). R2가 새 concrete 결함 없이 REJECT면 Planner escalate.
- [ ] FAIL → RE-PLAN
