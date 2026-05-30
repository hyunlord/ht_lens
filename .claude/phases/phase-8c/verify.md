# Phase 8c — Verify (self) — v3 (post R2 micro-fix)

마지막 code commit: `6516029 test(phase-8c): lock UI fallback handlers + radio toggle (R2 micro-fix)`. 작성 직전 `git status` = clean(코드 무변경). 2026-05-30.
v3 = verify-cross **R2 DOWNGRADE(~84)** 대응 — Planner-directed micro-fix(test-only + 1 export seam, **production 행위 무변경 → R3 cross-verify 없음**). v2 대비: 5-B2(R2 항목 처리)·5-D(CLAUDE.md 회귀 표)·5-F(coverage) 추가, 카운트 정정.

## 5-A. Automated checks (실측)
| Check | Command | Result |
| --- | --- | --- |
| Lint | `uv run ruff check .` | All checks passed |
| Format | `uv run ruff format --check .` | 181 files already formatted |
| Type | `uv run mypy src` | Success: no issues found in 79 source files |
| Test | `uv run pytest -m "not llm and not slow" -q --no-cov` | **677 passed, 1 skipped, 7 deselected in 585.78s** |
| Coverage | `uv run pytest tests/integration/test_reflow_api.py` (addopts `--cov=ht_lens`) | reflow.py **69%** (branch) — 상세 5-F |
| CI | prototype-reflow — GitHub CI는 8e cutover까지 미발생, 로컬 CI-equivalent green | n/a |

