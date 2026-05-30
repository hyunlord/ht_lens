## 1. Verification of automated checks

The report is not stale: current HEAD is `16d933a chore(phase-8d-1): verify`, and `verify.md` says the last code/test commit was `c4b2250`. I found no later code commits after `verify.md`.

Lint/format/type evidence is plausible, but the test command is not CI-equivalent. `verify.md` reports `uv run pytest -m "not llm and not slow" -q --no-cov`, while `.github/workflows/ci.yml:49` runs without `--no-cov`, and `pyproject.toml:71` enables coverage by default. They intentionally bypassed the configured coverage path, then marked coverage n/a.

CI evidence is weak. The repo has real GitHub Actions at `.github/workflows/ci.yml`, including `shellcheck scripts/*.sh` plus the Python checks. `verify.md` says CI is n/a / local equivalent, but does not run or account for shellcheck and does not show a green Actions run.

## 2. Verification of functional checks

The jsdom functional coverage is materially stronger than the plan stage: the tests cover digit-required citations, section-membership refs, KaTeX skip, original-based section identity, parent section selection, ref-click propagation, and TOC DOM placement.

The largest functional gap is that the new section logic is tested against synthetic chunks containing `order_idx`, but the real `/v2/documents/{doc_id}/reflow` response does not expose `order_idx`; see `src/ht_lens/api/routers/reflow.py:49-62`. `sections.js` sorts on `order_idx` in `buildSectionTree` and `computeSectionChunks` (`src/ht_lens/api/static/js/sections.js:29`, `:63`), so the tests do not match the live API contract.

Visual verification is still thin. `test_toc_drawer_outside_compare_grid` only asserts that `#toc` is outside `.layout`; it does not verify rendered drawer width, header overlap, mobile behavior, or actual visible citation/reference styling. The live serving check in `verify.md` confirms assets are 200 and imports exist, not that A+B workflows work in a browser.

## 3. Score audit

독창성 / 15: `12/15` is defensible. DOM-only enrichment and heading-membership disambiguation fit the phase without new dependencies. I would keep 12, with the caveat that the client-only section model is a temporary duplicate of future backend section semantics.

완결성 / 35: `31/35` is too high. The A+B unit behavior is mostly covered, but functional evidence misses live API schema integration (`order_idx` absent from `ReflowChunk`) and lacks browser visual evidence for a UI phase. I would score 28/35.

안정성 / 30: `28/30` is too high. The exact CI test command was not run because `--no-cov` bypasses configured coverage, CI was not actually green, and the new TOC toggle handler at `src/ht_lens/api/static/js/reflow.js:208-212` has no explicit test. I would score 24/30.

확장성 / 20: `17/20` is slightly optimistic. The `sectionselect` event is a useful bridge to 8d-2, but the current JS depends on ordering data absent from the API schema and defers canonical section boundaries. I would score 15/20.

Fair total: 79/100, not 88/100.

## 4. Issues missed (new this round)

`sections.js` depends on `order_idx`, but the live reflow API omits it. Tests define `H/T` fixtures with `order_idx` in `tests/integration/test_reflow_sections_js.py:61-64`, masking the mismatch. Current browsers may preserve API order when the comparator returns `NaN`, but this is accidental and untested; either the API should expose `order_idx` or the frontend should explicitly trust response order.

The TOC toggle path is new but untested. `reflow.html:14` adds `#toc-toggle`, and `reflow.js:208-212` mutates `hidden`/`aria-expanded`, but no test clicks the real toggle or verifies initial/after states. For a UI feature whose main affordance is hidden by default, this is a direct functional gap.

The full `load()` integration path is not tested. Component tests cover `enrichInline`, `renderToc`, and `wireRefJump` separately, but there is no jsdom fetch-backed test proving that a real `/v2/reflow`-shaped response builds `sectionNums`, enriches chunks, renders the TOC, wires selection callbacks, and handles refs together.

The old error rendering XSS surface remains and weakens the “DOM-only/no XSS surface” claim. `reflow.js:194` interpolates `e.message` into `innerHTML`, and `e.message` includes up to 160 chars of response body from `r.text()` at `reflow.js:154-155`. This predates 8d-1, but the verify report repeats broad safety claims without acknowledging that the page still has an unsafe error sink.

Reference enrichment also applies inside headings. Because `reflow.js:180` calls `enrichInline` on every chunk after setting `data-sec`, a heading like `28.4 Title` can wrap its own section number as `.rf-ref`. Clicking that number will jump to itself and stop the chunk sync handler, which is not covered by `test_ref_click_does_not_trigger_chunk_sync`.

## 5. Verdict

**DOWNGRADE** — The implementation appears mostly functional for the scoped A+B phase, and the debate points were addressed more concretely than usual. But the self-score overstates stability/completeness: CI-equivalent checks were not actually run, visual/browser verification is shallow, and the section tests use an `order_idx` field missing from the real API response. I would rate this around **79/100** and ask for targeted RE-CODE or planner acceptance with explicit debt tracking, not a full rejection.
