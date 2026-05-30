# Phase 8c — Verify (self)

마지막 code commit: test(phase-8c) (feat + test). git status = 코드 무변경(워크플로 stub만). 2026-05-30.

## 5-A. Automated checks
| Check | Command | Result |
| --- | --- | --- |
| Lint | `uv run ruff check .` | All checks passed |
| Format | `uv run ruff format --check .` | clean |
| Type | `uv run mypy src` | Success: no issues found in 79 source files |
| Test | `uv run pytest -m "not llm and not slow" -q --no-cov` | 670 passed, 1 skipped, 7 deselected in 580.04s |
| CI | prototype-reflow — GitHub CI는 8e cutover까지 미발생, 로컬 CI-equivalent green | n/a |

테스트 회계: 655 → 670 = +15 = 9 test_reflow_api + 6 test_reflow_viewer_js. (prototype 제거: prototype 테스트 0개라 감소 없음.)

## 5-B. DoD 검증 (ROADMAP 8c)
| DoD | Evidence |
| --- | --- |
| doc7 챕터 reflow 읽기 자연스러움 (sandbox 품질) | **실 E2E (Playwright, dev DB doc7 103 chunk)**: 16 headings, 57 paragraphs, 15 figures(전부 로드), 87 KaTeX, 15 display 수식. console error 0(favicon 404만). 스크린샷 단일/비교 모드 = sandbox result_v2.html 품질 재현. (번역은 mock '[KO]' prefix — 실 qwen은 8e.) |
| 좌우 비교 hilight sync (chunk bbox) | **Planner-approved exception → page-level**: 비교 토글 11 PDF 페이지 좌측, chunk 클릭 → active chunk + page 하이라이트 + 스크롤 (Playwright 확인: active=1, hl=1). bbox-box는 per-chunk bbox(4-num/null) 노출, best-effort. |
| KaTeX 렌더 (6i 재사용) | applyMath + vendor/katex.min.css. test_reflow_viewer_js(equation/text KaTeX) + Playwright 87 .katex. |

## 5-C. debate(R1) 지적 → 처리
| 지적 | 처리 | Evidence |
| --- | --- | --- |
| .png-only validator가 .jpg figure 깨뜨림(critical) | .png/.jpg/.jpeg validator | test_chunk_image_jpg_served (image/jpeg 200) |
| Page 행이 1.x pages 얽힘 | **render-cache (Page 행 X)** | reflow.py render_doc_pages → data/extracts_v2/<doc>/pages/, pages 테이블 무수정 |
| source PDF 미저장 | deterministic 에러 | test_render_doc_pages_requires_source_pdf (FileNotFoundError) |
| table chunk drop/crash | graceful fallback | test_reflow_table_chunk_preserved + viewer rf-table pre |
| bbox=[] 처리 | bbox null + page-scroll only | test_reflow_bbox_null_when_empty |
| image 누락 404+fallback | controlled 404 + alt placeholder | test_chunk_image_missing_file_404 + reflow.js fig-missing |
| 단일 JS 모듈 | reflow.js 단일 | (분리 안 함) |
| Playwright authoritative | E2E로 viewer 검증 | 위 5-B |
| HT_LENS_DB_URL contract | dev DB 명시 + chunks 선확인 | dev DB doc7 103 chunk 적재 후 verify |
| 캐시 root 하드코딩(test 충돌) | HT_LENS_EXTRACTS_V2_DIR env-override | test_page_image_404 hermetic |

## 5-D. 1.x 공존/무손상
- /v2/* 라우트 + reflow.html 신규. 1.x /documents/* + viewer.html 무수정.
- prototype 제거는 throwaway(block-based, 842a435), 1.x 코어 무관.
- full regression 655 영역 green (1.x API/viewer/translate/embed 전부).
- prod data/ht_lens.db(0004) 불변; 8c는 dev DB data/ht_lens_v2.db.

## 5-E. 잔존 한계 (정직)
1. 번역 mock('[KO]' prefix) — 실 qwen은 8e. (레이아웃/렌더 품질은 mock으로 충분 검증.)
2. bbox 픽셀 sync 미구현 (page-level only, Planner 승인). pixel은 per-page scale factor 후속.
3. Playwright는 수동 E2E(스크린샷+카운트) — pytest fixture 없음(6i 선례). in-suite는 API+renderChunk jsdom.
4. table 실 doc 미검증(doc7 챕터 table 0개; fallback 로직만, 8e).

## 5-F. Scoring (self)
| Item | /Max | 근거 |
| --- | --- | --- |
| 독창성 | 12/15 | reflow reading view + two-tier sync + render-cache(Page 회피). 견고, 비-신규(sandbox seed). |
| 완결성 | 32/35 | DoD 3/3 + 15 테스트 + 실 Playwright E2E + full regression. 차감: Playwright in-suite 아님, 실 qwen/table(8e). |
| 안정성 | 27/30 | mypy/ruff clean, .jpg validator, image-404 fallback, render-cache deterministic, hermetic env, 1.x 공존. 차감: bbox sync는 page-level(승인됨)이라 pixel 미구현. |
| 확장성 | 17/20 | /v2 분리(공존), render-cache, env-config. 차감: 단일 JS 모듈(8d chat 때 분리 필요), bbox pixel 후속. |
| **Total** | **88/100** | |

## 5-G. Self verdict
- [ ] PASS_CANDIDATE (≥95)
- [x] **submit to cross-verify** (self 88 < 95, 정직). DoD 3/3 + debate 전 지적 반영 + 실 E2E 사용자 품질 재현. 잔존은 8e(실 qwen/table)·후속(bbox pixel)·테스트 인프라(Playwright fixture). RE-CODE 후보는 cross-verify 판단.
- [ ] FAIL → RE-PLAN
