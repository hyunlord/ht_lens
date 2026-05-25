# Phase 7a — Plan

## Goal
Cross-document RAG: 모든 번역된 block을 vector embedding하고, chat 호출 시 다른 doc의 top-K relevant block을 context에 포함시켜 v1.5/v2.0 Personalization Agent 비전의 첫 단계를 구축한다.

## Context
Phase 6f-5 완료 후 prod 안정 (qwen3.6-27b + v2_ko prompt, doc 4/5 retranslate 완료, doc 6/7 ready_for_translation). 현재 chat context는 Phase 5의 same-page ±2 block (`build_block_context`) 만. Issue C (큰 틀 문맥) 의 same-doc 확장은 Phase 6h-1, 본 phase는 그 보다 가치 큰 cross-doc RAG.

ROADMAP Phase 7a로 정식 등재. 사용자 의사결정 5개 (4 + 1) 확인:

1. **Vector DB**: numpy brute-force (16K 이하 scale에서 deps-free 가장 안전)
2. **Embedding 모델**: BAAI/bge-m3 (1024d, multilingual)
3. **실행 위치**: CPU + transformers (qwen sglang GPU 점유 회피)
4. **Scope**: 번역된 block 478개 (original English 텍스트 indexing — cross-lingual retrieval은 bge-m3 강점)
5. **Retrieval**: Top-K=5, threshold=0.5, exclude same-doc, ingest pipeline에 자동 embed

## Scope
**In**:
- Alembic migration 0004: `block_embeddings` 테이블 (BLOB vector, metadata, source_hash). sqlite-vec virtual table은 numpy 채택 따라 생략.
- `src/ht_lens/embedding/service.py` (NEW): `EmbeddingClient` Protocol + `BgeM3Client` (transformers + bge-m3, CPU)
- `src/ht_lens/embedding/store.py` (NEW): `save_embedding`, `load_all_embeddings`, `delete_for_block`
- `src/ht_lens/embedding/search.py` (NEW): numpy brute-force cosine similarity. caching (in-memory matrix re-built on cache invalidation)
- `src/ht_lens/embedding/backfill.py` (NEW): CLI `python -m ht_lens.embedding.backfill --doc-id N` (또는 all-translated default)
- `src/ht_lens/api/chat_context.py` 확장: cross-doc RAG section 추가
- 새 API: `GET /blocks/{id}/related?k=5` (debugging/manual exploration)
- Ingest pipeline (Phase 6d upload chain `process_upload_job`) 에 embed 단계 추가 (translate 완료 후)
- 단위 테스트: embedding service mock, search top-K/threshold/exclude logic, store roundtrip, chat_context cross-doc
- 통합 테스트: backfill end-to-end, related endpoint, chat with RAG context

**Out**:
- Phase 6h-1 (same-doc section context)
- 다른 embedding 모델 swap UI
- Vector DB swap (sqlite-vec/chromadb 향후 scale-up phase)
- 사용자별 personalization (Phase 7b)
- doc 6 (12K) / doc 7 (36K) 강제 번역 트리거 (사용자 결정)
- Chat prompt 변경 (RAG context는 build_block_context 결과로 system message에 자동 주입)

## Approach

### 1. DB 모델
```python
# src/ht_lens/db/models.py 추가
class BlockEmbedding(Base):
    __tablename__ = "block_embeddings"
    block_id: int (PK, FK blocks.id ON DELETE CASCADE)
    model: str (e.g., "BAAI/bge-m3")
    dim: int (1024)
    vector: bytes (numpy float32 array bytes; len == dim * 4)
    source_hash: str (sha256 of source text — staleness check)
    source_kind: str ("original" or "translated"; 본 phase = "original")
    updated_at: datetime
```

Migration 0004 (현재 head 0003 이후) — `src/ht_lens/db/migrations/versions/0004_block_embeddings.py`. session.py 의 `ALEMBIC_HEAD = "0003"` → `"0004"`.

### 2. Embedding service
- `EmbeddingClient` Protocol: `model_name`, `dim`, `encode(texts) -> np.ndarray (N, dim) float32 L2-normalized`
- `BgeM3Client`: transformers AutoTokenizer + AutoModel, mean-pool last_hidden_state, L2 normalize. cache singleton (process-level)
- (테스트용) `MockEmbeddingClient`: deterministic vectors based on text hash

