# Phase 8e-4 — Summary

## Status
**PASS_CANDIDATE held at self 94 → escalated to Planner** (R2 = final cross-verify
round; R2 verdict DOWNGRADE → per push policy, no autonomous push).

## Score
- Self: **94 / 100** (v3, post-R2)
- Cross-verdict: R1 **DOWNGRADE ~89-91** → RE-CODE → R2 **DOWNGRADE 93-94**
  ("substantive R1 gaps mostly fixed; should NOT go back to RE-CODE for the
  original complaints" — residual was minor coverage + evidence scope, both now
  addressed).

## What was built
1. **Compare-mode continuous scroll-sync (right→left).** IntersectionObserver
   (jsdom-unverifiable, challenge §2.7) replaced with a deterministic
   `pickCurrentPage` (binary search over page-boundary offsets) + throttled
   `.pane--reflow` scroll-handler `initCompareSync`. One-way, last-page-cached,
   compare-mode-only, immediate sync on single→compare toggle, `teardown` on
   reload. **Boundary invalidation** on image `load`/`error` and window `resize`
   (lazy figures / layout shifts no longer cause wrong-page sync).
2. **Nested-image dedup (render-only).** `_drop_captionless_images_contained_by_captioned`
   drops a captionless image only when a same-page **captioned** image
   **strictly** contains it (doc1 Fig 28.18 = 3 panels nested in the full crop).
   Non-destructive: DB rows, `/v2/chunks/{id}/image`, and chat are untouched.
   Keeps side-by-side, standalone, equal-bbox, and malformed-bbox images.

## Files changed (vs main `b712a17`)
```
 src/ht_lens/api/routers/reflow.py                |  44 +     (dedup helpers + call site)
 src/ht_lens/api/static/js/reflow.js              | 126 +     (scroll-sync + invalidation)
 tests/integration/test_reflow_api.py             |  63 +     (endpoint dedup)
 tests/integration/test_reflow_compare_sync_js.py | 281 +     (7 jsdom event-path tests)
 tests/unit/test_reflow_dedup.py                  | 141 +     (9 dedup unit tests)
 5 files, +654 / -1
```
**0** DB / migration / model / 1.x-router / CLI changes (1.x prod fully untouched).

## Verification evidence
- Lint `ruff check src tests`: clean. Format `ruff format --check .`: 201 ok.
- Type `mypy src/`: **85 files, 0 issues**.
- Test `pytest -q`: **800 passed, 8 skipped, 0 failed** (3 snapshots).
- Live (in-process, prod 8086 untouched): doc1 images **15→12**, page2 = `[30]`,
  `/v2/chunks/27/image` 200 (non-destructive).

## Deviations from plan
- Plan's IntersectionObserver design was dropped at challenge time (PASS w/
  revisions A-R1..6) in favor of the deterministic scroll-handler — already
  ratified in challenge.md, not a new deviation.
- R2 added image-`error` invalidation (symmetric to `load`) — small scope
  addition beyond the plan's `load`/`resize`, justified by the existing
  `.fig-missing` fallback that also shifts offsets.

## Evidence index
- plan: `.claude/phases/phase-8e-4/plan.md` (`116dfc3`)
- debate: `.claude/phases/phase-8e-4/debate.md`
- challenge: `.claude/phases/phase-8e-4/challenge.md` (`7b9ff3c`)
- verify: `verify.md` v3 (`a4befeb`) — v1 `9dad445`, v2 `487bfee` in history
- verify-cross: `verify-cross.md` — R1 (in history), R2 `8872e75`

## Known issues / debt
- **CI green** is only confirmable after push (counted 0 in self-score's 안정성).
- No separate coverage gate this phase (project default only).
- Pixel-perfect bbox overlay still deferred (out of 8e-4 scope; follow-on).
- Boundary recompute is event-driven (load/error/resize/scroll); no
  ResizeObserver/font-load hook — acceptable for current docs, a future option.

## Planner decision needed (escalation)
R2 was a DOWNGRADE, so per CLAUDE.md/WORKFLOW.md push policy I did **not** push.
All R1 + R2 **functional** gaps are closed and test-locked; the gap between self
94 and the ≥95 bar is purely **pre-push evidence** (CI green) + no coverage gate.
**Recommendation: approve merge to main** (the residual resolves itself when CI
runs green on main). Awaiting Planner (Human) go/no-go before:
`PR/merge → GitHub CI → restart prod 8086 (pid 1526545) on new code`.

## Recommended next
- On approval: merge to main, confirm CI green, restart prod server.
- Follow-on: pixel-perfect bbox overlay; book2 full 1370p; bold (GPU decision).
