# Phase 8b — Plan: Chunk 번역 (수식 placeholder 보호) + Chunk Embeddings

## Goal
8a chunk schema 위에 번역(qwen+v2_ko+수식 placeholder 보호)과 임베딩을 올린다. Phase 7a-2 concurrency 재사용, 1.x 무손상.

## Scope
**In**:
- chunk_translations / chunk_embeddings 테이블 (8a에서 8b로 연기됨) — migration 0006 additive
- 수식 placeholder 보호 모듈 (sandbox 검증 로직 인계) + byte-identical 복원 + 누락 복구
- chunk 번역 파이프라인 (7a-2 as_completed+Semaphore(7)+cache/dedup 재사용, Block->Chunk 일반화)
- chunk 임베딩 (bge-m3) — block 모듈 rename 아닌 chunk-parallel ADD (1.x 무손상)
- CLI translate-chunks, embed-chunks

**Out** (후속): reflow viewer(8c), chat/RAG-over-chunks 검색(8d), 7 docs 전체(8e). 8b는 임베딩 *생성*만, 검색은 1.x 유지.

## Approach

### 1) 테이블 (migration 0006, additive — 8a guardrail 동일)
- chunk_translations(chunk_id PK FK CASCADE, translated_text, caption_translated, model, status, cache_key, updated_at)
- chunk_embeddings(chunk_id PK FK CASCADE, model, dim, vector BLOB, source_hash, updated_at) — block_embeddings 동형
- 모델 ChunkTranslation/ChunkEmbedding 추가. ALEMBIC_HEAD 0005->0006. 기존 1.x + chunks 테이블 ALTER/DROP 0.

### 2) 수식 placeholder 보호 — src/ht_lens/translate/math_protect.py (신규)
sandbox translate_md_v2.py 검증 로직 인계 (byte-identical, KaTeX 에러 0):
- PH_OPEN/CLOSE = 'kk'/'jj' (⟦⟧). protect_math: $$...$$ 먼저(DOTALL), 그다음 (?<!\$)\$[^$\n]+?\$(?!\$) inline -> ⟦MATHi⟧.
- restore_math: placeholder 복원 + 누락 인덱스 리스트.
- 누락 복구: 번역 결과에 placeholder 사라지면 본문 끝에 주석으로 원수식 append. 수식 손실 0 보장.

### 3) chunk 번역 — src/ht_lens/translate/chunk_pipeline.py (신규)
7a-2 translate_document 동시성 머신(as_completed + Semaphore(7) + pending_cache/futures dedup) 일반화. type별:
- text/heading: protect -> llm.translate(protected, src, tgt) -> restore + 누락복구. cache_key=hash(content).
- equation: passthrough — translated_text=content(LaTeX), model='passthrough', LLM 0.
- image: caption 번역(protect 적용) -> caption_translated, translated_text="". cache_key=hash(caption).
- table: content를 text처럼 protect->번역 (셀=자연어, | 마크다운은 $ 아니라 보존). cache_key=hash(content).
- unknown: text처럼 보수적 처리.
- cache_key는 원본 content 기준(protect 전) -> 동일 chunk dedup 유지 = 5.66x 보존.

### 4) chunk 임베딩 — embedding/chunk_store.py + chunk_backfill.py (신규, ADD)
- block 모듈 rename 안 함: 1.x block_embeddings/search/chat_context이 이 브랜치에서도 살아있어야 함. vector_to_bytes/from_bytes/text_source_hash/EmbeddingClient 재사용.
- chunk_backfill: chunk.type in (text,heading) + 번역 존재 + content>=30자 -> chunk.content 임베딩, source_hash, idempotent.
- search.py 8b 미변경 — chunk 검색은 8d.

### 5) CLI
- ht-lens translate-chunks --doc-id N [--concurrency 7]
- ht-lens embed-chunks [--doc-id N]

## File-level changes
- db/models.py: ChunkTranslation, ChunkEmbedding (+ Chunk relationships)
- db/migrations/versions/0006_*.py: new (additive 2 테이블)
- db/session.py: ALEMBIC_HEAD 0005->0006
- translate/math_protect.py: new (sandbox 인계)
- translate/chunk_pipeline.py: new (7a-2 일반화)
- embedding/chunk_store.py, chunk_backfill.py: new
- cli.py: translate-chunks, embed-chunks
- tests/unit/test_math_protect.py: new
- tests/integration/test_chunk_translate.py, test_chunk_embed.py: new
- tests/integration/test_chunk_schema.py: extend (0006 additive diff)
- extract-mineru CLI 테스트 (8a 잔존, 결정 E)

## Dependencies (new)
없음 — qwen sglang/bge-m3 전부 재사용.

## Test strategy
- unit test_math_protect: inline/display 보호, byte-identical 복원(\operatorname*,\textstyle), 누락 검출+복구, edge(currency $5 단독=미보호, 중첩 $x=\$5$, escape, 다중, 줄바꿈).
- integration test_chunk_translate: text 번역+수식 보존, equation passthrough(LLM 0), image caption 번역, placeholder 잔존 0, cache dedup(동일 content 1회), 1.x translations 무변경. MockLLMClient 사용.
- integration test_chunk_embed: text/heading만, source_hash idempotent, 1.x block_embeddings 무변경. MockEmbeddingClient.
- test_chunk_schema: 0006 additive-only diff.
- regression: 619 green.

## DoD mapping (ROADMAP 8b)
- chunk 번역 + placeholder byte-identical: math_protect + chunk_pipeline; test_math_protect + test_chunk_translate placeholder 잔존 0 + E2E doc7.
- embedding 생성: chunk_backfill; test_chunk_embed + COUNT(chunk_embeddings).
- 7a-2 5.66x 적용: 동시성 머신 재사용; cache-dedup 테스트(동일 content 1 LLM 호출) + Semaphore(7).

## Plan 결정 항목 (확정 2026-05-30)
1. equation chunk: 확정 **passthrough** (LLM 0, LaTeX 그대로, model='passthrough').
2. table chunk: 확정 **content protect->번역** (text 동일 파이프라인; `|`는 미보호 안전; doc7 챕터 table 0개라 실검증은 8e).
3. 이웃 chunk context: 확정 **단독 번역**. ROADMAP "이웃 context" Deliverable은 5.66x DoD와 충돌 → DoD 우선. cache_key=hash(content) dedup 유지. "이웃 문맥"은 8d 채팅으로 재배치(ROADMAP wording 사용자 정정).
4. 8a 잔존 extract-mineru CLI 테스트: 확정 **8b에서 보강**.

## 위험 / 완화
- placeholder edge(currency $5 단독): inline regex가 짝 필요 -> 미보호(정상), 테스트 잠금.
- equation 중복 placeholder: equation은 passthrough라 protect 안 거침.
- 이웃 context가 cache dedup 깨뜨림: 단독 채택(결정 3).
- 1.x embedding 깨짐: block 모듈 rename 안 함, chunk-parallel ADD.
