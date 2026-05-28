# Phase 6i — Summary

## Status

**ESCALATE_TO_PLANNER** (per WORKFLOW.md Stage 6: Round 2 DOWNGRADE → push held).

Self-score under 95 (honest grading per CLAUDE.md rule), Codex Round 2 returned
DOWNGRADE (not REJECT). Code is functionally complete, regression suite green,
no fresh defects after RE-CODE. Planner decides whether to PASS (sub-95 by self
is intentional; structural deductions not closeable inside Phase 6i) or RE-PLAN.

## Score

- Self (v2): **87 / 100** (12 + 32 + 26 + 17)
- Codex (R2): **DOWNGRADE — fair ≈ 79 / 100** (12 + 28 + 23 + 16)
- Delta: Codex trims 완결성 (-4: no ROADMAP DoD, coverage/CI unproven) + 안정성 (-3: `--no-cov` opt-out, known false-positive parse-error path) + 확장성 (-1: KaTeX policy at multiple call sites).

Both sides agree this is not a 95+ PASS_CANDIDATE. Neither side identifies a
fresh code defect after RE-CODE.

## What was built

- **KaTeX 0.16.22 vendored** under `src/ht_lens/api/static/vendor/katex/` (MIT, offline-first; see `SOURCE.md` for the npm-pack regeneration recipe and the `sed` patch flattening `dist/contrib/auto-render.mjs`'s `../katex.mjs` import to `./katex.mjs`).
- **`applyMath(el)`** export in `render_markdown.js` — KaTeX auto-render with paired `$...$` + `$$...$$` delimiters, `trust:false`, `throwOnError:false`, `ignoredTags` covering `<code>/<pre>/<script>/<style>/<noscript>/<textarea>/<option>`.
- **`hasPairedMath(text)`** export in `block.js` — pure gate function (paired-delimiter regex + null guard). `renderBlock(..., "translation")` calls `applyMath` only when the gate fires; original mode never invokes KaTeX.
- **`renderMessage` assistant branch** calls `applyMath(body)` after `renderMarkdown`. User/system stays `textContent` (no math, no HTML interpretation).
- **`viewer.html`** links `vendor/katex/katex.min.css` (index.html intentionally untouched — document list has no overlay or chat panel).
- **`base.css`** rules: `.block .katex { font-size: inherit }`, `.message .katex-display { margin/overflow }`, `.katex-error`.
- **Regression-fix during integration**: `DOMPurify.addHook` call now guarded against non-browser harness imports. block.js's new `applyMath` import made render_markdown.js transitively load in `test_viewport_js.py` (via `stage_container → pane → page_view → block`), which has no `window`; previously crashed there.

## Files changed

```
72 files changed, 19306 insertions(+), 9 deletions(-)    (feat afe1f7b)
 2 files changed,   151 insertions(+),  15 deletions(-)  (fix  5bf5c19 RE-CODE)
```

Code (non-vendor):
- `src/ht_lens/api/static/js/utils/render_markdown.js` (+58, addHook guard + applyMath)
- `src/ht_lens/api/static/js/components/block.js` (+13, exported hasPairedMath + applyMath call site)
- `src/ht_lens/api/static/js/components/message.js` (+5, applyMath on assistant branch)
- `src/ht_lens/api/static/viewer.html` (+4, KaTeX CSS link)
- `src/ht_lens/api/static/css/base.css` (+3 rules)

Tests:
- `tests/integration/test_katex_render_js.py` (new, 16 tests)
- `tests/integration/test_static_serving.py` (+7 rows)

Vendor:
- `src/ht_lens/api/static/vendor/katex/` (katex.mjs, katex.min.css, auto-render.mjs, LICENSE, SOURCE.md, fonts/×60)

## Evidence index

- plan: `.claude/phases/phase-6i/plan.md` (v2, 001a186)
- debate: `.claude/phases/phase-6i/debate.md`
- challenge: `.claude/phases/phase-6i/challenge.md`
- verify: `.claude/phases/phase-6i/verify.md` (v2, fc9d640 — Regression check + Deviations included per CLAUDE.md)
- verify-cross r1: REJECT → led to RE-CODE 5bf5c19
- verify-cross r2: DOWNGRADE (final per round-2 cap) → de205bb

Regression: **575/575 passed, 1 skipped**, mypy strict clean on src, ruff check/format clean on `.`.

## Deviations from plan

1. **`_hasPairedMath` → `hasPairedMath` rename + export + null guard** — not in original plan; added during RE-CODE to make the gate importable from tests (Codex R1 §4: tests redefined the regex rather than importing). Pure rename + null guard; semantics unchanged.
2. **`DOMPurify.addHook` guard** — not in plan; added when full-regression run surfaced `test_viewport_js` failing because block.js's new applyMath import pulled render_markdown.js into a no-window subprocess. The guard is `typeof DOMPurify?.addHook === "function"` — preserves all browser behaviour, only adds tolerance for non-browser ESM importers.

Both deviations are testing/harness hardening only, in-scope for Phase 6i.

## Known issues / debt

- **Paired-dollar false-positive**: `"Two prices: $5 and $10"` triggers the gate (regex matches `"$5 and $10"`). KaTeX then silently fails (`throwOnError:false`) but emits a `console.error` via auto-render.mjs's default `errorCallback`. **Test `test_paired_delimiter_gate_ignores_unmatched_dollar` locks this as intentional**. Possible follow-up: override `errorCallback` to suppress noise, or tighten the regex to require `[a-zA-Z\\]` inside the delimiters. Not blocking — current behaviour is correct, just noisy in console for rare prose patterns.
- **No ROADMAP-canonical Phase 6i DoD**: Codex flagged in both R1 and R2. Phase 6i was user-prompt-driven, not ROADMAP-anchored. Score audit deductions on 완결성 reflect that — closeable only by adding the DoD to ROADMAP (CLAUDE.md forbids worker editing ROADMAP).
- **Coverage explicitly disabled** (`--no-cov`): pyproject defaults `--cov`, but the project's default test invocation in `make test-fast` also disables coverage. No new code is introduced that lowers branch coverage of the existing covered modules.
- **No visual smoke test**: jsdom-only — font loading and reflow are not verified beyond static-asset reachability. Manual viewer check after push is recommended (see Recommended next).

## Recommended next (for Planner)

1. **Planner decision**: PASS the phase with the explicit "sub-95 by self is intentional, no fresh defects, Codex DOWNGRADE not REJECT" framing, OR request a narrow follow-up (ROADMAP DoD entry; `errorCallback` override).
2. **If PASS**: Planner pushes the 6 Phase 6i commits (or directs me to). Watch CI green, then manual smoke-test `$p(z) = \\text{Dir}(z|\\alpha)$` in the viewer.
3. **If RE-PLAN**: scope it to (a) add Phase 6i to ROADMAP.md with DoD, (b) override KaTeX `errorCallback` to a quieter logger. Both are <30 min, no architectural change.

Push status: **HELD** at local commit `de205bb` (4 commits ahead of origin/main were already there from Phase 7a-2/7a-3; Phase 6i added 6 more: plan→feat→verify→verify-cross→fix→verify-v2→verify-cross-r2→summary). Awaiting Planner direction.
