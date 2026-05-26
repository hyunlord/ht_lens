# Phase 7a — Summary (v2 final, post R2 Planner-directed micro-fix)

## Status
**PASS_CANDIDATE — push 완료 가정, CI green pending.**

R2 REJECT 66 → Planner Option B+ approved → micro-fix (5 items + 1 ROADMAP DoD)
→ verify v3 self 84 → push (R3 cross-verify NOT invoked, WORKFLOW.md Stage 5-B
round cap).

## Score history
| Round | Self | Cross verdict | Cross fair | 행동 |
|---|---|---|---|---|
| v1 | 91 | REJECT | 65 | RE-CODE (4 prod-code bugs + 1 UI DoD broken) |
| v2 (post RE-CODE) | 78 | REJECT | 66 | escalate (R2 round cap) |
| **v3 (post Planner micro-fix)** | **84** | — (round cap) | — | **push** |

## What changed in this round (R2 Planner Option B+)

Single bundled commit `8a26377` (fix(phase-7a): R2 Planner-directed micro-fix)
+ `2315b22` (chore(phase-7a): verify v3).

| R2 item | 분류 | 처리 | 결과 |
|---|---|---|---|
| (a) Frontend test infra unused for RE-CODE cache + renderer | test depth | ✅ `tests/integration/test_related_blocks_render_js.py` (4 jsdom tests) | locked |
| (b) `/messages` Phase 7a test missing (only `/explain` covered) | test depth | ✅ `tests/integration/test_api_messages.py` (+2 tests) | locked |
| (c) Upload-chain auto-embed missing (ROADMAP DoD bullet) | **DoD gap** | ✅ `src/ht_lens/jobs/pipeline.py` post-translate auto-embed + 3 tests | DoD closed |
| (d) Latency 575ms vs <500ms DoD | DoD partial | ⏭️ **deferred to Phase 7a-2** (Planner Option B+) | scope-out |
| (e) Backfill whitespace-only translations not excluded | edge case | ✅ Python-side `.strip()` filter (SQLite TRIM ≠ Python strip) + new test | locked |
| (f) `.env.backup.*` not in `.gitignore` | hygiene | ✅ `.gitignore:43` | clean |

Test deltas: 498 → **508 passed** (+10 new), 8 skipped, 0 regression.
Static checks: mypy strict / ruff / format / pre-commit hooks all clean.

## Why (d) latency is deferred to Phase 7a-2

- Measurement (v2): 5 runs avg **575ms** (target <500ms — exceeds by ~75ms).
- Root cause: bge-m3 CPU encode dominates; vector search itself <10ms.
- Mitigations require their own design pass:
  - GPU offload (contends with qwen sglang on shared GB10)
  - Per-query vector cache (LRU keyed by block_id+model)
  - Vector store swap (sqlite-vec / pgvector)
- Per Planner Option B+ this is a follow-up phase, not a micro-fix candidate.
- Action item for human: add Phase 7a-2 to ROADMAP.md (latency optimization).

## What was built (full Phase 7a scope, retained from v2)

### 코어 인프라
1. **Alembic migration 0004**: `block_embeddings` table (block_id PK + FK CASCADE, model, dim, vector BLOB, source_hash, updated_at) + index
2. **Embedding subsystem** (`src/ht_lens/embedding/`): service / store / search / backfill
3. **API integration**: `chat_context.build_block_context_with_refs`, `GET /blocks/{id}/related`, `/explain` + `/messages` `related_blocks` field, `RelatedBlock` schema, `get_embedding_client` DI, lifespan lazy bge-m3 init
4. **CLI**: `ht-lens embed --doc-id N --batch-size 32`
5. **Frontend UI**: `renderRelatedBlocks` + state.js cache + viewer.js capture
6. **Auto-embed (R2 micro-fix)**: `jobs/pipeline.py` post-translate stage with graceful degradation

### 실 prod 검증 (v2 measurement, unchanged)
- Backfill 완료: **485 vectors** (bge-m3 1024d, docs 1-5)
- E2E `/blocks/{id}/related`: top-1 score 1.00 (exact paragraph match, Open-Sora paper)
- Chat `/explain` 응답에 `related_blocks` 5건 + system context에 "다른 문서 관련 참조" section
- (New v3) `/messages` mirrors `/explain` related_blocks contract (test-locked)

### 테스트 (v3)
- 53 new tests cumulative (43 v2 + 10 v3 micro-fix), 0 regression
- 508 total / mypy strict / ruff / format clean

## Files changed in v3 (Planner micro-fix)

