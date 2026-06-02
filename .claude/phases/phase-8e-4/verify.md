# Phase 8e-4 — Verify (self) — v3 (post cross-verify R2)

Scope: compare-mode continuous scroll-sync (right→left) + nested-image dedup.
Frontend + render-only; **0 DB/migration/1.x changes**.

Round history: v1 self 96 (`9dad445`) → **Codex R1 DOWNGRADE ~89-91** (4 gaps) →
RE-CODE (`d77b1b5`,`caf118e`) → v2 self 96 (`487bfee`) → **Codex R2 DOWNGRADE
93-94** ("should NOT go back to RE-CODE for the original complaints"; residual
minor resize/error/teardown coverage + evidence scope) → small RE-CODE
(`597a16c` error-invalidate, `a6baa8f` resize/error/teardown tests). R2 is the
final cross-verify round (cap=2). This v3 reflects HEAD `8872e75`; tracked tree
clean at verify time.

## R2 findings → resolution
| R2 issue | Resolution | Lock |
| -------- | ---------- | ---- |
| §4#1 resize invalidation claimed but untested | added window-`resize` dispatch test | `test_resize_event_invalidates_stale_boundaries` |
| §4#2 image `load` invalidated, `error` not (→ .fig-missing shifts offsets) | added `error` listener symmetric to `load` | `test_image_error_invalidates_stale_boundaries` |
| §4#3 teardown didn't lock resize/load/error removal | teardown test dispatches scroll+resize+load+error post-teardown → all inert | `test_teardown_detaches_all_handlers` |
| §1 mypy scope (only reflow.py) | ran full `uv run mypy src/` | Success, 85 files |
| §1 format `--check` | ran `uv run ruff format --check .` | 201 files already formatted |

## 5-A. Automated checks
| Check    | Command | Result |
| -------- | ------- | ------ |
| Lint     | `uv run ruff check src tests` | All checks passed! |
| Format   | `uv run ruff format --check .` | 201 files already formatted |
| Type     | `uv run mypy src/` | Success: no issues found in 85 source files |
| Test     | `uv run pytest -q` | **800 passed, 8 skipped, 0 failed** (561.48s); 3 snapshots passed |
| Focused  | reflow compare-sync + api + dedup + viewer + load | 40 passed |
| Coverage | (project default; not separately gated this phase) | n/a |
| CI       | GitHub Actions | **pending push** (cannot count as green pre-push) |

800 = v2's 798 + 2 new R2 tests (resize, image-error).

## 5-B. Functional checks (live, in-process against `data/ht_lens_v2.db`)
| Check | Evidence |
| ----- | -------- |
| reflow 200 / Fig 28.18 dedup | doc1 image count **15 → 12**; page2 ids `[30]`; 27/28/29 absent |
| non-destructive | `GET /v2/chunks/27/image` → **200 image/jpeg** (DB row intact) |
| dedup helper unit | 9/9 (panels drop; side-by-side/standalone/equal/malformed/cross-page kept) |
| dedup endpoint | `test_reflow_dedup_drops_nested_panels_at_endpoint` (drop + `/image` 200) |
| scroll-sync pure | `pickCurrentPage` 0→p0 / 150→p1 / 350→p2 / []→null |
| scroll-sync handler | real `scroll` Event syncs in compare; **inert in single**; teardown detaches all |
| stale-offset guard | image `load`, image `error`, window `resize` each invalidate → recompute → correct page |
| 1.x untouched | diff = `reflow.py` helper + `reflow.js` + 2 test files; 0 DB/migration/model/1.x-router changes |

## 5-C. Regression check (RE-CODE guard) — honest, no overclaim
Every RE-CODE-introduced code path (R1 + R2) is locked by a named test:

| New code path (grep-able symbol) | Locking test |
| -------------------------------- | ------------ |
| `dirty` / `invalidate` | `test_image_load_invalidates_stale_boundaries`, `test_resize_event_invalidates_stale_boundaries`, `test_image_error_invalidates_stale_boundaries` |
| window `resize` listener | `test_resize_event_invalidates_stale_boundaries` (+ removal: `test_teardown_detaches_all_handlers`) |
| img `load` + `error` listeners | image-load / image-error tests (+ removal: teardown test) |
| `onScroll`→rAF→`syncNow` wiring | `test_real_scroll_event_drives_sync_only_in_compare_mode` |
| `teardown` (scroll+resize+load+error+rAF) | `test_teardown_detaches_all_handlers` |
| `_strict_contains` / `_drop_captionless_images_contained_by_captioned` | 9 unit + endpoint test |

R1/R2-fixed areas re-checked green: dedup (helper+endpoint), scroll-sync
(pure+event-path), invalidation (load/error/resize). Existing reflow contracts
(`viewer`, `load`, all prior `test_reflow_api.py`) unbroken (40 focused / 800
full). No public-contract change (`/v2` routes, 1.x routes, CLI all unchanged).

## 5-D. Scoring (100, self-assessment — honest, R2-aligned)
| Item       | Score / Max | Evidence |
| ---------- | ----------- | -------- |
| 독창성     |   14 / 15   | IO→deterministic binary search; narrow strict-containment dedup; complete invalidation lifecycle (load/error/resize) |
| 완결성     |   33 / 35   | both DoD done + live + endpoint + full event-path/invalidation tests; coverage not separately gated, CI green only post-push; pixel bbox overlay deferred (out of scope) |
| 안정성     |   28 / 30   | 800 passed/0 failed, full mypy clean; stale-offset closed for load/error/resize; one-way (no loop); −2: CI still pending pre-push |
| 확장성     |   19 / 20   | pure `pickCurrentPage` + page-boundary-only + invalidation hooks scale to 3338 chunks; bbox overlay clean follow-on |
| **Total**  | **94 / 100**|          |

## 5-E. Self verdict
- [ ] PASS_CANDIDATE (≥95)
- [x] **BELOW THRESHOLD (94) → escalate to Planner.** All R1+R2 *functional*
  gaps are closed and locked by tests; the residual is evidence-semantics that
  only resolves post-push (CI green) plus no separate coverage gate this phase.
  Per the cross-verify cap (R2 = final) and the R2-DOWNGRADE push policy, I do
  **not** self-certify ≥95 or push autonomously — the Planner decides merge.
- [ ] FAIL → RE-CODE (Codex R2: explicitly NOT warranted for R1 complaints)
- [ ] FAIL → RE-PLAN
