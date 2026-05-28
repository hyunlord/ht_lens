# Phase 6i — Verify (self) — v2 (post RE-CODE)

마지막 code commit: `5bf5c19 fix(phase-6i): direct renderBlock/renderMessage math tests (verify-cross R1)`
`git status` clean 직후 작성. RE-CODE는 verify-cross R1 REJECT 사후의 testing-only 보강.

## 5-A. Automated checks

| Check    | Command                                          | Result |
| -------- | ------------------------------------------------ | ------ |
| Lint     | `uv run ruff check .`                            | All checks passed |
| Format   | `uv run ruff format --check .`                   | 160 files already formatted |
| Type     | `uv run mypy src`                                | Success: no issues found in 68 source files |
| Test     | `uv run pytest -m "not llm and not slow" -q --no-cov` | 575 passed, 1 skipped, 7 deselected in 249.67s |
| Coverage | n/a (cov suite runs under `-m slow`; deferred per project policy) | n/a |
| CI       | push 후 GitHub Actions에서 확정 (the same 4 commands above run there) | pending push |

테스트 회계: baseline 552 → v1 570 (+18 KaTeX/static) → v2 575 (+5 RE-CODE direct tests). +5 = `test_render_block_translation_mode_renders_math` + `test_render_block_original_mode_does_not_render_math` + `test_render_block_unmatched_dollar_skips_katex` + `test_render_message_assistant_renders_math` + `test_render_message_user_role_stays_plain_text`.

## 5-B. Functional checks

| DoD | Evidence |
| --- | -------- |
| Viewer block translation mode renders `$...$` paired math via KaTeX | `test_render_block_translation_mode_renders_math` (direct `renderBlock(..., "translation")` call, asserts `.katex` present) + utility-level `test_inline_math_renders_to_katex_span`, `test_korean_text_with_inline_math_mixed`, `test_display_math_renders` |
| Viewer block original mode does NOT render math (PDF source verbatim) | **NEW** `test_render_block_original_mode_does_not_render_math`: drives `renderBlock(..., "original")` with `$E=mc^2$` in original_text → asserts no `.katex` AND `$E=mc^2$` preserved in textContent |
| Paired-delimiter gate filters currency `$5.00` | **NEW** `test_render_block_unmatched_dollar_skips_katex` (call-site lock) + `test_paired_delimiter_gate_ignores_unmatched_dollar` (now imports `hasPairedMath` from `block.js`, not redefined) |
| Chat assistant messages render math | **NEW** `test_render_message_assistant_renders_math`: drives `renderMessage()` from `message.js` directly with role=assistant + math content → asserts `.katex` present |
| Chat user/system messages stay plain text | **NEW** `test_render_message_user_role_stays_plain_text`: drives `renderMessage()` with role=user containing `$5.00`/`$x^2$` → asserts no `.katex`, textContent equals input, no HTML tags |
| Broken LaTeX doesn't crash | `test_broken_latex_falls_back`: `throwOnError:false` + try-guard in `applyMath` |
| XSS contract: `\href{javascript:...}` cannot create executable link | `test_no_xss_via_href_in_math`: KaTeX `trust:false`, no `<a href>` element emitted, no `javascript:` after stripping MathML annotation |
| `<code>` / `<pre>` skipped | `test_markdown_code_block_math_not_rendered`: `ignoredTags` config |
| Block click/contextmenu listeners survive math render | `test_block_translation_math_preserves_listeners_contract` |
| index.html (document list) has NO KaTeX assets | `test_phase6i_only_viewer_html_links_katex` |
| KaTeX vendor assets served via FastAPI static | `test_phase6i_katex_assets_served` × 6 |
| Existing markdown+DOMPurify XSS guarantees preserved | `test_render_markdown_js.py` (Phase 5) — 5/5 still pass |
| Existing viewport/stage/page tests unaffected | `test_viewport_js.py` 6/6 (addHook guard fix verified by transitive import path stage_container → pane → page_view → block → render_markdown) |

## 5-C. Scoring (100, self-assessment)

