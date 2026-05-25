# Phase 7a — Challenge

## Debate responses

### 1. Over-engineering (Codex)

> Plan adds a process-global matrix cache with invalidation before proving a plain brute-force pass is too slow. For 478 blocks, this is needless statefulness.

**ACCEPT.** 478 × 1024 × 4B = 2MB. 매 호출 load_all 비용 측정 후 결정. **Revised**: `Searcher` 클래스/cache 제거. `embedding/search.py`는 단일 함수 `search(session, query_vector, top_k, threshold, exclude_doc_ids)`로 단순화. SELECT all → numpy stack → dot product → top-K. doc 6/7 (50K reached) 후 latency 측정으로 cache 도입 결정.

> source_hash, source_kind, delete_for_block, --source, GET /blocks/{id}/related not required by ROADMAP DoD.

**PARTIAL ACCEPT.**
- `source_hash` **유지** (staleness check은 idempotent backfill의 핵심 — re-run 시 동일 block 재계산 회피). 단 1 column 추가 최소 침습.
- `source_kind` **제거**. 사용자 결정 "번역된 block (original text)" → 단일 source. 컬럼 추가 안 함.
- `delete_for_block` **제거**. CASCADE FK로 충분.
- `--source` CLI flag **제거**.
- `GET /blocks/{id}/related` **유지** — ROADMAP DoD ④ "다른 책의 관련 부분 시각적 표시" 위해 frontend가 사용할 API. 단 frontend 변경은 본 phase에 포함 (위 DoD ④).

> Dependency: sentence-transformers OR transformers — pick one.

**ACCEPT.** `sentence-transformers>=3` 단일 선택. 이유: bge-m3 정식 config (Pooling, Normalize) 자동 적용 → debate §2의 "mean-pooling 가설" 위험 제거.

### 2. Hidden assumptions (Codex)

> bge-m3 + generic mean-pooling: major unstated quality assumption.

**ACCEPT — sentence-transformers 채택으로 해결.** `SentenceTransformer("BAAI/bge-m3")`는 모델의 정식 modules.json (XLMRobertaModel → Pooling cls-token + Normalize)을 그대로 사용. AutoModel + manual pooling 안 함.

> jobs/pipeline.py status enum (pending/extracting/ingesting/translating/summarizing/done/failed) — "embed failure leaves status 'translated'" confuses Job vs Document status.

**ACCEPT — failure contract 명시.**
- Job.status 와 Document.status 구분.
- 새 job stage **embedding**: `translating → embedding → summarizing → done` 사이에 삽입 (또는 summarizing 후 별도).
- embedding 실패 시: Job.status = `failed`, error_message = "embed: <reason>". Document.status 는 그대로 `translated` 유지 (embedding은 부가 기능, document는 사용 가능).
- 결과: doc 사용은 정상, RAG context는 해당 doc 누락 (graceful degradation).

> SQLite WAL mode assumption — session.py says WAL tuning deferred.

**ACCEPT — concurrency story 삭제.** plan v2의 Risk 섹션에서 "WAL safe" 주장 제거. 대신 명시: "backfill CLI는 batch INSERT, default SQLite는 single writer — chat traffic과 동시 실행 시 짧은 write contention 발생 가능. doc 6/7 운영 시점에 WAL 도입 (별도 phase 후보)."

> plan의 debate questions가 미해결 — Stage 1 expects resolved.

**ACCEPT — 모두 결정.**
- **Singleton placement**: `app.state.embedding_client` (lifespan에서 lazy init). chat_context 함수는 `request.app.state.embedding_client` 받음.
- **Prompt format**: 기존 chat_context 마지막 `---` 다음 `## 다른 문서 관련 참조 (top-K)\n[Doc <filename> p.<n> b.<id>] <original 50자>... → <translated 50자>...\n...` 추가.
- **Default rollout**: `RAG_ENABLE_CROSS_DOC=true` (활성). 회귀 위험은 mock client + 회귀 테스트로 격리.
- **Runtime safety**: lifespan에서 client lazy init 실패 시 startup fail-closed (Phase 6e-2 패턴 일관). RAG search 자체 실패는 graceful fallback (cross-doc section 빠짐, 기존 same-doc context 그대로).

