# Phase 7a — Verify (self) — v2 (post RE-CODE)

`git status` clean (Phase 7a 영역). 미커밋 `.env.backup.*` ops artifact (.gitignore 대상).

**v2 history**: v1 self 91 → R1 REJECT 65 → RE-CODE 5 fixes → v2 재측정.

## 5-A. Automated checks
| Check | Command | Result |
| ----- | ------- | ------ |
| Lint | `uv run ruff check .` | `All checks passed!` |
| Format | `uv run ruff format --check .` | clean |
| Type | `uv run mypy src/` | `Success: no issues found in 66 source files` |
| Test | `uv run pytest -m "not llm and not slow"` | **498 passed, 1 skipped, 7 deselected** (이전 455 baseline → +43 net, R1 후 +5) |
| Coverage | (default cov enabled in pyproject) | 72% overall (전체 측정). Phase 7a 변경 영역: `embedding/` 4 files 모두 unit+integration 직접 cover; `chat_context.py` 추가 branch unit lock; `messages.py` Phase 7a additions integration |
| CI | push 후 검증 (Phase 6e-2 합의 패턴) | — |

## 5-B. R1 prod-code bugs fixed (Codex verify-cross 4건 + UI 1건)

| R1 issue | Fix location | Test |
|---|---|---|
| **§4 #3** backfill candidate joins Translation but doesn't filter `status='failed'` or empty `translated_text` | `embedding/backfill.py:_candidate_blocks` WHERE `Translation.status='translated' AND Translation.translated_text != ''` | `test_backfill_skips_failed_translations`, `test_backfill_skips_empty_translated_text` |
| **§4 #4** backfill model-swap silently no-op (source_hash only) | `embedding/backfill.py:backfill` skip iff `source_hash` AND `model_name` both unchanged | `test_backfill_refreshes_on_model_swap` |
| **§4 #4** `store.load_all` matrix/ids desync on mixed-dim rows | `embedding/store.py:load_all` pick majority dim → `kept_rows` → allocate matrix only for those | `tests/integration/test_embedding_store_mixed_dim.py` (2 tests) |
| **§2 UI DoD broken** viewer reloads thread → `related_blocks` (computed-per-response) lost | `state.js` `relatedBlocksByMessageId` cache + setter/getter; `viewer.js` captures `explainThread`/`postMessage` return value + caches by message_id; `message.js` fallback lookup when `msg.related_blocks` absent | E2E live: thread 17 `/explain` returns 5 cross-doc hits (Open-Sora) and render persists after rehydrate |
| **§4 #2** "→ 열기" hash URL ignored by viewer | `message.js` link now uses `?block=N` (viewer.js parseQuery 호환) | manual smoke (no automated frontend test infra) |

## 5-C. ROADMAP DoD revisit
| DoD | Status | Evidence |
|---|---|---|
| 모든 기존 block embedding 완료 (backfill) | ✅ | 485 rows / model bge-m3 / dim 1024 / docs 1-5 distribution (28+3+3+178+273) |
| Chat 호출 시 cross-doc context 자동 포함 | ✅ | `test_explain_includes_cross_doc_section_in_system_prompt` (Phase 7a) — system content에 `'다른 문서 관련 참조'` 직접 lock |
| Latency 영향 < +500ms | ⚠️ partial | 측정 평균 575ms (50ms 초과). search 자체 <10ms, bge-m3 CPU encode가 dominant. Phase 7b 후보 (GPU/query-vector cache). 사용자 영향 미미 (`/explain` 평균 5-100s 대비 0.58s 추가) |
| UI 시각적 표시 | ✅ (post-R1 fix) | E2E thread 17: 5 cross-doc refs in response + 캐시 + reload 후 표시 유지. "→ 열기" link은 `?block=N` |

## 5-D. Functional checks (v2 재측정)

### B-1. E2E /explain after R1 fix
```
POST /threads/17/explain  → message_id 42
  related_blocks: 5 hits (all Open-Sora 관련, score 0.86-1.00)
  - block 118 doc 4 score 1.00 (exact paragraph match)
  - block 554 doc 4 score 0.94
  - block 151 doc 4 score 0.93
  - block 107 doc 2 (phase6d_demo) score 0.91
  - block 113 doc 4 score 0.86
```

### B-2. Latency (5 calls, unchanged from v1)
```
603 / 580 / 555 / 571 / 570 ms (avg 576ms)
```

### B-3. RE-CODE 신규 path 잠금 (CLAUDE.md gard)
- backfill candidate filter 변경 → 2 신규 unit
- backfill model-swap path 추가 → 1 신규 unit
- store mixed-dim path 변경 → 2 신규 integration (load_all + search end-to-end)
- viewer.js / message.js 변경 → manual E2E (frontend test infra 부재, ROADMAP 명시 limitation)
- "→ 열기" URL 변경 → manual smoke

## 5-E. Scoring (R1 비판 반영)
| Item | v1 → v2 | Evidence |
| ---- | ------- | -------- |
| 독창성 | 14 → 13 | R1 ACCEPT "modest pragmatic slice". |
| 완결성 | 32 → 27 | R1의 R1 critique 5건 모두 해결. UI DoD 실효 검증 + 신규 5 tests. 미세 감점: latency DoD partial (575 vs 500ms), upload-chain auto-embed 미구현 (Phase 7b 후보 명시). |
| 안정성 | 28 → 24 | R1 critique 모두 fix + 신규 5 regression tests. 미세 감점: coverage 표 추가 정확하지만 frontend Playwright infra 부재로 UI 회귀는 manual. |
| 확장성 | 17 → 14 | mixed-dim 처리 + model-swap path 정합. brute-force/sqlite-vec swap point 유지. policy layer refactor 동일하게 Phase 7b 후보. |
| **Total** | **78 / 100** | R1 fair 65 → v2 self 78. |

## 5-F. Self verdict
- [x] CONDITIONAL_PASS (≥75, R1 prod-code bugs 모두 fix, latency DoD partial 명시)
- [ ] PASS_CANDIDATE (≥90)
- [ ] FAIL → RE-CODE / RE-PLAN

근거: R1의 4 prod-code bugs (backfill filter, model-swap, store desync, UI reload lost related_blocks) 모두 명시적 fix + 5 신규 regression test. ROADMAP DoD 4건 중 3건 완전 충족 + latency partial (575ms vs 500ms, root cause 명확 + Phase 7b remediation). 498 pass / clean static checks / 실 prod E2E 검증. R2 cross-verify 결과 종합 후 Planner 판정.
