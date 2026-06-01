## 1. Verification of automated checks
No stale-verify issue found. Current HEAD is `5502c79 chore(phase-8d-2a): verify v2`, and it only changes `.claude/phases/phase-8d-2a/verify.md`; the last code/test commit remains `87fde93`, matching the self-report.

The lint/format/type/test evidence is specific and plausible: `718 passed, 1 skipped, 7 deselected in 552.79s`. I did not rerun the full suite in this read-only audit, so this is a credibility check against current HEAD and code/tests, not an independent execution.

CI is still not real evidence. `verify.md` correctly marks GitHub CI as n/a due to 8e/jsdom provisioning debt. That is acceptable only because the report does not claim PASS_CANDIDATE.

## 2. Verification of functional checks
The Round 1 issues that were fixed should not be re-raised: the frontend duplicate-section select path now uses `renderToc(... onSelect: headingChunkId)` in `src/ht_lens/api/static/js/reflow.js:191-194`, `selectSectionByHeading()` in `src/ht_lens/api/static/js/sections.js:138-153`, and transcript clearing in `src/ht_lens/api/static/js/chat.js:23-35`.

Backend functional coverage is credible for 8d-2a: chunk/section thread creation, doc mismatch, section-anchor heading validation, LLM failure no-write, deleted-thread behavior, pins, and 1.x non-interference are covered in `tests/integration/test_chunk_chat_api.py:78-219`.

Frontend coverage improved materially: ask flow and pin flow are now mocked through fetch in `tests/integration/test_chat_ui_js.py:148-215`. However, the actual TOC button-to-chat path is still not tested end-to-end. The new duplicate test calls `selectSectionByHeading(4, ...)` directly at `tests/integration/test_reflow_sections_js.py:248`; it does not click a rendered `.toc-select` button and prove `renderToc()` passes `node.chunkId`.

The live qwen claim remains smoke-level only. `verify.md` still lacks reproducible command/payload/transcript artifacts, so it should not be weighted heavily.

## 3. Score audit
독창성 / 15: 12/15 is justified. The concrete heading `chunk_id` section anchor and separate `chunk_pins` table are clean responses to debate/R1, visible in `src/ht_lens/db/models.py:198-251`.

완결성 / 35: 31/35 is slightly high but defensible only as a non-pass score. The core DoD subset is implemented, but Roadmap Phase 8d still includes figure chat and cross-doc RAG, explicitly deferred to 8d-2b. I would score 30/35.

안정성 / 30: 27/30 is high. RE-CODE fixed the visible transcript bug and added ask/pin tests, but two regression-lock claims are overstated: no test asserts the DB CHECK rejects invalid direct inserts, and the real TOC select button path is not locked. Suggested 25/30.

확장성 / 20: 17/20 is reasonable. Anchoring section threads by heading chunk id gives 8d-2b a stable base. Minor deduction remains for the old `secNo`-first helpers still being exported and partially used for jump/reference flows. Suggested 16/20.

Fair audited score: about 83/100, not a failure, but below the self-score of 87.

## 4. Issues missed (new this round)
The RE-CODE DB CHECK is not actually tested. `ck_chunk_threads_anchor_type` was added in `src/ht_lens/db/migrations/versions/0007_chunk_chat.py:56-58` and ORM metadata in `src/ht_lens/db/models.py:209-211`, but `rg` finds no test reference to that constraint name or invalid `anchor_type` direct insert. `test_migration_0007_additive_only` only checks table add/drop behavior at `tests/integration/test_chunk_chat_schema.py:65-81`.

The new TOC callback contract lacks a regression test. `src/ht_lens/api/static/js/sections.js:198-207` changed `.toc-select` to call `onSelect(node.chunkId)`, which was the exact product path implicated by Round 1. Existing `test_render_toc_nested_with_callbacks` counts buttons but does not click a select button or inspect the callback value (`tests/integration/test_reflow_sections_js.py:211-227`). The duplicate test bypasses this path.

The self-report overstates grep evidence for `computeSectionByHeading`. That function is a new exported production identifier at `src/ht_lens/api/static/js/sections.js:114-133`, but tests only exercise it indirectly through `selectSectionByHeading`; the identifier itself does not appear in tests. Indirect coverage is not a functional defect, but it does not meet the stated RE-CODE rule as written.

`pinCurrent()` still fires `loadPins()` without awaiting it at `src/ht_lens/api/static/js/chat.js:99-107`. The new test compensates with polling (`tests/integration/test_chat_ui_js.py:202-205`), which proves eventual rendering, not that callers can await a completed pin+reload operation. This is minor, but it is a new async edge in RE-CODE’s exported test surface.

## 5. Verdict
**DOWNGRADE** — The important Round 1 functional defects appear fixed, and this is no longer a reject-level phase. The remaining problems are narrower: overstated regression evidence around the DB CHECK and incomplete locking of the new TOC button callback path. I would put the phase around **83/100** and send it to the human Planner with a focused note, not another broad RE-CODE.