### 3. Edge cases (Codex)

> Empty / non-text blocks — Block.type includes image/table. Plan talks like all blocks embeddable.

**ACCEPT — filter 명시.**
- Backfill scope: `Block.type IN ('text', 'header') AND LENGTH(original_text.strip()) > 30` 만.
- Search 결과 post-filter도 동일.
- 사용자 결정 (번역된 block 478개) 와 정합 — translation 자체가 text/header만 처리.

> Fragment-heavy: same-doc exclude만으론 부족, 다른 doc의 짧은 fragment/boilerplate가 top-K 오염.

**ACCEPT — search post-filter.**
- search 결과를 다음 조건으로 post-filter:
  1. `LENGTH(block.original_text.strip()) >= 50` (짧은 fragment 제외)
  2. `block.type IN ('text', 'header')`
  3. similarity ≥ threshold (default 0.5)
- top_k 만족 못 하면 less results — 비어도 OK (graceful).

> Prompt size ignored — full thread history + system context, 5 cross-doc blocks could blow max_tokens.

**ACCEPT — context budget.**
- Cross-doc section: top-K block 각각 max 200자 (original 100 + translated 100)로 truncate. K=5 → 최대 ~1500자 추가.
- 기존 chat context typical ~500-1000자. 합쳐 2500자 ≈ 1000 tokens. chat max_tokens=4096 모델 context window (qwen 32K) 대비 무리 없음.
- `RAG_MAX_CHARS_PER_BLOCK=200` env로 tunable.

> Auto-embed on upload: bge-m3 2GB download — fresh machine first-run failure mode.

**ACCEPT — model preload + offline fallback.**
- lifespan에서 client init 시도. 다운로드 실패 시 startup 자체는 succeed (chat 기본 동작 보존), 대신 `app.state.embedding_client = None` + warning log.
- `build_block_context`는 client None이면 cross-doc section skip (graceful).
- Backfill CLI는 client None이면 명확히 fail.

### 4. Alternative approaches (Codex)

> If long-term vector layer: use sqlite-vec now (ROADMAP recommends).

**REJECT (defer to scale-up phase).** 사용자 결정 "numpy brute-force" (478개 scale 적합). ROADMAP은 50K 목표 명시했지만 **본 phase에서는 478만 embed**. doc 6/7 번역 후 50K reached 시점 별도 phase에서 sqlite-vec/faiss 스왑. 본 phase는 도입 위험 최소화 (deps 0 추가).

> If brute-force: simpler. No search.py cache, no /related, no source_kind/--source.

**MOSTLY ACCEPT** (위 §1).
- search.py cache 제거 ✓
- source_kind/--source 제거 ✓
- `/blocks/{id}/related` **유지** — ROADMAP DoD ④ "다른 책 관련 부분 UI" 위해 필요.

> backfill CLI should follow ht_lens.cli pattern (Phase 6e-2 lesson).

**ACCEPT — typer 통합.**
- `src/ht_lens/cli.py`에 `embed` subcommand 추가 (`ht-lens embed --doc-id N`).
- 새 module `ht_lens.embedding.backfill` 함수만 expose, CLI는 cli.py에 inline.
- Phase 6e-2 `_load_repo_dotenv` 인프라 자동 적용.

### 5. Missing tests (Codex)

**모두 ACCEPT — DoD lock-in.**

1. **UI 시각적 표시 (ROADMAP DoD ④)**: frontend 변경 + 테스트 추가.
   - `src/ht_lens/api/static/viewer.html` chat 패널에 "관련 참조" 섹션. AI 응답 위/아래에 cross-doc block 링크 표시 (block_id → 해당 doc viewer 새 탭).
   - `/threads/{id}/explain` 응답에 새 필드 `related_blocks: list[RelatedBlock]` (의미: 응답 생성 시 참조한 cross-doc blocks).
   - Test: `tests/integration/test_api_messages.py` 확장 — `RecordingMockLLM` 으로 system content에 cross-doc section 존재 + 응답 schema에 related_blocks 필드 확인.
   - Frontend test 자동화는 본 phase scope 외 (Playwright infra 없음) — 수동 smoke screenshot으로 verify.

