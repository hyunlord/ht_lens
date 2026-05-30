# Phase 8d-1 — Verify (self)

마지막 code commit: `c4b2250 test(phase-8d-1): jsdom enrich + sections`. 작성 직전 `git status` = clean. 2026-05-31. frontend-only(JS/HTML/CSS) + 테스트만 — API/DB/LLM/src-py 변경 0.

## 5-A. Automated checks
| Check | Command | Result |
| ----- | ------- | ------ |
| Lint | `uv run ruff check .` | All checks passed |
| Format | `uv run ruff format --check .` | 183 files already formatted |
| Type | `uv run mypy src` | Success: no issues found in 79 source files |
| Test | `uv run pytest -m "not llm and not slow" -q --no-cov` | **691 passed, 1 skipped, 7 deselected in 473.40s** |
| Coverage | n/a (신규 코드 = JS; py 변경 0) | reflow.js/sections.js/enrich_inline.js는 jsdom 서브프로세스로 잠금(py-cov 밖) |
| CI | prototype-reflow — GitHub CI는 8e cutover까지 미발생, 로컬 CI-equivalent green | n/a |

테스트 회계: 677 → **691 (+14)**: `test_reflow_enrich_js`(5) + `test_reflow_sections_js`(9). 기존 `test_reflow_viewer_js`(10) 회귀 green.

## 5-B. Functional checks
### A — 인라인 스타일링 (enrich_inline.js)
| 검사 | Evidence |
| --- | --- |
| 인용 ≥1 digit 필수 ([KO]/[EN]/[Note] 제외, [BJ05]/[Kha+10]/[CDS02] 포함) | test_citation_excludes_digitless_markers |
| 섹션참조는 heading 집합 멤버십만 (식 28.116/그림 28.22 제외) | test_section_ref_membership_only |
| 다중·인접 매칭 1 노드, 텍스트 무손실 | test_multiple_adjacent_matches_one_node |
| KaTeX-safe (`closest('.katex')` skip) | test_katex_zone_is_skipped |
| 평정수(150/16)·미지 소수(0.5) 무손상 | test_plain_integers_and_decimals_untouched |

### B — 섹션 트리/선택/점프 (sections.js)
| 검사 | Evidence |
| --- | --- |
| parseSectionNo (§/후행점/Appendix/bare 변형) | test_parse_section_no_variants |
| 트리 중첩 + 합성노드 0 (28.4>28.4.1/28.4.2>28.4.2.1; 28.3.5/28.5 root) | test_build_tree_nests_without_synthetic_nodes |
| 섹션 식별 = original (번역 prefix 변경 무관) | test_section_id_from_original_when_translation_changes_prefix |
| 선택 = 부모가 자식 포함, 다음 동급 직전 정지 | test_compute_section_includes_children_until_next_sibling |
| 선택 하이라이트 + secNo 이벤트 | test_select_section_highlights_and_emits_secno |
| 점프 scroll+flash, miss=false | test_jump_to_section_scrolls_and_flashes |
| 참조 클릭 stopPropagation (chunk sync 미발동) | test_ref_click_does_not_trigger_chunk_sync |
| TOC 중첩 렌더 + onJump 콜백 + 선택버튼 | test_render_toc_nested_with_callbacks |
| TOC drawer가 compare grid 밖 (2 pane 유지) | test_toc_drawer_outside_compare_grid (실 reflow.html 로드) |

### 라이브 서빙 (8086, dev DB doc7)
- 신규 에셋 전부 200: reflow.html / reflow.js / sections.js / utils/enrich_inline.js / css/reflow.css.
- 서빙된 reflow.js가 두 신규 모듈 import 확인(grep=2). 사용자 시각 평가 URL 가동: `http://100.70.109.50:8086/static/reflow.html?doc=1`.
- 시각 품질(인용/참조 표시, 목차, 점프, 섹션선택 하이라이트)은 사용자 확인 대상 (DoD 사용자 시각; 6i/8c 선례 — jsdom이 로직 잠금).

## 5-C. DoD 매핑 (8d-1 = 사용자 A+B 목표)
| DoD | Evidence |
| --- | --- |
| 인용/섹션참조 스타일 (A) | enrich 5 테스트 + 라이브 |
| 섹션 트리 표시 (B) | buildSectionTree/renderToc 테스트 + 라이브 |
| 섹션 선택 (B) | select 테스트(부모=자식, secNo 이벤트) |
| 참조 28.3.5 클릭→점프 (B) | jump + ref-click 테스트(stopPropagation) |
| 볼드 → 데이터 부재(8e 재추출) | 인용/참조로 대체, 정직 기재 |
| KaTeX/번역/레이아웃 무손상 | KaTeX-safe + viewer 10 회귀 + compare-layout 테스트 |
| 1.x 무손상 | API/DB/src-py 변경 0; `data/ht_lens.db` blocks=49850 불변; 691 회귀 |

## 5-D. 잔존 한계 (정직)
1. chat/핀/RAG/섹션질문/figure채팅/neighbor 재번역 = **8d-2** (결정 locked: 하이브리드 context, 짧은chunk 재번역).
2. backend `sections[]` canonical 모델 = 8d-2 (chat context); 8d-1은 frontend 파생 + `sectionselect`가 secNo 탑재(opaque-id coupling 회피).
3. 진짜 볼드 = 8e MinerU 재추출 (현 데이터 has_bold=0).
4. cross-doc/챕터 외 참조 = plain text 유지(미파손); 해소는 8d-2 RAG.
5. 시각 자연스러움/스크린샷 = 수동(in-suite는 24 jsdom; 6i/8c 선례).

## 5-E. Scoring (100, self)
| Item | Score / Max | Evidence |
| ---- | ----------- | -------- |
| 독창성 | 12 / 15 | KaTeX-safe DOM-only enrich, 멤버십 disambiguation, original 기반 secNo, secNo-event 분리. 차감: 트리는 표준 패턴. |
| 완결성 | 31 / 35 | A+B DoD 충족 + 14 테스트(debate R1–R12 전부 잠금) + 라이브 서빙. 차감: 시각 자연스러움 수동, 볼드는 데이터 부재. |
| 안정성 | 28 / 30 | ruff/format/mypy clean, 691 회귀 0, KaTeX-safe·stopPropagation·compare-layout·합성노드0 전부 잠금, 1.x 무손상. 차감: 시각 회귀는 jsdom 구조 검증(픽셀 아님). |
| 확장성 | 17 / 20 | enrich/sections 모듈 분리(8d-2 토대), secNo 이벤트 계약, frontend-only로 API 무변경. 차감: backend section 모델 8d-2 이연. |
| **Total** | **88 / 100** | |

## 5-F. Self verdict
- [ ] PASS_CANDIDATE (≥95)
- [x] **submit to cross-verify Round 1** (self 88 < 95, 정직). debate R1–R12 전부 구현+테스트 잠금, DoD A+B 충족, 691 회귀 0, 1.x 무손상. 잔존은 8d-2(chat/backend section)·8e(볼드/cross-doc)·본질적 수동(시각).
- [ ] FAIL → RE-CODE / RE-PLAN