### 3. Search
- `Searcher` class: lazy-loads all rows from `block_embeddings` table on first call → in-memory `(block_id_array, matrix (N, dim))`
- `search(query_vector, top_k=5, threshold=0.5, exclude_block_ids=set(), exclude_doc_ids=set()) -> list[(block_id, score)]`
- Cosine similarity = dot product (vectors L2-normalized)
- Invalidation: 새 embedding 저장 시 in-memory cache reset (간단한 dirty flag)

### 4. chat_context.py 확장
기존 `build_block_context(session, block_id, radius=2) -> str`:
- 새 인자 `enable_cross_doc: bool = True`, `cross_doc_top_k: int = 5`, `cross_doc_threshold: float = 0.5`
- 같은 페이지 ±radius 결과 + cross-doc top-K 결과 두 section을 markdown 으로 결합
- cross-doc 가져올 query text: target block의 `original_text`
- exclude: target block의 doc_id (same doc 제외)
- Feature flag: env `RAG_ENABLE_CROSS_DOC=true|false` (default true), `RAG_TOP_K=5`, `RAG_THRESHOLD=0.5`

### 5. Backfill CLI
- `python -m ht_lens.embedding.backfill` (모든 번역된 block, source_kind="original")
- `--doc-id N` (특정 doc만)
- `--source original|translated` (default original)
- `--batch-size 16` (CPU 메모리)
- 이미 embedding 있는 block은 source_hash 비교 → 변경됐으면 갱신, 아니면 skip
- tqdm progress

### 6. Ingest pipeline 자동 embed
- `process_upload_job` (`src/ht_lens/jobs/pipeline.py`) 의 translate stage 완료 후 `await embed_translated_blocks(doc_id)` 호출
- Feature flag `ENABLE_AUTO_EMBED=true` (default true); skip 시 그냥 backfill CLI 의존
- 실패 시 job status는 'translated' 유지 (embed failure 가 transfer block 'translated' 깨지지 않음)

### 7. API
`src/ht_lens/api/routers/blocks.py` 에:
```python
@router.get("/{block_id}/related")
async def related_blocks(block_id, k: int = 5, threshold: float = 0.5) -> list[RelatedBlock]
```
- 같은 doc 제외
- bbox, page_num, doc_id, original/translated preview, similarity score 포함

## File-level changes
| Path | Action | Note |
| ---- | ------ | ---- |
| `src/ht_lens/db/migrations/versions/0004_block_embeddings.py` | NEW | block_embeddings 테이블 + index |
| `src/ht_lens/db/session.py` | MODIFY | `ALEMBIC_HEAD = "0004"` |
| `src/ht_lens/db/models.py` | MODIFY | `BlockEmbedding` ORM model |
| `src/ht_lens/embedding/__init__.py` | NEW | package marker |
| `src/ht_lens/embedding/service.py` | NEW | `EmbeddingClient` Protocol + `BgeM3Client` + `MockEmbeddingClient` |
| `src/ht_lens/embedding/store.py` | NEW | `save`, `delete`, `load_all` (numpy round-trip) |
| `src/ht_lens/embedding/search.py` | NEW | `Searcher`, top-K + threshold + exclude |
| `src/ht_lens/embedding/backfill.py` | NEW | CLI entry: `python -m ht_lens.embedding.backfill` |
| `src/ht_lens/api/chat_context.py` | MODIFY | cross-doc RAG section 추가 |
| `src/ht_lens/api/routers/blocks.py` | MODIFY | `/blocks/{id}/related` 추가 |
| `src/ht_lens/api/schemas.py` | MODIFY | `RelatedBlock` schema |
| `src/ht_lens/jobs/pipeline.py` | MODIFY | translate 완료 후 embed 단계 |
| `tests/unit/test_embedding_service.py` | NEW | MockEmbeddingClient shape/normalize |
| `tests/unit/test_embedding_store.py` | NEW | bytes round-trip, deletion |
| `tests/unit/test_embedding_search.py` | NEW | top-K, threshold, exclude same-doc |
| `tests/unit/test_chat_context_rag.py` | NEW | mock embedding/searcher로 cross-doc 결과 포함 |
| `tests/integration/test_api_related.py` | NEW | `/blocks/{id}/related` endpoint |
| `tests/integration/test_embedding_backfill.py` | NEW | CLI subprocess, source_hash 갱신 |