테스트 회계: 655 → v1 670(+15) → v2 674(+4 RE-CODE) → **v3 677(+3 micro-fix)**.
8c 합계 **22**: **12** `test_reflow_api`(API/read-model) + **10** `test_reflow_viewer_js`(jsdom; renderChunk·syncToChunk·buildPdfPane·fallback·toggle).
(v2의 "13 test_reflow_api"는 오기 — 실측 `grep -c` = 12. R2 nit #5 정정.)

## 5-B. verify-cross R1 DOWNGRADE 4 gap → 처리 (유지)
| R1 gap | 처리 | Evidence |
| --- | --- | --- |
| traversal test name만 있고 미검증 | 실제 traversal 분기 호출 | test_chunk_image_traversal_rejected (img_path '..' → 500) |
| syncToChunk(compare 이벤트) 미테스트 | full-DOM jsdom 하니스 | test_sync_to_chunk_compare_highlights_page (active chunk + page hl) |
| page_image SUCCESS 경로 미테스트 | 캐시 PNG 200 | test_page_image_success_serves_cached_png (200 image/png + no-cache) |
| render_doc_pages negative만 | 실 PDF 렌더 + 파일명 검증 | test_render_doc_pages_positive (page_0000/0001.png == page_image 규약) |

## 5-B2. verify-cross R2 DOWNGRADE 5 항목 → 처리 (신규)
R2는 "Round 1 gap은 깔끔히 fix, RE-CODE 회귀 없음 — 잔여는 evidence/process gap"으로 판정. 5건 처리:
| R2 항목 | 처리 | Evidence |
| --- | --- | --- |
| #1 coverage 미실행(--no-cov) | reflow.py coverage 1회 실측 | 5-F (69%, gap 정직 분해) |
| #2 toggle 수동 evidence만 | radio 토글 in-suite jsdom 잠금 | test_radio_toggle_updates_layout_mode (single→compare, layout.dataset.mode) |
| #3 regression-check 서술문(표 아님) | CLAUDE.md 표 형식으로 재작성 | 5-D |
| #4 UI fallback 핸들러 미테스트(reflow.js:44-50, 112-114) | 둘 다 jsdom 잠금 | test_image_error_swaps_in_fig_missing_fallback / test_page_render_error_updates_label |
| #5 카운트 nit(13 vs 12) | 정정 | 5-A (12 API + 10 jsdom) |
| (잔여) doc7 자연스러움 Playwright 수동 | in-suite fixture 없음 — 6i 선례, 시각/품질 검증은 본질적 수동 | 5-C |

## 5-C. DoD 검증 (ROADMAP 8c)
| DoD | Evidence |
| --- | --- |
| doc7 챕터 reflow 읽기 자연스러움 | 실 Playwright E2E(dev DB doc7 103 chunk): 16 headings/57 paragraphs/15 figures/87 KaTeX/15 display, console error 0(favicon만), result_v2.html 품질 재현. (번역 mock '[KO]', 실 qwen 8e.) **시각 품질은 본질적 수동** — in-suite는 렌더 로직(renderChunk) 잠금. |
| 좌우 비교 hilight sync | **Planner-approved page-level**. in-suite 잠금: syncToChunk(active+hl) + **radio toggle(layout.dataset.mode)** + page-render fallback(label). bbox 4-num/null 노출(two-tier). |
| KaTeX 렌더 (6i 재사용) | applyMath + vendor/katex; test_reflow_viewer_js(equation/text) + Playwright 87 .katex |

## 5-D. Regression check (RE-CODE v2 + micro-fix v3) — CLAUDE.md 표
RE-CODE(v2)·micro-fix(v3) 모두 **test-only + 1 export seam**(production 행위 무변경). 변경별 새 코드 경로 → 잠금 단위 테스트:

| 라운드 | 변경 / 새 코드 경로 | 새 함수·handler·seam | 잠금 단위 테스트 |
| --- | --- | --- | --- |
| v2 | _validate_v2_image traversal 분기 | (기존 fn) | test_chunk_image_traversal_rejected |
| v2 | syncToChunk compare 이벤트 | (기존 fn) | test_sync_to_chunk_compare_highlights_page |
| v2 | page_image 200 경로 | (기존 handler) | test_page_image_success_serves_cached_png |
| v2 | render_doc_pages 렌더+파일명 규약 | (기존 fn) | test_render_doc_pages_positive |
| v3 | image onerror → `.fig-missing` (reflow.js:44-50) | renderChunk error handler | test_image_error_swaps_in_fig_missing_fallback |
| v3 | page-render onerror → 라벨 (reflow.js:112-114) | buildPdfPane error handler | test_page_render_error_updates_label |
| v3 | radio change → layout.dataset.mode (reflow.js:170-173) | auto-init toggle handler | test_radio_toggle_updates_layout_mode |
| v3 | **buildPdfPane export**(reflow.js:181) — **비행위 test seam**, prod import 0, auto-init 불변 | export 노출만 | _FULL_PRELUDE import + test_page_render_error_updates_label가 호출 |

**grep 증거**(새 이름이 테스트 파일에 실재): `buildPdfPane`(test:169,175,239), `.fig-missing`(test:222), `원문 렌더 없음`(test:246), `input[name="mode"]`/`layout.dataset.mode`(test:255,257,259), 3 신규 test명(test:212/234/249). prod export: `reflow.js:181 export { buildPdfPane, renderChunk, syncToChunk }`.

**회귀 0**: full regression 674→677(+3 신규만), 기존 영역 무변경. micro-fix는 새 production 함수/state field 도입 0(기존 buildPdfPane export만), 새 코드 경로(3 핸들러)는 위 표대로 전부 잠금.

## 5-E. 1.x 공존/무손상
/v2/* + reflow.html 신규. 1.x /documents/* + viewer.html 무수정. prototype 제거=throwaway(decision D). buildPdfPane export는 reflow.js 내부 한정(1.x 무관). full regression 655 영역 green. prod data/ht_lens.db(0004) 불변(8c=dev DB).

## 5-F. Coverage 정직 분해 (R2 #1)
`reflow.py` 69% (101 stmt / 26 miss, branch). Miss = `74-75, 79-80, 90-91, 100-127, 139, 157-160, 176-183`. 분해:
- **HTTP 핸들러 본문**(90-91, 100-127, 139, 157-160, 176-183): get_reflow 루프·chunk_image·page_image 본문. **실행되나 미귀속** — Starlette TestClient 경유 핸들러는 coverage가 귀속 못함(concurrency=thread 추가해도 동일). 단, 12개 API 테스트가 **응답을 assert**하므로 실행은 증명됨(예: test_reflow_order_and_types가 `[heading,text,equation]`을 assert → 100-127 루프 실행 필수).
- **미실행 방어 분기**(74-75, 79-80): _bbox_or_none의 malformed-json / 비숫자 except. 어떤 테스트도 깨진 bbox json을 안 먹임 → 미히트. 순수 가드, 저위험.
- 직접 호출 코드(render_doc_pages 194-205, _bbox_or_none happy)는 귀속됨.
- reflow.js 경로(renderChunk 전 분기·syncToChunk·buildPdfPane·fallback·toggle)는 py coverage 밖(subprocess) — 10 jsdom 테스트로 잠금.
→ 69%는 측정 하한(핸들러 본문은 기능적으로 100% assert). coverage config(concurrency) 변경은 8c 스코프 외 → 미시행.

## 5-G. 잔존 한계 (정직)
1. 번역 mock — 실 qwen 8e. 2. bbox pixel sync 미구현(page-level only, Planner 승인). 3. doc7 자연스러움/스크린샷은 수동 Playwright(in-suite는 API+renderChunk+syncToChunk+fallback+toggle jsdom; 6i 선례). 4. render-cache 운영 채움 경로(CLI)는 8e에서 와이어(render_doc_pages 함수는 존재+테스트). 5. reflow.py 69% 라인 — 본문은 기능 assert(5-F), 절대 수치는 낮음. 6. 단일 JS 모듈(chat/pin 분리는 8d).

## 5-H. Scoring (self)
| Item | /Max | 근거 |
| --- | --- | --- |
| 독창성 | 12/15 | reflow + two-tier sync + render-cache(Page 회피). |
| 완결성 | 32/35 | DoD 3/3 + 22 테스트(R1 4 gap + R2 toggle/fallback 폐쇄) + 실 E2E. 차감: doc7 자연스러움은 본질적 수동, 실 qwen/table(8e). |
| 안정성 | 28/30 | mypy/ruff clean, traversal/page-success/render/sync/**fallback×2/toggle** 전부 잠금, .jpg validator, hermetic env, 1.x 공존. 차감: reflow.py 69% 라인(본문은 assert, 5-F), bbox page-level(승인). |
| 확장성 | 16/20 | /v2 분리, render-cache, env-config. 차감: render-cache CLI 미와이어(8e), 단일 JS 모듈(8d), bbox pixel 후속. |
| **Total** | **88/100** | |

## 5-I. Self verdict
- [x] **PASS_CANDIDATE (Planner-directed micro-fix 완료 → push, R3 없음)**. self **88**. R2 DOWNGRADE 5 항목 전부 처리(5-B2): coverage 실측·toggle/fallback×2 in-suite 잠금·회귀 표 정규화·카운트 정정. Codex R2 = "RE-CODE 회귀 없음, evidence/process gap" → micro-fix가 evidence gap 폐쇄. production 행위 무변경(test-only + export seam) → CLAUDE.md cap 준수, **R3 cross-verify 미호출**.
- 88<95이나 자체 cross-verify cap(R2) 도달 + Planner 결정(micro-fix→push). 잔존(doc7 수동·69% 라인·실 qwen·render-cache CLI·bbox pixel)은 정직 기재(5-F/5-G), 전부 8e/후속 또는 본질적 수동.
- [ ] FAIL → RE-PLAN (해당 없음)
