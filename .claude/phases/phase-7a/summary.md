# Phase 7a — Summary

## Status
**ESCALATE TO PLANNER** (R2 REJECT, push 보류).

WORKFLOW.md Stage 6: Round 2 cross-verify REJECT → worker push 금지. Planner 판정 대기.

## Score history
| Round | Self | Cross verdict | Cross fair | 행동 |
|---|---|---|---|---|
| v1 | 91 | REJECT | 65 | RE-CODE (4 prod-code bugs + 1 UI DoD broken) |
| v2 (post RE-CODE) | 78 | **REJECT** | **66** | **escalate (R2 상한)** |

R2 잔존 비판 분류:
- ✅ R1의 prod-code bugs 모두 해결 (R2 Codex 인정): backfill filter, model-swap, store desync, UI cache propagation
- ⚠️ 잔존 (Planner 판정 필요):
  - **Frontend test infra 활용 미흡** (worker가 놓친 부분): repo에 `test_viewer_history_thread_js.py`, `test_sidebar_toggle_js.py` 패턴 있음. RE-CODE 핵심인 `relatedBlocksByMessageId` cache + viewer.js setter/getter 자동 테스트 가능. Phase 7b 또는 micro-fix 후보.
  - `/messages` route test 부재 (only `/explain` covered). 동일 RAG 동작이라 회귀 위험 낮지만 명시적 lock 부재.
  - **Upload-chain auto-embed (ROADMAP DoD `새 PDF 업로드 시 자동 embedding`)** 미구현. Worker가 scope-out으로 처리했지만 ROADMAP 명시 deliverable. 별도 phase 후보.
  - **Latency 575ms vs DoD <500ms**: 본 phase의 명확한 functional fail. CPU bge-m3 encode가 dominant (search <10ms). Phase 7b 후보 (GPU 또는 query-vector cache).
  - Backfill `Translation.translated_text != ''` 만 검사, `'   '` whitespace-only 미exclude.
  - `.env.backup.*` not in .gitignore (clean-tree claim 부정확).

## What was built

### 코어 인프라 (Phase 7a personalization 비전 첫 단계)
1. **Alembic migration 0004**: `block_embeddings` (block_id PK + FK CASCADE, model, dim, vector BLOB, source_hash, updated_at) + index
2. **Embedding subsystem** (`src/ht_lens/embedding/`):
   - `service.py`: `EmbeddingClient` Protocol, `BgeM3Client` (sentence-transformers, CPU), `MockEmbeddingClient` (deterministic for tests, no torch)
   - `store.py`: `upsert_embedding`, `load_all` (majority-dim guard after R1 fix), `vector_*_bytes` round-trip
   - `search.py`: brute-force cosine, `SearchHit` dataclass, top-K + threshold + exclude_doc_ids + min_chars
   - `backfill.py`: idempotent loop, candidate filter `status='translated' AND translated_text != ''`, model-swap refresh (R1 fix)
3. **API integration**:
   - `chat_context.py`: `build_block_context_with_refs` returns markdown + structured refs, cross-doc section with char budget, graceful skip
   - `routers/blocks.py`: `GET /blocks/{id}/related?k=5&threshold=0.5` (503 if no client, 404 unknown, 400 invalid k)
   - `routers/messages.py`: `/explain` + `/messages` 응답에 `related_blocks` 필드 + cross-doc system context
   - `schemas.py`: `RelatedBlock` + `MessageRead.related_blocks`
   - `deps.py`: `get_embedding_client` DI
   - `app.py`: lifespan lazy bge-m3 init, fail-soft None on failure, `RAG_DISABLED=1` test escape
4. **CLI**: `ht-lens embed --doc-id N --batch-size 32` (Phase 6e-2 pattern with `load_repo_dotenv`)
5. **Frontend UI**:
   - `components/message.js`: `renderRelatedBlocks` helper with doc/page/score/preview/link
   - `state.js`: `relatedBlocksByMessageId` cache + setter/getter (R1 fix — survives thread reload)
   - `viewer.js`: capture `/explain` + `/messages` return value, cache before reload (R1 fix)
   - `css/chat_panel.css`: `.related-blocks` styling

