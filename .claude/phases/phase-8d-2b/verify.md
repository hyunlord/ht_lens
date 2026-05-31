# Phase 8d-2b — Verify (self) — v2 (post RE-CODE, verify-cross R1 REJECT)

마지막 code commit: `4e5171a test(phase-8d-2b) ... (verify-cross R1)` (직전 fix `3aba497`). 작성 직전 `git status` = clean. 2026-05-31. v2 = R1 REJECT(~76) 실 결함(section-chat embedding 실패 500) fix + top-K budget cap + 누락 테스트(positive top-K / figure API / cross-lingual) 추가. migration 없음.

## 5-A. Automated checks (실측)
| Check | Command | Result |
| ----- | ------- | ------ |
| Lint | `uv run ruff check .` | All checks passed |
| Format | `uv run ruff format --check .` | clean |
| Type | `uv run mypy src` | Success: no issues found in 83 source files |
| Test | `uv run pytest -m "not llm and not slow" -q` | **733 passed, 1 skipped, 8 deselected in 685.36s** |
| Coverage | 타깃 측정(v1) | chunk_search 90% / chunk_chat_context 81% (cross-doc 빌더 TestClient 미귀속) |
| CI | prototype-reflow — GitHub CI 미발생(8e 전) | n/a (jsdom CI provisioning 부채) |

테스트 회계: 730 → **733** (+3 fast: section-graceful / figure-API / positive-topK) + **1 @llm**(cross-lingual, fast suite 제외 → deselected). 8d-2b 누적 신규 14.

## 5-B. cross-verify R1 REJECT(~76) → 처리
| R1 항목 | 종류 | 처리 | Evidence |
| --- | --- | --- | --- |
| §3/§4 **section-chat가 embedding 실패 시 500**(8d-2a는 무embedding 동작) | **실 결함(regression)** | `_build_context` section top-K embedding을 best-effort try/except로 감싸 실패 시 build_section_context(결정적) fallback | **test_section_chat_graceful_on_embedding_failure** (202, 무500) |
| §4 build_section_context_topk가 budget 무시(긴 hit로 prompt 비대) | **실 결함** | heading + hits를 budget 누적길이로 cap | **test_within_section_topk_picks_relevant_and_respects_budget** (관련 hit + ≤budget) |
| §2 positive within-section top-K 미테스트 | gap | 위 테스트(관련성+budget) | 동상 |
| §2/§4 figure API-level post 미테스트(builder만) | gap | image anchor thread → post → system에 caption+이웃 | **test_figure_anchor_post_uses_figure_context** |
| §2/§4 cross-lingual 테스트 누락(challenge R9 accept) | gap | 실 bge-m3 ko→en 검색 테스트 추가(@llm, fast 제외) | **test_korean_question_retrieves_english_chunk** (@pytest.mark.llm) |

## 5-C. Regression check (RE-CODE — CLAUDE.md)
RE-CODE = section embedding fallback(분기 가드) + budget cap + 테스트. 새 production 함수 0(가드/cap만). 변경별 잠금:
| 변경 | 새 코드 경로 | 잠금 단위 테스트 |
| --- | --- | --- |
| chunk_chat `_build_context` section embedding best-effort fallback | section try/except → build_section_context | test_section_chat_graceful_on_embedding_failure |
| chunk_chat_context `build_section_context_topk` budget cap | included 누적 budget 절단 | test_within_section_topk_picks_relevant_and_respects_budget |
| (신규 테스트) figure API / cross-lingual | image-anchor post / ko→en 검색 | test_figure_anchor_post_uses_figure_context, test_korean_question_retrieves_english_chunk(@llm) |

**grep 증거**: 위 4 test명이 test 파일에 실재. **회귀 0**: 730→733(+3 fast 신규만, @llm 1 deselected), 기존 green. section regression은 8d-2a 동작(무embedding section context)으로 복귀 보장(fallback) + 테스트 잠금.

## 5-D. 1.x 무손상
migration 0건(0007 재사용). 1.x block RAG/chat 무변경. prod 0004/blocks=49850 불변. 733 회귀 green.

## 5-E. 잔존 한계 (정직, 범위 외)
1. neighbor 재번역 + resize = **8d-2c**. cross-doc live(7 docs) = 8e(dev=doc7만; 머신+2-doc 단위 + @llm cross-lingual로 검증).
2. cross-lingual 테스트는 @llm(bge-m3 로드 → fast 제외; 모델 부재 시 skip). 결정적 머신은 seeded 벡터(733에 포함).
3. router 라인 coverage TestClient 미귀속, brute-force(≤50K), 동시 post 상속, jsdom CI provisioning(8e), 볼드/영어fallback(8e).

## 5-F. Scoring (100, self)
| Item | Score / Max | Evidence (R1 대비) |
| ---- | ----------- | -------- |
| 독창성 | 12 / 15 | chunk RAG 일반화 + figure=image-anchor + topk 별도 fn + best-effort RAG. query 의미 명시(section=question vec, cross-doc=anchor vec). (R1 11→ 계약 명확화) |
| 완결성 | 31 / 35 | figure(builder+**API**) + cross-doc(응답 refs) + **positive top-K** + cross-lingual(@llm) + 14 테스트. 차감: cross-doc live=8e, neighbor/resize=8d-2c. (R1 27→ gap 폐쇄) |
| 안정성 | 28 / 30 | 733 green + **section embedding-실패 fallback fix** + topk budget cap + graceful/no-write/mixed-dim 전부 잠금 + 1.x 무손상. 차감: context 81% 라인, 동시 post 상속. (R1 23→ regression fix 회복) |
| 확장성 | 17 / 20 | RAG 머신 재사용 + RelatedChunkRef + topk budget. 차감: brute-force 후속. (R1 15→ budget cap 회복) |
| **Total** | **88 / 100** | R1 실 결함 2개 fix + gap 3개 폐쇄. |

## 5-G. Self verdict
- [ ] PASS_CANDIDATE (≥95)
- [x] **submit to cross-verify Round 2 (최종, cap)** (self 88 < 95, 정직). R1 REJECT 실 결함 2개(section embedding 500, topk budget) fix + 테스트 잠금, gap 3개(positive topk·figure API·cross-lingual) 폐쇄. production 새 함수 0(가드/cap). 733 green, 1.x 무손상. 잔존은 8d-2c·8e·본질적. R2가 새 concrete 결함 없으면 push.
- [ ] FAIL → RE-PLAN
