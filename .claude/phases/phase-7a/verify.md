# Phase 7a — Verify (self) — v3 (post Planner-directed micro-fix)

`git status` clean. HEAD = `8a26377` (fix(phase-7a): R2 Planner-directed micro-fix).
`.env.backup.*` now in `.gitignore`; untracked rotation backups no longer surface.

**v3 history**: v1 self 91 → R1 REJECT 65 → RE-CODE 5 fixes → v2 self 78 →
R2 REJECT 66 → Planner Option B+ → v3 (5 cited gaps + 1 DoD gap closed).

## 5-A. Automated checks (current HEAD, all re-run after micro-fix)

| Check | Command | Result |
| ----- | ------- | ------ |
| Lint | `uv run ruff check .` | `All checks passed!` |
| Format | `uv run ruff format --check .` | `144 files already formatted` |
| Type | `uv run mypy src/` | `Success: no issues found in 66 source files` |
| Test (full) | `uv run pytest -q` | **508 passed, 8 skipped, 9 warnings in 201.91s** (v2 baseline 498 → +10 net, +5 backfill subset re-pass + 0 regression) |
| Pre-commit hooks | `git commit` ran them | `trim trailing whitespace / fix end of files / ruff / ruff format` all PASS |
| Backfill subset | `uv run pytest tests/integration/test_embedding_backfill.py -v` | **8 passed** (incl. new `test_backfill_excludes_whitespace_only_translations`) |
| Auto-embed subset | `uv run pytest tests/integration/test_pipeline_auto_embed.py -v` | **3 passed** |
| Frontend jsdom | `uv run pytest tests/integration/test_related_blocks_render_js.py -v` | **4 passed** |
| /messages Phase 7a | `uv run pytest tests/integration/test_api_messages.py -k "messages_includes_related or messages_related_blocks_empty"` | **2 passed** |
| CI | push 후 검증 (Phase 6e-2 합의 패턴) | — |

## 5-B. R2 critiques addressed (Planner Option B+)

| R2 issue | Fix location | Test |
|---|---|---|
| **§4 #1** RE-CODE state.js cache (`relatedBlocksByMessageId`, set/get) has no automated coverage | `tests/integration/test_related_blocks_render_js.py` | `test_set_and_get_related_blocks_round_trip`, `test_set_related_blocks_ignores_falsy_message_id` |
| **§2 ##2-3** renderer fall-back from cache + inline-vs-cache priority untested | `tests/integration/test_related_blocks_render_js.py` | `test_render_message_falls_back_to_cache_for_related_blocks`, `test_render_message_prefers_inline_related_blocks_over_cache` |
| **§2 #3 / §4 #2** /messages route has no Phase 7a coverage (only /explain) | `tests/integration/test_api_messages.py` (new 2 tests) | `test_messages_includes_related_blocks_when_embedding_available`, `test_messages_related_blocks_empty_when_no_embedding_client` |
| **§2 #5 / §4 (DoD)** upload-chain auto-embed missing from `jobs/pipeline.py` | `src/ht_lens/jobs/pipeline.py:208-235` (post-translate stage, graceful) | `tests/integration/test_pipeline_auto_embed.py` (3 tests: success, broken-client warning, RAG-disabled skip) |
| **§4 #3** backfill candidate filter only excludes exact `""`, not whitespace-only | `src/ht_lens/embedding/backfill.py:_candidate_blocks` (Python-side `.strip()` on translated_text — SQLite TRIM does not strip `\n\t`) | `test_backfill_excludes_whitespace_only_translations` |
| **§1 #2** `.env.backup.*` ops artifact not in `.gitignore` despite v2 verify claiming so | `.gitignore:43` | `git status` clean post-rotation |
| **§4 (deferred)** Latency 575ms vs <500ms DoD | NOT FIXED — explicitly deferred to Phase 7a-2 per Planner Option B+ | summary.md "Deviations" |

## 5-C. ROADMAP DoD revisit (post Option B+)

| DoD | Status | Evidence |
|---|---|---|
| 모든 기존 block embedding 완료 (backfill) | ✅ | 485 rows / bge-m3 / dim 1024 / docs 1-5 (v2 measurement, unchanged) |
| **새 PDF 업로드 시 자동 embedding (extract → ingest → translate → embed)** | ✅ (this round) | `jobs/pipeline.py` calls `embedding.backfill.backfill` after translate; `test_process_upload_job_auto_embeds_after_translate` locks the contract end-to-end with monkeypatched heavy stages |
| Chat 호출 시 cross-doc context 자동 포함 | ✅ | Unchanged — `test_explain_includes_cross_doc_section_in_system_prompt`; /messages now mirrored (`test_messages_includes_related_blocks_when_embedding_available`) |
| Latency 영향 < +500ms | ⚠️ partial (deferred) | 575ms unchanged; Phase 7a-2 follow-up |
| UI 시각적 표시 | ✅ (frontend test infra now exercised) | jsdom tests lock the cache + renderer fall-back paths that R2 flagged |

## 5-D. Regression check (CLAUDE.md RE-CODE guard)

Each R2 micro-fix introduces a new code path → matching unit/integration lock:

