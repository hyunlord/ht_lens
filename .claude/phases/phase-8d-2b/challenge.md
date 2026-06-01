# Phase 8d-2b — Challenge

Codex의 scope 지적이 타당. Planner 결정: **범위 축소** — 8d-2b = chunk RAG 머신 + within-section top-K + cross-doc RAG + figure 채팅(ROADMAP 8d DoD: figure + cross-doc). **neighbor 재번역(--short-only) + resize → 8d-2c**. architectural/safety fix 전부 accept. PASS w/ revisions.

## Debate responses
### 1. Over-engineering
- **accept (scope, Planner 확정)**: `--short-only` 재번역 + resize → **8d-2c**(별도). 8d-2b는 검색/RAG 축으로 응집(backend RAG + figure). 회귀위험↓, verify 가벼움.
- **accept (top-K 분리)**: within-section top-K 로직을 `build_section_context`(순수 renderer)에 넣지 않음 → **별도 `build_section_context_topk`**(router가 호출). embedding 의존/실패는 router 계층에서 명시 처리. `build_section_context`(8d-2a 절단)는 불변.
- **partial (chunk_search 중복)**: block/chunk 격리상 일부 중복 OK. 단 chunk는 doc_id 직속(Page join 없음) + translated preview 다른 contract → 의도적 분리.

### 2. Hidden assumptions
- **accept**: Korean question → English chunk 임베딩 검색은 **bge-m3 cross-lingual** 의존. 명시 + 테스트(test_korean_question_retrieves_english_chunk)로 최소 relevance 검증. (bge-m3는 multilingual 설계.)
- **accept**: refs는 schema 응답 구성 필요 — `RelatedChunkRef`(chat_context RelatedBlockRef chunk 버전) + `ChunkMessageRead.related_chunks` 필드 + post_message가 schema 응답 반환.
- **accept**: `get_embedding_client` dep를 post_message에 주입; 테스트는 `make_test_client(embedding_override=...)`(기존). None이면 graceful skip(8d-2a 동작).
- **accept(8d-2c로 이연)**: `<60자` 판정 위험은 8d-2c 사안. 8d-2c에서 text-type만 + heading/equation/image/table 제외 + math-dense 제외.

### 3. Edge cases
- **accept**: within-section top-K 빈 hit(전부 <min_chars/embeddings 없음) → **8d-2a 절단 context fallback**. 테스트.
- **accept**: figure anchor는 content 빈 image — cross-doc/RAG query는 **caption+이웃 텍스트**로 합성(빈 content encode 금지). build_figure_context가 query 텍스트 제공.
- **accept**: `min_chars` block 기본 50은 학술 chunk(정의/식/캡션) 누락 → chunk search 기본 **20**(param화).
- **accept**: zero-vector/dim mismatch → get_or_encode_chunk_vector 빈 content는 zero-vector 반환(encode 안 함); search_chunks는 빈 corpus/하위 dim drop → 500 금지(chat은 graceful).
- **accept (중요)**: cross-doc search는 LLM-call→DB-write 순서 + rollback re-check(8d-2a orphan guard) **불변**. 검색/encode 실패는 best-effort skip(무쓰기 보장).

### 4. Alternative approaches
- **accept**: top-K는 `build_section_context_topk`(별도) 또는 router 호출 — chunk_chat_context는 순수 renderer 유지.
- **accept**: `RelatedChunkRef`(chunk_id/doc_id/filename/page_idx/score/original_preview/translated_preview) — refs를 **API 응답에 포함**(prompt만 아님).
- **accept**: figure RAG query = `caption_translated or caption` + 이웃 body 합성(빈 image content 아님).

### 5. Missing tests — accept (8d-2b 해당분)
1. test_chunk_post_message_returns_related_chunks (refs schema 응답).
2. test_chunk_chat_no_write_on_embedding_failure (검색/encode raise → LLM 전 → 무행; 또는 best-effort skip + 정상 응답).
3. test_figure_cross_doc_query_uses_caption_and_neighbors (빈 content image → caption/이웃 텍스트로 encode).
4. test_within_section_topk_empty_hits_falls_back_to_degraded (heading + 절단).
5. test_load_all_chunks_mixed_dim_keeps_ids_matrix_aligned (block 버그 미러).
6. test_korean_question_retrieves_english_chunk (cross-lingual 최소 검증).
7. test_search_chunks_within_and_cross (within_chunk_ids 한정 + exclude_doc_ids 2-doc).
- (test_short_only_* → 8d-2c.)

## Plan revisions (after debate)
- R1 **scope 축소**: 8d-2b = RAG 머신 + within-section top-K + cross-doc + figure. neighbor 재번역 + resize → 8d-2c.
- R2 top-K = `build_section_context_topk`(별도, router 호출); `build_section_context` 순수 불변.
- R3 `RelatedChunkRef` + `ChunkMessageRead.related_chunks` — refs API 응답 포함.
- R4 figure RAG query = caption+이웃(빈 content 금지).
- R5 cross-doc/encode 실패 = best-effort skip + 무쓰기 보장(LLM-call→write+rollback re-check 불변).
- R6 chunk search `min_chars` 기본 20(param), zero-vector/empty graceful(500 금지).
- R7 `get_embedding_client` post_message 주입; None graceful(8d-2a 동작).
- R8 load_all_chunks majority-dim + mixed-dim 테스트.
- R9 cross-lingual(bge-m3) 명시 + 테스트.
- R10 within-section empty-hit → 8d-2a 절단 fallback + 테스트.

## DoD checklist (ROADMAP 8d 잔여: figure ② + cross-doc RAG ④)
| DoD item | Status | Evidence |
| -------- | ------ | -------- |
| figure 클릭 → caption+이웃 설명 | 계획 | build_figure_context + image anchor 분기 + 테스트 |
| cross-doc RAG (chunk) | 계획 | search_chunks(exclude_doc) + refs 응답 + 2-doc 테스트 |
| within-section top-K (8d-2a 큰 섹션) | 계획 | build_section_context_topk + empty fallback 테스트 |
| 1.x 무손상 | 계획 | embedding/chat 신규·확장만, blocks=49850 + 720 회귀 |
| neighbor 재번역 / resize | 8d-2c | (범위 외) |

## Risk register
| Risk | L | I | Mitigation |
| ---- | - | - | ---------- |
| cross-lingual 검색 품질 | 중 | 중 | bge-m3 multilingual + relevance 테스트(R9) |
| top-K가 절단 path 회귀 | 중 | 중 | 별도 fn + empty fallback + 양쪽 테스트(R2,R10) |
| embedding 실패가 chat 깸 | 중 | 고 | best-effort skip + 무쓰기 보장(R5) |
| figure 빈 content encode | 중 | 중 | caption+이웃 query(R4) |
| min_chars로 학술 chunk 누락 | 중 | 중 | 기본 20 param(R6) |
| mixed-dim 행렬 비정렬 | 저 | 고 | majority-dim + 테스트(R8) |
| 1.x/8d-2a 회귀 | 저 | 고 | 신규/확장만, 720 회귀, orphan guard 불변 |

## Decision
- [x] **PASS → proceed to code** (R1–R10). 범위 축소(Planner) + Codex fix 전부 반영. 설계 유지 → RE-PLAN 불요.
- [ ] RE-PLAN