## Dependencies (new)
| Package | Why |
| ------- | --- |
| `sentence-transformers>=3` 또는 `transformers>=4.40` + `torch>=2.2` | bge-m3 실행 |
| `numpy>=1.26` | 이미 있음 (transformers 의존) |
| `tqdm` | backfill progress (이미 있음 가능) |

비-default 선택 안 함: sqlite-vec, chromadb, faiss — 의존성 감소.

## Test strategy
- **Unit (신규 ~15)**:
  - `MockEmbeddingClient`: deterministic encoding shape, L2 norm
  - `Searcher.search(...)`: top_k, threshold filter, exclude_doc_ids, exclude_block_ids 동작
  - `store.save/load`: bytes ↔ numpy float32 round-trip, source_hash 갱신
  - `chat_context`: enable_cross_doc=False → 기존 동작, True + mock searcher → cross-doc section 포함
- **Integration**:
  - `python -m ht_lens.embedding.backfill --doc-id 1` (작은 doc) — 실 embedding 호출 (5분 내 완료) OR MockEmbeddingClient 주입한 fake backfill
  - `GET /blocks/{id}/related` — mock searcher 주입 (DI), 같은 doc 제외, top-K 제한 검증
  - `POST /threads/{id}/explain` with mock chat LLM — context 에 cross-doc block markdown 포함 확인
- **회귀**: 기존 455 tests pass 유지. 특히 `test_api_chat_context.py` (Phase 5) 가 새 default `enable_cross_doc=True` 로 깨지면 → mock embedding (또는 RAG_ENABLE_CROSS_DOC=false) 로 격리

## DoD mapping
| DoD item | How to satisfy | Evidence plan |
| -------- | -------------- | ------------- |
| Migration 0004 적용 | session.py head 갱신 + ORM model + alembic 검증 | `alembic check` 통과 + 신규 테이블 schema 확인 |
| Embedding service 동작 | BgeM3Client 1-call smoke (1 sample → 1024d L2-norm vec) | unit test + live smoke (verify 단계) |
| Backfill 478 blocks | CLI 완료, DB row 478 | `SELECT COUNT(*) FROM block_embeddings` |
| Cross-doc search 정확 | top-K, threshold, same-doc exclude | unit test (mock) + 수동 5 sample relevance 평가 |
| Chat 통합 | `explain` 응답에 cross-doc context 반영 (markdown 안 보임 가능, 단 context_blocks API 또는 응답 변화 확인) | E2E test + 수동 |
| 회귀 0 | mypy / ruff / pytest -m "not llm and not slow" | verify |
| 자동 embed in ingest | upload job → embed 호출 | integration test or 수동 smoke (새 PDF 1건) |
| API related 작동 | `GET /blocks/{id}/related?k=5` 200 + 결과 검증 | integration test + 수동 curl |

## Risk / 주의
- **CPU bge-m3 latency**: chat 호출당 query embed 1회 ~200ms 추가. `/explain` 평균 4-7s 대비 미세. 단 P99 영향 모니터링.
- **bge-m3 2GB 다운로드**: 첫 실행 시. ~/.cache/huggingface 사용. CI 환경에선 mock 사용.
- **Numpy matrix in-memory**: 478 × 1024 × 4B = 2MB. doc 6/7 후 50K reached → 200MB. 메모리 OK, 단 lazy load + dirty flag로 관리.
- **In-memory cache 동시성**: ht_lens는 single-process uvicorn. multi-worker 시 cache 분리 issue (현 prod 무관).
- **Source hash staleness**: 사용자가 block original_text 수정 가능 (현 UI 없음 — 향후 추가 시 trigger). 본 phase scope 무관.
- **debate에서 다룰 질문**:
  - 본 phase의 search.py `Searcher`가 module-level singleton인지, ht_lens app.state에 inject인지
  - chat_context 의 cross-doc 결과를 system message에 어떻게 표현하는가 (markdown 헤더? json? )
  - feature flag `RAG_ENABLE_CROSS_DOC` 기본값 — true (활성)으로 하면 기존 chat 응답이 모두 영향. false로 safe rollout 후 별도 phase에서 activate?
  - backfill CLI가 chat 가동 중에 안전한지 (write lock issue, 단순 INSERT는 SQLite WAL 모드에서 OK)