| New code path | Locking test |
|---|---|
| `src/ht_lens/jobs/pipeline.py` auto-embed branch (post-translate, after `translate_document`) | `test_process_upload_job_auto_embeds_after_translate` (success) + `test_process_upload_job_survives_embed_failure` (graceful) + `test_process_upload_job_skips_embed_when_client_unavailable` (RAG_DISABLED) |
| `src/ht_lens/jobs/pipeline.py` `embed_error` warning merge into `error_message` | `test_process_upload_job_survives_embed_failure` asserts `"임베딩 실패"` in `job.error_message` and `job.status == "done"` |
| `embedding/backfill.py` Python-side `.strip()` filter on `translated_text` | `test_backfill_excludes_whitespace_only_translations` asserts candidate count drops when `translated_text="   \n\t  "` |
| `test_related_blocks_render_js.py` jsdom harness for state.js + message.js | 4 tests directly invoke the new state.js exports + the renderer; locks `setRelatedBlocksForMessage(falsy)` no-op, cache-key isolation, fall-back, priority |

Existing R1 fix regions re-verified (498 baseline tests still pass; no regression in:
- `tests/integration/test_embedding_backfill.py` (8/8 — incl. R1 failed/empty translation + model-swap)
- `tests/integration/test_embedding_store_mixed_dim.py` (mixed-dim path)
- `tests/integration/test_api_messages.py` (existing /explain related_blocks + system-prompt section)

Grep verification for new symbols / functions in tests:
- `setRelatedBlocksForMessage` → `tests/integration/test_related_blocks_render_js.py:3 occurrences`
- `getRelatedBlocksForMessage` → `tests/integration/test_related_blocks_render_js.py:2 occurrences`
- `process_upload_job` auto-embed → `tests/integration/test_pipeline_auto_embed.py:3 invocations`
- `embed_error` field merge → asserted via `"임베딩 실패" in job.error_message`

## 5-E. Functional checks (v3 spot-check)

### B-1. /messages cross-doc smoke (new test surface)
```
POST /threads/{id}/messages  (body content="...")
  → 202 Accepted
  → body.related_blocks: [{block_id, doc_id, doc_filename, page_num, score, ...}]
  → same-doc blocks excluded; mirror doc cross-doc block present
```
Locked by `test_messages_includes_related_blocks_when_embedding_available`.

### B-2. Auto-embed end-to-end (new test surface)
```
process_upload_job(job_id, app)  (extract/ingest/translate/summarize monkeypatched)
  → job.status == "done"
  → BlockEmbedding rows for new doc_id: 2 (matches seeded translated blocks)
  → broken embedding client → job.status == "done", error_message contains "임베딩 실패"
  → embedding_client=None → job.status == "done", BlockEmbedding count == 0
```
Locked by `test_pipeline_auto_embed.py` × 3.

### B-3. Latency (unchanged from v2)
```
603 / 580 / 555 / 571 / 570 ms (avg 576ms) — Phase 7a-2 scope
```

### B-4. Frontend cache/renderer (new jsdom harness)
```
state.relatedBlocksByMessageId[7] = [...refs]
  getRelatedBlocksForMessage(7).length == 2  ✓
  getRelatedBlocksForMessage(999).length == 0  ✓
  setRelatedBlocksForMessage(undefined, [...]) → no entry written  ✓
renderMessage(container, {id:7, role:'assistant', content:'X'})  // no inline related_blocks
  → DOM has <section.related-blocks>; <a.related-open href="/static/viewer.html?doc=7&page=3&block=42">  ✓
renderMessage(container, {id:9, related_blocks:[fresh]})  // cache=stale
  → DOM link points at fresh.pdf, not stale.pdf  ✓
```

## 5-F. Scoring (R2 critique reflected, v3 self)

| Item | v2 → v3 | Evidence |
| ---- | ------- | -------- |
| 독창성 | 13 → 13 | Unchanged. Pragmatic slice; no scope creep. |
| 완결성 | 27 → 30 | ROADMAP DoD bullet "auto-embed on upload" now ✅ (was the missing R2 §4 deliverable). Latency still partial → not full marks. |
| 안정성 | 24 → 27 | Cache/renderer/messages paths all now have automated locks (R2 §2). RE-CODE regression guard applied per CLAUDE.md. |
| 확장성 | 14 → 14 | Unchanged. backfill filter is now consistent with what the docstring promised. |
| **Total** | **78 → 84** | R2 fair was 66 → v3 self 84 (closes 5/6 cited issues; latency deferred with Planner approval). |

## 5-G. Self verdict
- [x] PASS_CANDIDATE — R2 cited gaps closed with explicit tests; latency explicitly deferred to Phase 7a-2 with Planner approval; 508 pass / clean static checks
- [ ] CONDITIONAL_PASS
- [ ] FAIL

Round-cap (Phase 5-B): R2 verify-cross already ran; per WORKFLOW.md / CLAUDE.md, **R3 cross-verify is NOT invoked**. Planner-directed micro-fix lands as a single bundled commit; this verify v3 is the worker self-verification, push happens after.

Rationale: 5 of 6 R2 critiques closed with automated tests (jsdom + /messages + auto-embed + whitespace + gitignore). Item d (latency) explicitly out of scope per Planner Option B+ → Phase 7a-2. No new code path is left untested under CLAUDE.md regression rule.