| Item | Score / Max | Evidence |
| ---- | ----------- | -------- |
| 독창성 | 12 / 15 | Per Codex audit: pragmatic vendor-and-wrap, not novel. Paired-delimiter gate + assistant-only chat boundary is the design subtlety; remaining 3-point gap is the known false-positive (`Two prices: $5 and $10` triggers gate, KaTeX silently fails) — intentional + documented. |
| 완결성 | 32 / 35 | All Codex R1 gaps closed: `renderBlock` translation+math, `renderBlock` original-skip, `renderBlock` currency-skip, `renderMessage` assistant, `renderMessage` user-plain — all directly exercised. Static-asset routing + viewer/index split verified. Deduction: ROADMAP has no canonical Phase 6i DoD; this remains "matches the ad-hoc plan + addresses Codex R1" rather than "matches ROADMAP". |
| 안정성 | 26 / 30 | mypy strict + ruff lint/format clean on canonical `.` scope. 575/575 regression green. Detected + fixed a transitive-import regression (addHook on non-browser env). `block.js` no-window path now indirectly + directly covered. Deduction: the known false-positive parse-error log path is still present (`auto-render.mjs:123,237`) — silent in practice but visible if a real `$N$ vs $M$`-style sentence appears; mitigated only by `errorCallback` defaulting to `console.error`. |
| 확장성 | 17 / 20 | `applyMath(el)` is reusable from any UI surface. `hasPairedMath` is now an exported pure function. SOURCE.md captures regen commands. Deduction: renderer choice (KaTeX) is hardwired across call sites; replacing it would require touching `render_markdown.js` + every caller. |
| **Total** | **87 / 100** | |

## 5-D. Self verdict

- [ ] PASS_CANDIDATE (≥95)
- [x] **FAIL (self-score < 95)** — but RE-CODE has closed every concrete Codex R1 finding. The remaining sub-95 reasons are structural (no ROADMAP DoD; known regex false-positive is by-design + documented in plan), not new defects.
- [ ] FAIL → RE-PLAN

Status: submit to **cross-verify Round 2 (final per CLAUDE.md cap)**. If Round 2 still REJECTs without naming a concrete new defect, escalate to Planner per the round-2-cap rule.

## 5-E. Regression check (RE-CODE → required by CLAUDE.md)

RE-CODE 라운드의 새 코드 경로 ↔ 단위 테스트 잠금 표:

| RE-CODE change | Test that locks it |
| -------------- | ------------------ |
| `block.js`: `_hasPairedMath` → `export function hasPairedMath` (rename + null guard) | `test_paired_delimiter_gate_ignores_unmatched_dollar` now imports `hasPairedMath` from `block.js`; includes `""` → false case for the new null guard |
| `block.js:71` `if (overlayMode === "translation" && hasPairedMath(text))` branch — translation mode + math | `test_render_block_translation_mode_renders_math` |
| `block.js:71` branch — translation mode + non-math (currency) | `test_render_block_unmatched_dollar_skips_katex` |
| `block.js:71` branch — original mode (must NOT call applyMath) | `test_render_block_original_mode_does_not_render_math` |
| `message.js:35` `applyMath(body)` for role=assistant | `test_render_message_assistant_renders_math` (real `renderMessage` import) |
| `message.js:38` `textContent` path for role=user/system | `test_render_message_user_role_stays_plain_text` (real `renderMessage` import) |

각 새 export / 새 분기 이름이 grep으로 테스트 파일에 등장함:
- `grep "hasPairedMath" tests/integration/test_katex_render_js.py` → 2 hits
- `grep "renderBlock" tests/integration/test_katex_render_js.py` → 4 hits
- `grep "renderMessage" tests/integration/test_katex_render_js.py` → 4 hits

Regression of v1 area (Round 1 fix: DOMPurify.addHook guard):
- `test_viewport_js.py` 6/6 pass (transitive import path stage_container → pane → page_view → block → render_markdown still triggers the no-window load).
- `test_render_markdown_js.py` 5/5 pass (Phase 5 XSS — the guard didn't change browser-path behaviour).

No fix-area regressions detected.

## 5-F. Deviations from plan

- **`_hasPairedMath` → `hasPairedMath` rename**: not in original plan; added during RE-CODE to make the gate importable from tests (responding to Codex R1 §4 finding that the regex was being redefined in tests rather than imported). Pure rename + null guard; same semantics.
- **`hasPairedMath(null)` / `hasPairedMath("")` returns false**: new behaviour. Plan implied "matches `INLINE_MATH_RE` or `DISPLAY_MATH_RE`" which would have crashed `.test(null)`. Added an explicit empty-string guard during RE-CODE.

Both deviations are minimal, in-scope (testing hardening), and documented above per CLAUDE.md Regression-guard rule §3.