2. **Latency benchmark (ROADMAP DoD ③ <+500ms)**:
   - `tests/integration/test_rag_latency.py` 신규. mock embedding client (deterministic instant) 사용해서 brute-force search 자체 latency 측정. 478 × 1024 dot product → numpy로 <50ms 예상.
   - Verify 단계 manual benchmark: real bge-m3 client + 실 478 row → query 1회 latency 측정. CPU bge-m3 query embed ~200ms + search <50ms ≈ <250ms.
   - Assert `< 500ms` end-to-end.

3. **Upload pipeline embed failure test**:
   - `tests/integration/test_api_jobs.py` (또는 새 파일) — mock embedding client가 raise. Job.status='failed', Document.status='translated' 보존, error_message 'embed:' prefix.

4. **Alembic test 확장**:
   - `tests/integration/test_alembic.py`에 0004 migration 검증 (upgrade → block_embeddings 존재, downgrade → 제거).

5. **Backfill 명시 테스트**:
   - `tests/integration/test_embedding_backfill.py`: mock client로 idempotent rerun (source_hash 변경 없으면 skip), source 변경 시 re-embed, empty/non-text block skip.

## Plan revisions (after debate) — summary

### Cuts
- `Searcher` class + matrix cache → 단일 함수
- `source_kind` 컬럼 + `--source` flag
- `delete_for_block` (CASCADE FK로 충분)
- "WAL safe" assumption
- 미해결 design questions

### Adds
- sentence-transformers 단일 의존성 (bge-m3 정식 pooling)
- Block type/length filter (text/header, ≥50 char search post-filter, >30 char backfill scope)
- Per-block char budget (`RAG_MAX_CHARS_PER_BLOCK=200`)
- Frontend chat panel "관련 참조" 섹션 + `/explain` 응답 schema 확장
- Latency benchmark test (DoD ③)
- Failure-path test (upload pipeline)
- Alembic 0004 migration 테스트
- Idempotent backfill test
- typer `ht-lens embed` subcommand (cli.py 통합, Phase 6e-2 인프라 재사용)
- `app.state.embedding_client` lifespan singleton (None on init failure → graceful)
- Job state machine `embedding` 단계 추가 (translating → embedding → done)

