# Phase 8d-2b — Plan (chunk RAG 머신 + within-section top-K + cross-doc + figure 채팅 + neighbor 재번역 + resize)

## Goal
8d-2a 채팅 코어 위에 (1) chunk 벡터 검색 머신(Phase 7a block 일반화), (2) within-section top-K(큰 섹션 질문 정밀화), (3) cross-doc RAG refs, (4) figure 텍스트 채팅, (5) 짧은-chunk neighbor 재번역, (6) 사이드탭 resize+본문 연동을 추가한다. 8d의 마지막 조각.

## Stage 0 실측
- Phase 7a block RAG: `store.load_all`(BlockEmbedding→matrix, majority-dim), `search.search`(cosine, Block/Page join, threshold/min_chars/exclude), `lookup.get_or_encode_block_vector`(stored 재사용 else encode), `fetch_hit_details`. → **chunk 일반화 필요**(Chunk는 doc_id 직속, Page join 없음).
- 8b: `store.upsert_chunk_embedding`, `chunk_backfill.backfill_chunks`(model=client.model_name, source_hash) 존재. chunk **검색**(retrieval)은 미구현("revisit in 8d") → 본 phase.
- doc7 chunk_embeddings=0 → Stage 1 embed(진행 중). figure chunk: type=image, `caption`(영문, 일부 빈), `img_path`. 번역 caption은 ChunkTranslation.caption_translated.
- 결정(확정): neighbor 재번역 `content<60자`(수식밀집 제외, 6곳 영어 fallback은 8e); figure 이웃 `±2`; resize 영속 `sessionStorage`.

## Scope
**In (8d-2b)**
- chunk 검색 머신: `embedding/chunk_search.py`(신규) `ChunkSearchHit`/`search_chunks`/`fetch_chunk_hit_details`; `store.load_all_chunks`; `lookup.get_or_encode_chunk_vector`.
- within-section top-K: `build_section_context`에 optional `(question, embedding_client)` — 큰 섹션 over-budget 시 heading + `search_chunks(within=섹션 chunk ids)` top-K (8d-2a 절단 path 대체); 없으면 8d-2a 절단 fallback.
- cross-doc RAG: chunk_chat `post_message`가 context 후 `search_chunks(exclude_doc_ids={doc})` refs를 system에 추가 + 응답에 refs. dev=doc7만→empty(8e live); **2-doc fixture 단위검증**.
- figure 채팅: `build_figure_context(chunk_id, radius=2)` = caption(번역 우선) + ±2 이웃. anchor_type 추가 없이 **'chunk' anchor + chunk.type=='image' 분기**(_build_context). UI에 figure 선택 표시.
- neighbor 재번역: `translate-chunks --short-only`(CLI) = `content<60자` AND not math-dense chunk만 이웃(radius 1) context로 재번역, chunk_translations 덮어쓰기. `is_math_dense` 휴리스틱(수식 기호 비율).
- resize: chat 패널 좌측 경계 drag → 패널 너비 + 본문 우측 여백 연동(고정 패널, 그리드 불변), min/max, **sessionStorage**(localStorage 금지).

**Out**
- cross-doc **live**(7 docs)·실 볼드·수식밀집 영어 fallback 재번역 = 8e. 웹/논문 검색 = 8f. figure vision 모델(텍스트 기반만).

## Approach
### A. chunk 검색 머신 (Phase 7a 일반화)
- `load_all_chunks(session)` → (chunk_ids, matrix, models) (ChunkEmbedding, majority-dim; load_all 패턴).
- `search_chunks(session, *, query_vector, top_k, threshold, within_chunk_ids=None, exclude_doc_ids=None, exclude_chunk_ids=None, min_chars=50)`:
  - cosine = matrix @ q; Chunk.id/doc_id/content 메타 1쿼리; `within_chunk_ids`(섹션 범위 한정) + exclude + min_chars 필터; top_k. cross-doc=exclude_doc_ids={doc}; within-section=within_chunk_ids=섹션 ids.
- `get_or_encode_chunk_vector(session, client, chunk)`: ChunkEmbedding 조회(source_hash 일치 재사용) else encode(chunk.content).
- `fetch_chunk_hit_details` → {chunk_id:(Chunk,ChunkTranslation|None)}.

### B. within-section top-K (8d-2a 연결)
- `build_section_context(..., question=None, embedding_client=None)`: section over budget AND question+client 있으면 → heading + search_chunks(within=섹션 chunk ids, query=encode(question)) top-K; truncated=True+top_k 메타. 없으면 8d-2a 절단(graceful fallback). post_message가 question+client 주입.

### C. cross-doc RAG (chunk chat)
- chat_context `_build_cross_doc_refs`의 chunk 버전: `get_or_encode_chunk_vector(anchor)` → `search_chunks(exclude_doc_ids={doc})` → `ChunkRef`(doc/chunk/score/preview). post_message가 system에 "다른 문서 관련 참조" 추가 + 응답 refs. embedding_client None이면 graceful skip(8d-2a 동작 유지).

### D. figure 채팅
- `build_figure_context(session, chunk_id, radius=2)`: image chunk → `caption_translated or caption`(없으면 "(캡션 없음)") + ±2 이웃 chunk(라벨). `_build_context`가 anchor chunk.type=='image'면 호출. typed ChatContext.