```
.gitignore                                          +1 line (.env.backup.*)
src/ht_lens/embedding/backfill.py                   +13 -3 (Python-side trim filter)
src/ht_lens/jobs/pipeline.py                        +34 -1 (auto-embed stage + warning merge)
tests/integration/test_api_messages.py              +107 (2 new /messages tests)
tests/integration/test_embedding_backfill.py        +33 (whitespace exclusion test)
tests/integration/test_pipeline_auto_embed.py       NEW (3 tests, 305 lines)
tests/integration/test_related_blocks_render_js.py  NEW (4 jsdom tests, 250 lines)
.claude/phases/phase-7a/verify.md                   v2 → v3 (full re-measurement)
.claude/phases/phase-7a/summary.md                  this file
```

## Commits (push 대상, origin/main..HEAD = 15 commits)

```
2315b22 chore(phase-7a): verify v3 (post Planner-directed micro-fix)
8a26377 fix(phase-7a): R2 Planner-directed micro-fix (Option B+)
88da071 chore(phase-7a): summary — ESCALATE TO PLANNER (R2 REJECT)
dffb207 chore(phase-7a): verify-cross r2
3686ba1 chore(phase-7a): verify v2 (post RE-CODE)
4fb38f1 fix(phase-7a): RE-CODE addressing verify-cross R1 REJECT (65)
16697bc chore(phase-7a): verify-cross r1
aa2a3b4 chore(phase-7a): verify
3981ed4 feat(phase-7a): frontend 'related references' UI (ROADMAP DoD ④)
0278759 feat(phase-7a): ht-lens embed CLI + alembic 0004 schema test
b1f17aa feat(phase-7a): cross-doc RAG wired into API + chat context
6c070dd test(phase-7a): embedding service + store + search + backfill (24 tests)
11c7a22 feat(phase-7a): embedding subsystem + migration 0004
1005fc2 chore(phase-7a): debate + challenge
ad0a288 chore(phase-7a): plan
```

## Deviations from plan
- v1 plan: upload-chain auto-embed scope-in but worker scoped out → R2 R2 critique.
  v3 micro-fix re-installs the deliverable per ROADMAP DoD.
- v1 plan: frontend covered by manual smoke (worker missed existing jsdom infra).
  v3 micro-fix adds 4 jsdom tests using the same harness as
  `test_render_markdown_js.py` / `test_viewer_history_thread_js.py`.
- Latency target (<500ms) not met (575ms). Explicitly carried to Phase 7a-2 per
  Planner Option B+ — human-driven ROADMAP update required (CLAUDE.md "ROADMAP
  수정 금지" rule applies to worker).

## Evidence index
- plan: `eae8e99` / `ad0a288`
- debate (Codex): `e22a348` / `1005fc2`
- challenge: `1005fc2`
- code v1: `11c7a22` → `6c070dd` → `b1f17aa` → `0278759` → `3981ed4`
- verify v1: 91 → R1 REJECT 65 (`aa2a3b4` / `16697bc`)
- RE-CODE R1: `4fb38f1`
- verify v2: 78 → R2 REJECT 66 (`3686ba1` / `dffb207`)
- summary v1 (escalate): `88da071`
- **R2 Planner micro-fix: `8a26377`**
- **verify v3: `2315b22`** (self 84, PASS_CANDIDATE)

## Recommended next (human / Planner)

1. **ROADMAP update** (human-driven per CLAUDE.md):
   - Mark Phase 7a ✅ 완료 (v1.5 cross-doc RAG milestone hit)
   - Add **Phase 7a-2**: latency optimization (target: bring `/explain` extra
     overhead under 500ms; explore GPU bge-m3, per-query vector cache, or
     vector-store swap)
2. **Doc 6 (textbook) translation**: now safe to start — the upload pipeline
   exercises the new auto-embed branch end-to-end, so a real new doc becomes
   the strongest integration test of the full chain.
3. **Phase 7b (User Profile + Persona)**: ready to enter once latency follow-up
   either lands or is parked.

## Known issues / debt (post v3)

- Latency 575ms (deferred to Phase 7a-2; not a defect, an optimization target).
- bge-m3 init still synchronous in lifespan (2GB model download on first
  cold start; fail-soft to None is in place but UX is a long pause on a fresh
  machine). Phase 7a-2 candidate alongside latency work.
- Upload-chain `embed_error` is surfaced into `jobs.error_message` but the
  viewer does not yet visually distinguish embed warnings from summarize
  warnings. Cosmetic, not blocking.

All other R2 critiques are closed by this micro-fix.