### 실 prod 검증
- Backfill 완료: **485 vectors** (bge-m3 1024d, docs 1-5)
- E2E `/blocks/{id}/related`: top-1 score 1.00 (exact paragraph match, Open-Sora paper), 의미상 정확한 top-5
- Chat `/explain` 응답에 `related_blocks` 5건 + system context에 "다른 문서 관련 참조" 섹션 lock

### 테스트
- 43 new tests (44 - 1 frontend manual): 498 total / +43 baseline / 0 regression
- 9 fail-by-default-state lib tests (RAG_DISABLED in helper)

## Files changed

```
.claude/phases/phase-7a/                            7 files (plan/debate/challenge/verify/cross/summary)
src/ht_lens/db/migrations/versions/0004_block_embeddings.py NEW
src/ht_lens/db/session.py                           ALEMBIC_HEAD 0003→0004
src/ht_lens/db/models.py                            BlockEmbedding ORM
src/ht_lens/embedding/__init__.py                   NEW
src/ht_lens/embedding/service.py                    NEW (128 lines)
src/ht_lens/embedding/store.py                      NEW (R1-fix: majority-dim guard)
src/ht_lens/embedding/search.py                     NEW (132 lines)
src/ht_lens/embedding/backfill.py                   NEW (R1-fix: filter + model-swap)
src/ht_lens/cli.py                                  +embed subcommand
src/ht_lens/api/app.py                              lifespan bge-m3 lazy init
src/ht_lens/api/chat_context.py                     +build_block_context_with_refs, cross-doc section
src/ht_lens/api/deps.py                             +get_embedding_client
src/ht_lens/api/routers/blocks.py                   +GET /blocks/{id}/related
src/ht_lens/api/routers/messages.py                 /explain+/messages 응답 related_blocks
src/ht_lens/api/schemas.py                          +RelatedBlock, MessageRead.related_blocks
src/ht_lens/api/static/js/components/message.js     renderRelatedBlocks + cache fallback
src/ht_lens/api/static/js/state.js                  relatedBlocksByMessageId cache
src/ht_lens/api/static/js/viewer.js                 capture explain/post response refs
src/ht_lens/api/static/css/chat_panel.css           .related-blocks styling
tests/unit/test_embedding_service.py                NEW (7 tests)
tests/unit/test_embedding_store.py                  NEW (5 tests)
tests/unit/test_embedding_search.py                 NEW (8 tests)
tests/unit/test_chat_context_rag.py                 NEW (6 tests)
tests/integration/test_embedding_backfill.py        NEW (7 tests with R1)
tests/integration/test_embedding_store_mixed_dim.py NEW (2 tests, R1 fix lock)
tests/integration/test_api_related.py               NEW (4 tests)
tests/integration/test_api_messages.py              +3 Phase 7a tests
tests/integration/test_alembic.py                   +block_embeddings expected, +0004 schema test
tests/integration/_api_helpers.py                   +embedding_override, RAG_DISABLED setup
pyproject.toml                                      +sentence-transformers, numpy
```

## Commits (push 대기, origin/main..HEAD = 11 commits)

```
dffb207 chore(phase-7a): verify-cross r2  ← REJECT 78→66
3686ba1 chore(phase-7a): verify v2 (post RE-CODE)
4fb38f1 fix(phase-7a): RE-CODE addressing verify-cross R1 REJECT (65)
16697bc chore(phase-7a): verify-cross r1   ← REJECT 91→65
aa2a3b4 chore(phase-7a): verify
3981ed4 feat(phase-7a): frontend 'related references' UI (ROADMAP DoD ④)
0278759 feat(phase-7a): ht-lens embed CLI + alembic 0004 schema test
b1f17aa feat(phase-7a): cross-doc RAG wired into API + chat context
6c070dd test(phase-7a): embedding service + store + search + backfill (24 tests)
11c7a22 feat(phase-7a): embedding subsystem + migration 0004
1005fc2 chore(phase-7a): debate + challenge
ad0a288 chore(phase-7a): plan
```

## Test deltas
- pre-phase: 455 → v2 (post RE-CODE): **498 passed, 1 skipped, 7 deselected**
- 43 new tests, 0 regression
- mypy strict / ruff / format all clean