## File-level changes (revised)
| Path | Action | Note |
| ---- | ------ | ---- |
| `src/ht_lens/db/migrations/versions/0004_block_embeddings.py` | NEW | block_id PK, model, dim, vector BLOB, source_hash, updated_at |
| `src/ht_lens/db/session.py` | MODIFY | `ALEMBIC_HEAD = "0004"` |
| `src/ht_lens/db/models.py` | MODIFY | `BlockEmbedding` ORM |
| `src/ht_lens/embedding/__init__.py` | NEW | |
| `src/ht_lens/embedding/service.py` | NEW | `EmbeddingClient` Protocol, `BgeM3Client` (sentence-transformers, CPU), `MockEmbeddingClient` |
| `src/ht_lens/embedding/store.py` | NEW | `save(session, block_id, vec, model, source_hash)`, `load_all(session) -> (block_ids, matrix)` |
| `src/ht_lens/embedding/search.py` | NEW | `search(session, query_vec, top_k, threshold, exclude_doc_ids, min_chars=50)` — 매 호출 load + dot |
| `src/ht_lens/embedding/backfill.py` | NEW | 함수 `backfill_doc(session, client, doc_id, batch_size=16)`, `backfill_all` |
| `src/ht_lens/cli.py` | MODIFY | `ht-lens embed --doc-id N --all` typer subcommand |
| `src/ht_lens/api/app.py` | MODIFY | lifespan에서 `app.state.embedding_client` lazy init (실패 시 None) |
| `src/ht_lens/api/chat_context.py` | MODIFY | cross-doc section + char budget |
| `src/ht_lens/api/routers/messages.py` | MODIFY | `/explain`, `/messages` 응답에 `related_blocks` 필드 |
| `src/ht_lens/api/routers/blocks.py` | MODIFY | `GET /blocks/{id}/related` |
| `src/ht_lens/api/schemas.py` | MODIFY | `RelatedBlock` schema |
| `src/ht_lens/api/static/viewer.html` | MODIFY | chat 패널 "관련 참조" 섹션 |
| `src/ht_lens/api/static/js/viewer.js` 또는 chat js | MODIFY | related_blocks 렌더링 |
| `src/ht_lens/jobs/pipeline.py` | MODIFY | translating → embedding → done state machine, embed 실패 graceful |
| `tests/unit/test_embedding_service.py` | NEW | MockEmbeddingClient shape/normalize |
| `tests/unit/test_embedding_store.py` | NEW | bytes round-trip |
| `tests/unit/test_embedding_search.py` | NEW | top-K, threshold, exclude doc, min_chars filter |
| `tests/unit/test_chat_context_rag.py` | NEW | mock embed/search → cross-doc section 포함 |
| `tests/integration/test_alembic.py` | EXTEND | 0004 up/down |
| `tests/integration/test_embedding_backfill.py` | NEW | idempotent rerun, source_hash refresh, skip image/table/short |
| `tests/integration/test_api_related.py` | NEW | `/blocks/{id}/related` 200, exclude same doc, top-K |
| `tests/integration/test_api_messages.py` | EXTEND | RecordingMockLLM `system` 인자에 cross-doc section + `related_blocks` 응답 schema |
| `tests/integration/test_api_jobs.py` | EXTEND | embed failure: Job.status=failed, Document.status=translated 보존 |
| `tests/integration/test_rag_latency.py` | NEW | search latency <50ms with 1000 mock vectors |

## DoD checklist (vs ROADMAP)
| ROADMAP DoD | Status | Evidence plan |
| ----------- | ------ | ------------- |
| 모든 기존 block embedding 완료 (backfill) | planned | `SELECT COUNT(*) FROM block_embeddings` ≥ 478 |
| Chat 호출 시 cross-doc context 자동 포함 | planned | `test_api_messages.py` system content + 수동 `/explain` |
| Latency 영향 < +500ms | planned | benchmark test + verify 단계 real timing |
| UI 시각적 표시 | planned | frontend chat 패널 변경 + 수동 screenshot |

## Risk register (revised)
| Risk | Likelihood | Impact | Mitigation |
| ---- | ---------- | ------ | ---------- |
| bge-m3 2GB 다운로드 첫 실행 실패 | Mid | Low | lifespan client None fallback, manual preload 명시 |
| 478 sample 너무 작아 cross-doc 결과 부실 | High | Mid | doc 6/7 후 재평가. 본 phase 는 인프라 검증 |
| 짧은 fragment top-K 오염 | Mid | Mid | min_chars=50 post-filter |
| Frontend 시각적 표시 testing 자동화 부재 | High | Low | 수동 screenshot verify, 향후 Playwright phase |
| CPU embed latency P99 outlier | Mid | Mid | 본 phase 끝에 percentile 측정 |
| Job state machine 변경이 기존 upload 회귀 | Low | High | `test_api_jobs.py` 신규 + 기존 보존 |

## Decision
- [x] PASS → proceed to code
- [ ] RE-PLAN

근거: Codex 모든 critique ACCEPT 또는 명시적 defer. ROADMAP DoD 4건 모두 evidence 계획. sentence-transformers 단일 채택으로 pooling 가설 위험 제거. 26 file 변경 (3 frontend, 16 src/test) — 중간 규모이지만 phase 가치 (v1.5/v2.0 비전 첫 단계) 정당. 코딩 진행.
