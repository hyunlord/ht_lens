# Phase 8e-4 — Verify (self)

Scope: compare-mode continuous scroll-sync (right→left) + nested-image dedup
(captionless panels contained by a captioned full crop). Frontend + render-only;
**0 DB/migration/1.x changes**. Written after the last code commit
(`2b9b400`); tracked tree clean at verify time.

## 5-A. Automated checks
| Check    | Command | Result |
| -------- | ------- | ------ |
| Lint     | `uv run ruff check src tests` | All checks passed! |
| Format   | `uv run ruff format --check` (pre-commit ruff-format on commit) | Passed (cf87f69/2b9b400 hooks) |
| Type     | `uv run mypy src/ht_lens/api/routers/reflow.py` | Success: no issues found |
| Test     | `uv run pytest -q` | **795 passed, 8 skipped, 0 failed** (632.53s); 3 snapshots passed |
| Focused  | `pytest test_reflow_compare_sync_js.py test_reflow_viewer_js.py test_reflow_load_js.py test_reflow_dedup.py` | 23 passed |
| CI       | GitHub Actions (after merge to main) | pending push |

8 skipped are pre-existing env-conditional skips (e.g. GPU/network), not new.

## 5-B. Functional checks (live, in-process against `data/ht_lens_v2.db`)
ASGI lifespan + httpx ASGITransport (no port, prod 8086 untouched):

| Check | Evidence |
| ----- | -------- |
| reflow 200 | `GET /v2/documents/1/reflow` → 200 |
| Fig 28.18 dedup | doc1 image count **15 → 12**; page2 image ids = `[30]` (full crop); chunks 27/28/29 absent from reflow |
| non-destructive | `GET /v2/chunks/27/image` → **200 image/jpeg** (dropped panel still served; DB row intact) |
| dedup unit | `test_reflow_dedup.py` 9/9: panels drop, full+text kept; side-by-side / standalone / equal-bbox / malformed / cross-page kept |
| scroll-sync unit | `test_reflow_compare_sync_js.py` 3/3: `pickCurrentPage` binary search (0→p0, 150→p1, 350→p2, []→null); `syncNow` highlights left page **only in compare mode** (single mode = no left scroll); `teardown` detaches scroll handler (post-teardown scroll = no highlight) |
| reading-mode unaffected | sync gated on `layout.dataset.mode==="compare"`; single mode early-returns (unit-locked) |
| 1.x untouched | diff = `reflow.py` (new helpers) + `reflow.js` + 2 test files only; 0 DB/migration/model/1.x-router changes |

## 5-C. Regression check (RE-CODE guard — no RE-CODE this phase)
No RE-CODE round occurred (self verdict PASS_CANDIDATE on first pass). New code
paths introduced this phase are each locked by a named unit test:

| New code path (grep-able) | Locking test |
| ------------------------- | ------------ |
| `_strict_contains` | `test_strict_contains_true_for_nested_panel`, `test_strict_contains_false_for_equal_disjoint_inverted_malformed` |
| `_drop_captionless_images_contained_by_captioned` | `test_drops_nested_captionless_panels_keeps_captioned_full` + 6 keep-cases |
| `pickCurrentPage` | `test_pick_current_page_binary_search` |
| `initCompareSync` (`syncNow`/`recompute`/`teardown`) | `test_sync_scrolls_left_pane_only_in_compare_mode`, `test_teardown_detaches_scroll_handler` |

Existing reflow JS contracts (viewer/load) unbroken: `test_reflow_viewer_js.py`
+ `test_reflow_load_js.py` still green in the focused run (23 passed total).

## 5-D. Scoring (100, self-assessment)
| Item       | Score / Max | Evidence |
| ---------- | ----------- | -------- |
| 독창성     |   14 / 15   | IO→deterministic binary-search-on-page-offsets (jsdom-verifiable, challenge §2.7/§4.2); strict-containment dedup with malformed/equal-bbox guards |
| 완결성     |   34 / 35   | both DoD items done + live doc1 evidence; pixel-perfect bbox overlay still deferred (out of 8e-4 scope per plan) |
| 안정성     |   29 / 30   | 795 passed / 0 failed; non-destructive verified live; one-way sync (no feedback loop); malformed/inverted/None bbox never drops |
| 확장성     |   19 / 20   | `pickCurrentPage` pure + page-boundary-only tracking scales to 3338 chunks; helper composable; bbox overlay is a clean follow-on seam |
| **Total**  | **96 / 100**|          |

## 5-E. Self verdict
- [x] PASS_CANDIDATE (≥95) — proceed to cross-verify (Round 1)
- [ ] FAIL → RE-CODE
- [ ] FAIL → RE-PLAN
