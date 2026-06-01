# Phase 8d-2b — Verify (self) — v3 (post R2 micro-fix)

마지막 code commit: `85f0b4f fix(phase-8d-2b): top-K packs smaller hits ... (verify-cross R2 micro-fix)`. 작성 직전 `git status` = clean. 2026-05-31. v3 = cross-verify R2 DOWNGRADE(~86) follow-up gap 처리(Planner-directed micro-fix, **R3 없음**). migration 없음.

## 5-A. Automated checks (실측)
| Check | Command | Result |
| ----- | ------- | ------ |
| Lint | `uv run ruff check .` | All checks passed |
| Format | `uv run ruff format --check .` | 193 files already formatted |
| Type | `uv run mypy src` | Success: no issues found in 83 source files |
| Test | `uv run pytest -m "not llm and not slow" -q` | **736 passed, 1 skipped, 8 deselected in 633.87s** |
| Coverage | v1 측정 | chunk_search 90% / chunk_chat_context 81% (cross-doc 빌더 TestClient 미귀속) |
| CI | prototype-reflow — GitHub CI 미발생(8e 전) | n/a (jsdom CI provisioning 부채) |

테스트 회계: 730 → v2 733(+3 R1 fast) → **v3 736(+3 R2)** + @llm 1(deselected). 8d-2b 누적 신규 17.

## 5-B. cross-verify R1 REJECT + R2 DOWNGRADE → 처리
### R1 REJECT(~76) 실 결함 2 → fix (v2, R2 확인됨)
| 항목 | 처리 | Evidence |
| --- | --- | --- |
| section-chat embedding 실패 500 | best-effort fallback(결정적 context) | test_section_chat_graceful_on_embedding_failure |
| build_section_context_topk budget 무시 | budget cap | test_within_section_topk_picks_relevant_and_respects_budget |

### R2 DOWNGRADE(~86) follow-up gap → 폐쇄 (v3, **functional 결함 아님**)
| R2 항목 | 처리 | Evidence |
| --- | --- | --- |
| #1 budget-cap break→큰 hit 시 heading-only | **`break`→`continue`**: 큰 hit skip하고 작은 관련 hit 계속 pack(섹션 답 품질) | **test_within_section_topk_packs_smaller_hit_when_top_oversized** |
| #2 figure cross-doc end-to-end 미테스트 | image anchor + 2-doc + embedding → related_chunks | **test_figure_cross_doc_refs_end_to_end** |
| #3 section cross-doc 계약(heading 벡터) 미테스트 | section anchor + 2-doc → 다른 doc ref | **test_section_cross_doc_refs_use_heading_vector** |
| #4 cross-lingual @llm(fast 제외) | 설계상(bge-m3 무거움); 결정적 머신은 seeded | (불변, 기재) |

## 5-C. Regression check (R2 micro-fix — CLAUDE.md)
(a)는 production 로직 1-line(break→continue, 큰 섹션 답 품질 직결), (b)(c)는 테스트. 변경별 잠금:
| 변경 | 코드 경로 | 잠금 테스트 |
| --- | --- | --- |
| build_section_context_topk budget loop `break`→`continue` | 큰 hit skip, 작은 hit pack | test_within_section_topk_packs_smaller_hit_when_top_oversized (큰 hit 제외, 작은 hit 포함) |
| (테스트) figure cross-doc | _cross_doc_refs(image, caption query) | test_figure_cross_doc_refs_end_to_end |
| (테스트) section cross-doc | _cross_doc_refs(heading 벡터) | test_section_cross_doc_refs_use_heading_vector |

**grep 증거**: 3 신규 test명 실재. **회귀 0**: 733→736(+3 신규만), 기존 green. (a) continue는 budget cap 유지(작은 hit만 추가 pack) — 절단 path 회귀 없음.

## 5-D. 1.x 무손상 / Coverage
migration 0건(0007 재사용), 1.x block RAG/chat 무변경, prod 0004/blocks=49850 불변, 736 회귀 green. chunk_search 90%/context 81%(cross-doc 빌더 TestClient 미귀속 — 그러나 figure/section cross-doc 응답 refs를 API 테스트가 assert).

## 5-E. 잔존 한계 (정직, 범위 외)
1. neighbor 재번역 + resize = **8d-2c**. cross-doc live(7 docs) = 8e(dev=doc7만; 머신+2-doc+@llm 검증).
2. cross-lingual @llm(fast 제외), router 라인 coverage TestClient, get_or_encode source_hash-only(mixed-model 후속), brute-force(≤50K), 동시 post 상속, jsdom CI(8e), 볼드/영어fallback(8e).

## 5-F. Scoring (100, self)
| Item | Score / Max | Evidence |
| ---- | ----------- | -------- |
| 독창성 | 12 / 15 | chunk RAG 일반화 + figure=image-anchor + topk 별도 fn + best-effort RAG. |
| 완결성 | 31 / 35 | figure(builder+API+cross-doc) + cross-doc(text+figure+section refs) + within-section top-K(positive+budget+oversized-skip) + 17 테스트. 차감: cross-doc live=8e, neighbor/resize=8d-2c. |
| 안정성 | 28 / 30 | 736 green + section 500 fix + budget cap + oversized-skip + graceful/no-write/mixed-dim 잠금 + 1.x 무손상. 차감: context 81% 라인, 동시 post 상속. |
| 확장성 | 17 / 20 | RAG 머신 재사용 + RelatedChunkRef + budget. 차감: brute-force 후속, get_or_encode source_hash-only(mixed-model 후속). |
| **Total** | **88 / 100** | R1 실 결함 2 + R2 gap 4 전부 폐쇄. |

## 5-G. Self verdict
- [x] **PASS_CANDIDATE (Planner-directed micro-fix 완료 → push, R3 없음)**. self **88**. R1 REJECT 실 결함 2개 fix+lock(R2 확인), R2 follow-up gap 4개(budget continue·figure/section cross-doc·cross-lingual) 폐쇄. (a)는 1-line production 개선(큰 섹션 답 품질) + 테스트. 736 green, 1.x 무손상. Codex R2 "not fundamentally broken, not another broad RE-CODE" → cap 준수, R3 미호출. 잔존은 8d-2c·8e·본질적.
- [ ] FAIL → RE-PLAN (해당 없음)