### E. neighbor 재번역
- `is_math_dense(content)`: `$` 쌍/LaTeX 비율 ≥ 임계 → True(제외). `select_short_chunks(doc_id, <60, not math_dense)`. 재번역: 이웃(radius1) 포함 프롬프트 → 출력 c만 → ChunkTranslation 덮어쓰기(model 표시, cache_key 갱신). CLI `translate-chunks --short-only`.

### F. resize (frontend)
- reflow.css: 본문 컨테이너에 `--chat-w` 변수, 패널 open 시 `margin-right: var(--chat-w)`(고정 패널 공간 확보). `resize.js`(or chat.js): 패널 좌측 `.chat-resizer` drag → `--chat-w` 갱신(min 280/max 60vw), sessionStorage 저장/복원. KaTeX 리렌더 불필요(인라인 reflow).

## File-level changes
| Path | Action | Note |
| ---- | ------ | ---- |
| `src/ht_lens/embedding/store.py` | 수정 | `load_all_chunks` |
| `src/ht_lens/embedding/lookup.py` | 수정 | `get_or_encode_chunk_vector` |
| `src/ht_lens/embedding/chunk_search.py` | 신규 | `ChunkSearchHit`/`search_chunks`/`fetch_chunk_hit_details` |
| `src/ht_lens/api/chunk_chat_context.py` | 수정 | within-section top-K, `build_figure_context`, cross-doc refs helper |
| `src/ht_lens/api/routers/chunk_chat.py` | 수정 | post_message: figure 분기, top-K(question/client), cross-doc refs |
| `src/ht_lens/api/schemas.py` | 수정 | ChunkRelatedRef(응답 refs) |
| `src/ht_lens/translate/chunk_pipeline.py` + `cli.py` | 수정 | `--short-only` + neighbor context + `is_math_dense` |
| `src/ht_lens/api/static/js/chat.js` + `reflow.css`/`reflow.html` | 수정 | figure 선택 모드, resizer, sessionStorage |
| `tests/integration/test_chunk_search.py` 등 | 신규 | search(within/cross 2-doc), figure, neighbor, resize jsdom |

## Dependencies (new)
| Package | Why |
| ------- | --- |
| (없음) | numpy/sqlalchemy/qwen/bge-m3 기존. 신규 0. |

## Test strategy
- `search_chunks`: 2-doc fixture + seeded embeddings — within_chunk_ids 한정, cross-doc(exclude_doc_ids) 다른 doc hit, min_chars/threshold/exclude, empty corpus []. `get_or_encode_chunk_vector` stored 재사용 vs encode.
- within-section top-K: 큰 섹션 + question → heading + 관련 top-K(절단 아닌); client 없으면 8d-2a 절단 회귀.
- figure: image chunk → caption + ±2; caption 없는 figure graceful.
- neighbor 재번역: `<60자` non-math만 대상, math-dense 제외, 이웃 context 사용, 덮어쓰기, 긴 chunk 무변경.
- cross-doc refs: 2-doc → 다른 doc ref 반환; embedding_client None → graceful skip(refs=[]).
- resize jsdom: drag → `--chat-w`/margin 갱신, min/max clamp, sessionStorage 저장·복원.
- 회귀 720→720+신규. ruff/format/mypy clean. 1.x blocks=49850.

## DoD mapping (ROADMAP 8d: cross-doc RAG ④ + figure ② + 8d-2a 보강)
| DoD item | How | Evidence |
| --- | --- | --- |
| cross-doc RAG (chunk) | search_chunks(exclude_doc) + chat refs | test_chunk_search(cross) + chat refs test |
| figure 클릭→caption+이웃 설명 | build_figure_context + image anchor 분기 | test figure context + 사용자 |
| within-section top-K (큰 섹션) | build_section_context top-K | test top-K vs 절단 |
| neighbor 재번역 (짧은 조각) | --short-only + math 제외 | test neighbor + 사용자(where) |
| 사이드탭 resize+본문 연동 | resizer + --chat-w + sessionStorage | resize jsdom + 사용자 |
| 1.x 무손상 | embedding/chat 신규·확장만, 1.x 경로 무변경 | blocks=49850 + 720 회귀 |

## 위험 / 완화
- chunk 검색 block 정합/scale → load_all 패턴 재사용(majority-dim), brute-force(≤50K ok), 단위 패리티.
- within-section top-K가 8d-2a 절단 회귀 → client 없으면 절단 fallback + 양쪽 테스트.
- figure 이웃 판정(image 전후) → order_idx ±2(build_chunk_context 재사용).
- neighbor 재번역 덮어쓰기 손실 → `<60자` non-math만, math-dense 제외, 긴 chunk 무변경 테스트, idempotent cache_key.
- cross-doc dev-empty → 2-doc fixture 단위(머신 검증), live=8e 명시.
- resize 본문/KaTeX → 고정 패널+margin(그리드 불변), KaTeX 인라인 reflow(리렌더 불요), min/max clamp.
- anchor_type 불변(figure는 'chunk'+type 분기) → 0007 CHECK/migration 무변경.
