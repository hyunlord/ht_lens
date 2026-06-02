# Phase 8e-4 — Verify (self) — v2 (post RE-CODE, after cross-verify R1 DOWNGRADE)

Scope: compare-mode continuous scroll-sync (right→left) + nested-image dedup.
Frontend + render-only; **0 DB/migration/1.x changes**. v1 (self 96) was
written at `9dad445`; Codex R1 returned **DOWNGRADE** (~89-91) on 4 gaps —
all addressed by RE-CODE (`d77b1b5` fix, `caf118e` tests). This v2 reflects the
post-RE-CODE tree (HEAD `caf118e`); tracked tree clean at verify time.

## R1 findings → resolution
| R1 issue | Resolution | Lock |
| -------- | ---------- | ---- |
| §4#1 cached boundaries go stale after lazy-image load / resize | `dirty` flag + `invalidate()` wired to window `resize` + per-image `load` (torn down with handler); next sync recomputes, invalidate self-schedules a sync | `test_image_load_invalidates_stale_boundaries` |
| §4#2 real continuous-scroll path (onScroll→rAF→syncNow) untested | new test dispatches a **real** `scroll` Event + flushes rAF | `test_real_scroll_event_drives_sync_only_in_compare_mode` |
| §4#4 "reading-mode unaffected" not proven through the handler | same test asserts single-mode scroll Event = no left highlight | (same) |
| §4#3 dedup not locked at the API boundary | hermetic `get_reflow` endpoint test: captioned crop survives, panels dropped, `/v2/chunks/{id}/image` still 200 | `test_reflow_dedup_drops_nested_panels_at_endpoint` |

## 5-A. Automated checks
| Check    | Command | Result |
| -------- | ------- | ------ |
| Lint     | `uv run ruff check src tests` | All checks passed! |
| Format   | `uv run ruff format` (pre-commit ruff-format on each commit) | Passed (reformatted endpoint test committed in caf118e) |
| Type     | `uv run mypy src/ht_lens/api/routers/reflow.py` | Success: no issues found |
| Test     | `uv run pytest -q` | **798 passed, 8 skipped, 0 failed** (566.97s); 3 snapshots passed |
| Focused  | reflow compare-sync + api + dedup + viewer + load | 38 passed |
| CI       | GitHub Actions (after merge to main) | pending push |

798 = v1's 795 + 3 new R1 tests. 8 skipped are pre-existing env-conditional skips.

## 5-B. Functional checks (live, in-process against `data/ht_lens_v2.db`)
ASGI lifespan + httpx ASGITransport (no port; prod 8086 untouched):

| Check | Evidence |
| ----- | -------- |
| reflow 200 | `GET /v2/documents/1/reflow` → 200 |
| Fig 28.18 dedup | doc1 image count **15 → 12**; page2 image ids = `[30]`; chunks 27/28/29 absent |
| non-destructive | `GET /v2/chunks/27/image` → **200 image/jpeg** (DB row intact) |
| dedup helper unit | `test_reflow_dedup.py` 9/9 (panels drop; side-by-side/standalone/equal/malformed/cross-page kept) |
| dedup endpoint | `test_reflow_dedup_drops_nested_panels_at_endpoint` — seeded nested images, response drops panels, `/image` 200 |
| scroll-sync pure | `pickCurrentPage` 0→p0 / 150→p1 / 350→p2 / []→null |
| scroll-sync handler | real `scroll` Event syncs left pane in compare mode; **inert in single mode**; `teardown` detaches |
| stale-offset guard | image `load` invalidates → recompute → correct page (1, not stale 2) |
| reading-mode unaffected | sync gated on `mode==="compare"`; single-mode scroll Event proven inert |
| 1.x untouched | diff = `reflow.py` helper + `reflow.js` + 2 test files; 0 DB/migration/model/1.x-router changes |

## 5-C. Regression check (RE-CODE guard)
RE-CODE (`d77b1b5`/`caf118e`) added the `dirty`/`invalidate` path and 3 tests.
Each new code path is locked by a named test (grep-able symbol → test):

| New code path (grep-able) | Locking test |
| ------------------------- | ------------ |
| `dirty` / `invalidate` / window-resize + img-load listeners (`reflow.js`) | `test_image_load_invalidates_stale_boundaries`, `test_real_scroll_event_drives_sync_only_in_compare_mode` |
| `onScroll` → rAF → `syncNow` event wiring | `test_real_scroll_event_drives_sync_only_in_compare_mode` |
| `teardown` (now also removes resize + img-load listeners) | `test_teardown_detaches_scroll_handler` |
| `_strict_contains` / `_drop_captionless_images_contained_by_captioned` | 9 unit + `test_reflow_dedup_drops_nested_panels_at_endpoint` |

Regression of R1-fixed areas: dedup helper tests + endpoint test both green;
existing reflow contracts (`test_reflow_viewer_js.py`, `test_reflow_load_js.py`,
all prior `test_reflow_api.py`) unbroken (38 focused passed; 798 full). No
public contract change (CLI/API exit codes, `/v2` routes, 1.x routes unchanged).

## 5-D. Scoring (100, self-assessment)
| Item       | Score / Max | Evidence |
| ---------- | ----------- | -------- |
| 독창성     |   14 / 15   | IO→deterministic binary search (jsdom-verifiable); strict-containment dedup; lazy boundary invalidation lifecycle now complete |
| 완결성     |   33 / 35   | both DoD done + live doc1 + endpoint + event-path tests; pixel-perfect bbox overlay still deferred (out of 8e-4 scope) |
| 안정성     |   30 / 30   | 798 passed/0 failed; stale-offset failure mode closed; event path + single-mode-inert + non-destructive all locked; one-way (no loop) |
| 확장성     |   19 / 20   | pure `pickCurrentPage` + page-boundary-only tracking + invalidation hooks (load/resize) scale to 3338 chunks; bbox overlay clean follow-on |
| **Total**  | **96 / 100**|          |

## 5-E. Self verdict
- [x] PASS_CANDIDATE (≥95) — R1 gaps closed; proceed to cross-verify Round 2 (final)
- [ ] FAIL → RE-CODE
- [ ] FAIL → RE-PLAN
