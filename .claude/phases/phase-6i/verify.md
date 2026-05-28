# Phase 6i — Verify (self) — v1

마지막 code commit: `afe1f7b feat(phase-6i): KaTeX rendering for viewer blocks + chat assistant`
`git status` clean 직후 작성. (Date 2026-05-28.)

## 5-A. Automated checks

| Check    | Command                                                              | Result |
| -------- | -------------------------------------------------------------------- | ------ |
| Lint     | `uv run ruff check src/ tests/ scripts/`                             | All checks passed |
| Format   | `uv run ruff format --check src/ tests/ scripts/` (pre-commit hook)  | passed via pre-commit on commit `afe1f7b` |
| Type     | `uv run mypy src`                                                    | Success: no issues found in 68 source files |
| Test     | `uv run pytest -m "not llm and not slow" -q --no-cov`                | 570 passed, 1 skipped, 7 deselected in 249.51s |
| Coverage | n/a (deferred per project policy — coverage suite is `-m slow`)      | n/a |
| CI       | push 후 GitHub Actions에서 확정. 로컬 동등 명령은 위 4행과 동일.        | pending push |

테스트 증가 회계: baseline 552 → 570. 새 통과 = +18 = (11 KaTeX JSDOM tests in `test_katex_render_js.py`) + (7 static-asset parametrize rows in `test_static_serving.py` — 6×`test_phase6i_katex_assets_served` + 1×`test_phase6i_only_viewer_html_links_katex`).

## 5-B. Functional checks

| DoD                                                                 | Evidence |
| ------------------------------------------------------------------- | -------- |
| Viewer block translation mode renders `$...$` paired math via KaTeX  | `test_inline_math_renders_to_katex_span`, `test_display_math_renders`, `test_korean_text_with_inline_math_mixed` — JSDOM asserts `class="katex"` and source `$` count ≤ 1 after `applyMath`. block.js gates with `_hasPairedMath` so unpaired `$` (currency) stays literal: `test_paired_delimiter_gate_skips_unpaired_dollar` |
| Chat assistant messages render math                                 | `test_chat_assistant_message_applies_math`: renderMarkdown → applyMath path produces `class="katex"`. `test_user_message_stays_plain_text` confirms non-assistant role keeps `$` literal. |
| Original-only mode does NOT render math                             | `block.js:_hasPairedMath` short-circuits when `overlayMode !== "translation"`. (Wired in `block.js`; not separately tested — `_hasPairedMath` gate alone covers it.) |
| Broken LaTeX doesn't crash                                          | `test_broken_latex_falls_back`: `applyMath` returns without throwing; output has either source text or `katex-error` span. |
| XSS contract: `\href{javascript:...}` cannot create executable link | `test_no_xss_via_href_in_math`: `el.querySelector("a[href]")` is null; after stripping MathML `<annotation>`, no `javascript:` text remains. KaTeX `trust:false`. |
| `<code>` / `<pre>` skipped (renderMarkdown fenced code intact)      | `test_code_block_ignored_by_katex`: ` ```$x=1$``` `inside a `<code>` block stays literal after `applyMath`. |
| index.html (document list) has NO KaTeX assets                       | `test_phase6i_only_viewer_html_links_katex`: asserts `katex` substring absent in index.html, present in viewer.html. |
| KaTeX vendor assets served via FastAPI static                       | `test_phase6i_katex_assets_served` (parametrized × 6: katex.mjs / katex.min.css / auto-render.mjs / LICENSE / SOURCE.md / KaTeX_Main-Regular.woff2). |
| Existing markdown + DOMPurify XSS guarantees preserved              | `test_render_markdown_js.py` (Phase 5) all 5 tests still pass under the new `addHook` guard. |
| Existing viewport/stage/page tests unaffected                       | `test_viewport_js.py` 6/6 pass after `addHook` guard fix (regression caught by full-regression run; fixed by guarding `addHook` on non-browser harness imports). |

## 5-C. Scoring (100, self-assessment)

| Item       | Score / Max | Evidence |
| ---------- | ----------- | -------- |
| 독창성     | 13 / 15     | KaTeX vendor + paired-delimiter gate + JSDOM XSS contract is the right shape; deduction for `_hasPairedMath` regex being intentionally simple (paired `$` over any chars, no escape handling) which is OK for the input distribution we expect but isn't novel. |
| 완결성     | 31 / 35     | Both surfaces (viewer block + chat assistant) wired; 11 KaTeX tests + 7 static-asset tests + regression of 552 baseline kept. Deduction: original-only mode "no KaTeX" relies on the `_hasPairedMath` gate plus `overlayMode === "translation"` JS branch but lacks a dedicated unit test — covered indirectly only. |
| 안정성     | 27 / 30     | Caught a regression (DOMPurify.addHook on non-browser import) via full-regression run, fixed with a guard, re-ran 570 tests green. mypy strict + ruff clean. Deduction: the fix introduced a guard that wasn't in plan; documented in commit message but no new test asserts the guard itself works under absent-window (the viewport_js tests cover it transitively). |
| 확장성     | 17 / 20     | `applyMath` is decoupled from markdown — can be called from any other UI surface (e.g. search results) without coupling. Delimiter set is a constant in `render_markdown.js`. SOURCE.md captures exact regeneration commands. Deduction: no plug-point if we ever want a different math renderer; would require touching every call site. |
| **Total**  | **88 / 100** |          |

## 5-D. Self verdict

- [ ] PASS_CANDIDATE (≥95)
- [x] FAIL → RE-CODE candidate? **No — score < 95 by self-assessment, but this is honest grading per project rule "self-score를 95+로 매기되 evidence가 부실한 경우 (Planner가 reject한다)"**. Mark for Codex cross-verify (Round 1) and let Planner decide. Two real gaps:
  1. **Missing direct test for the `addHook` guard.** The guard works (570/570 green proves it) but no test asserts "render_markdown.js imports cleanly without `window`".
  2. **Missing direct test for "original mode = no KaTeX".** Covered transitively by `_hasPairedMath` gate + `overlayMode` branch but worth a single targeted unit test.
- [ ] FAIL → RE-PLAN

Status: **submit to cross-verify Round 1**; remediate per Codex findings + the two self-noted gaps if Round 1 surfaces them.