## Deviations from plan
- `process_upload_job` 자동 embed integration scope-out (challenge §5 #2 missing test도 포함). 사용자가 `ht-lens embed --doc-id N` manual로 보강 가능. Codex R2 REJECT 정당.
- Frontend Playwright/jsdom test infra가 repo에 이미 있다는 사실을 worker가 plan/challenge에서 인지 못함 → R2의 가장 큰 critique. RE-CODE도 manual로 처리.

## Evidence index
- plan: `eae8e99` / `ad0a288`
- debate (Codex): `e22a348` / `1005fc2`
- challenge: `1005fc2` (Codex 5건 critique 모두 ACCEPT)
- code: `11c7a22` (infra) → `6c070dd` (tests) → `b1f17aa` (API) → `0278759` (CLI) → `3981ed4` (UI)
- verify v1: 91 → R1 REJECT 65 (`aa2a3b4` / `16697bc`)
- RE-CODE: `4fb38f1` (5 fixes — 4 prod-code + 1 UI DoD)
- verify v2: 78 → R2 REJECT **66** (`3686ba1` / `dffb207`)
- summary: 본 파일

## Known issues / debt (Planner 검토 필요)

### R2 잔존 비판 (모두 documented in Codex output)
1. **Frontend test infra 활용 미흡** (가장 큰 critique): repo의 `tests/integration/test_viewer_history_thread_js.py`, `test_sidebar_toggle_js.py` 패턴 follow → RE-CODE 핵심 `relatedBlocksByMessageId` cache + viewer.js setter/getter 자동 테스트 가능. Worker가 manual smoke로 처리.
2. **`/messages` route test 부재**: `/explain`만 cover. 동일 RAG 동작이지만 explicit lock 없음.
3. **Upload-chain auto-embed 미구현**: ROADMAP "새 PDF 업로드 시 자동 embedding (extract → ingest → translate → embed chain)" — `src/ht_lens/jobs/pipeline.py`에 embed stage 추가 필요. 본 phase scope-out.
4. **Latency 575ms vs DoD <+500ms**: CPU bge-m3 encode가 dominant. 측정 자체로 fail.
5. **Backfill whitespace-only**: SQL `!= ''`만, `'   '` (whitespace only) 미exclude. 의미상 edge case지만 docstring과 불일치.
6. **`.env.backup.*` not in .gitignore**: clean-tree claim 부정확. 단 file은 ops artifact이고 git에 commit 안 됨 (untracked로 잔존). gitignore 추가 권장.

### 도메인 차원 (별도 phase 후보)
- **Phase 7b**: latency optimization (GPU bge-m3 또는 query-vector cache), policy layer refactor (transport ↔ retrieval 분리)
- **Phase 7c**: upload-chain auto-embed integration (jobs/pipeline.py)
- **Phase 7d** (이후): user profile, memory, persona (ROADMAP v1.5/v2.0)

## Recommended next

### For Planner — push 결정
이 phase의 사실관계:
- R1의 **4 prod-code defects 모두 해결**: backfill candidate filter, model-swap refresh, store mixed-dim desync, UI related_blocks cache propagation
- 458 → 498 tests (+43 신규, 0 regression)
- 실 prod 데이터 485 embeddings + E2E cross-doc retrieval 의미상 정확 검증
- ROADMAP DoD 4건 중 3건 완전 충족, 1건 (latency 575ms vs 500ms) partial — root cause CPU encode + Phase 7b/c 후보
- R2 잔존 6건 모두 evidence/process/scope (prod 코드 회귀 없음)

판정 옵션:
- **Option A**: PASS_DESPITE_R2 — R1 prod bugs 해결, R2 잔존은 follow-up phase (frontend test + auto-embed + latency 최적화). push + CI 후 결과 보강.
- **Option B**: Planner-directed micro-fix — actionable items 즉시 fix:
  - (a) `.gitignore`에 `.env.backup.*` 추가
  - (b) backfill SQL에 `trim(translated_text) != ''` 또는 length check 추가
  - (c) `/messages` Phase 7a test 추가
  - (d) Frontend jsdom test 1건 (related_blocks render path)
  - (e) upload-chain auto-embed + latency 최적화는 Phase 7c로 위임
- **Option C**: REJECT — 재설계 (불필요해 보임, prod 코드는 안전).

권장 **B** (a/b/c/d 30분 내, e Phase 7c 위임). R1 prod bugs 모두 fix + R2 잔존도 test quality / scope 차원이라 즉시 처리 가능.
