# Phase 8d-2b — Verify (self)

마지막 code commit: `72a015a test(phase-8d-2b)`. 작성 직전 `git status` = clean. 2026-05-31. 범위 축소(Planner): chunk RAG 머신 + within-section top-K + cross-doc RAG + figure 채팅. neighbor 재번역 + resize = 8d-2c. **migration 없음**(0007 재사용) — 1.x/2.0 스키마 불변.

## 5-A. Automated checks (실측)
| Check | Command | Result |
| ----- | ------- | ------ |
| Lint | `uv run ruff check .` | All checks passed |
| Format | `uv run ruff format --check .` | 193 files already formatted |
| Type | `uv run mypy src` | Success: no issues found in 83 source files |
| Test | `uv run pytest -m "not llm and not slow" -q` (coverage 포함) | **730 passed, 1 skipped, 7 deselected in 577.19s** |
| Coverage | 타깃 측정 | `chunk_search.py` **90%**(직접), `chunk_chat_context.py` **81%**(cross-doc 빌더는 TestClient 경유 일부 미귀속) |
| CI | prototype-reflow — GitHub CI 미발생(8e 전) | n/a (jsdom CI provisioning 부채, 8d-1 등록) |

테스트 회계: 720 → **730** (+10): `test_chunk_search`(5) + `test_chunk_chat_context`(+2 figure/topk) + `test_chunk_chat_api`(+2 cross-doc/graceful) + `test_chat_ui_js`(+1 figure label).

## 5-B. Functional checks (DoD: ROADMAP 8d figure ② + cross-doc RAG ④ + 8d-2a top-K 연결)
### chunk RAG 머신 (Phase 7a block 일반화)
| 검사 | Evidence |
| --- | --- |
| search within-section + cross-doc | test_search_chunks_within_and_cross (within_chunk_ids 한정 / exclude_doc_ids 다른 doc) |
| mixed-dim ids↔matrix 정렬(block 버그 미러, R8) | test_load_all_chunks_mixed_dim_keeps_ids_matrix_aligned |
| get_or_encode_chunk_vector stored 재사용 | test_get_or_encode_chunk_vector_reuses_stored (encode 미호출) |
| graceful empty/dim-mismatch/zero/min_chars (R6) | test_search_chunks_graceful_*, test_search_chunks_empty_corpus (모두 [] 반환, 500 없음) |

### within-section top-K (8d-2a 큰 섹션 연결, R2/R10)
| 검사 | Evidence |
| --- | --- |
| 빈 hit → 8d-2a 절단 degraded fallback | test_within_section_topk_empty_hits_falls_back_to_degraded |
| (build_section_context_topk 별도 fn — chunk_chat_context 순수성 유지) | 코드 + router 호출 |

### cross-doc RAG (R3/R5)
| 검사 | Evidence |
| --- | --- |
| refs가 **API 응답**에 포함 (prompt만 아님) | test_post_message_returns_related_chunks (doc A anchor→doc B chunk, filename/page_idx) |
| embedding 실패 = best-effort skip, chat 무중단 + 무쓰기 보장 | test_chat_graceful_on_embedding_failure (202 + refs=[] + 메시지 영속) |
| dev cross-doc live-empty(doc7만) → 8e 7-doc 후 live | 2-doc fixture로 머신 검증; live 명시 |

### figure 채팅 (R4)
| 검사 | Evidence |
| --- | --- |
| caption(번역) + ±2 이웃, query=caption+이웃(빈 content 아님) | test_build_figure_context_caption_and_neighbors |
| figure 클릭 → image anchor('chunk' + type 분기, anchor_type 불변) | chunk_chat `_build_context` + test_figure_click_labels_as_figure(UI 라벨 "그림") |

### 라이브 (8086, dev doc7 56 embeddings)
- 신규 코드 라이브 서빙(reflow.html/chat.js 200). within-section top-K는 doc7 임베딩으로 live(큰 섹션 질문); cross-doc는 doc7만이라 empty(8e). figure 채팅은 image chunk 클릭으로 live.

## 5-C. 1.x 무손상
- **migration 0건**(0007 재사용). embedding/chat 신규·확장만(load_all_chunks/chunk_search/get_or_encode_chunk_vector + chunk_chat_context/router/schema/chat.js). 1.x block RAG(search.py/lookup.block/store.load_all) **무변경**. prod `data/ht_lens.db` 0004/blocks=49850 불변. 730 회귀 green(8d-2a 13 api + 기존 전부).

## 5-D. Coverage 정직 분해
- `chunk_search.py` 90%(직접 단위). `chunk_chat_context.py` 81% — figure/topk/section/parse 직접 테스트; cross-doc 빌더(`build_cross_doc_chunk_refs`)·refs 렌더는 API 테스트 경유(TestClient worker-thread 미귀속, 8c reflow.py 동일 artifact)나 test_post_message_returns_related_chunks가 응답 refs를 assert(실행 증명). router는 8d-2a와 동일 53%대(핸들러 본문 미귀속).

## 5-E. 잔존 한계 (정직, 범위 외)
1. neighbor 재번역(--short-only) + 사이드탭 resize = **8d-2c**.
2. cross-doc RAG **live**(7 docs) = 8e(dev=doc7만, 머신+2-doc 단위 검증). cross-lingual 품질(bge-m3 ko→en)은 multilingual 설계 + live eval(섹션Q 8d-2a 확인); 결정적 머신 테스트는 seeded 벡터.
3. char-budget=coarse, router 라인 coverage TestClient 미귀속, 동시 post stale-history(1.x 상속), jsdom CI provisioning(8e), 볼드/영어 fallback(8e).

## 5-F. Scoring (100, self)
| Item | Score / Max | Evidence |
| ---- | ----------- | -------- |
| 독창성 | 12 / 15 | Phase 7a block 머신의 chunk 일반화(중복 최소), figure=image-anchor 분기(anchor_type 불변), within-section top-K 별도 fn(순수성), best-effort cross-doc(무쓰기 보장). |
| 완결성 | 31 / 35 | figure + cross-doc(응답 refs) + within-section top-K DoD + 10 테스트. 차감: cross-doc live=8e, neighbor/resize=8d-2c. |
| 안정성 | 28 / 30 | 730 green + graceful(empty/dim/zero/min_chars)/no-write/mixed-dim 전부 잠금 + 1.x 무손상(migration 0). 차감: chunk_chat_context 81% 라인(cross-doc 빌더 TestClient), 동시 post 상속. |
| 확장성 | 17 / 20 | chunk RAG 머신 재사용 가능, RelatedChunkRef 계약, 8e가 cross-doc 채움. 차감: brute-force(≤50K ok, 그 이상은 후속). |
| **Total** | **88 / 100** | |

## 5-G. Self verdict
- [ ] PASS_CANDIDATE (≥95)
- [x] **submit to cross-verify Round 1** (self 88 < 95, 정직). 범위 축소(Planner) + Codex R1–R10 전부 반영(refs 응답·figure query·no-write·mixed-dim·min_chars·top-K 별도 fn·graceful). 10 테스트, 730 green, 1.x 무손상(migration 0). 잔존은 8d-2c(neighbor/resize)·8e(cross-doc live)·본질적(coverage TestClient·brute-force). R1이 새 concrete 결함 없으면 push.
- [ ] FAIL → RE-CODE / RE-PLAN
