## 1. Over-engineering
- [plan.md](/home/hyunlord/github/ht_lens/.claude/phases/phase-6i/plan.md:47) adds a large DOMPurify MathML/tag allowlist, but the actual call sites do not need it. In [message.js](/home/hyunlord/github/ht_lens/src/ht_lens/api/static/js/components/message.js:30) the content is sanitized before math rendering, and in [block.js](/home/hyunlord/github/ht_lens/src/ht_lens/api/static/js/components/block.js:52) KaTeX would run on `textContent`. That allowlist increases security surface without protecting a real path.

- [plan.md](/home/hyunlord/github/ht_lens/.claude/phases/phase-6i/plan.md:63) modifies both [index.html](/home/hyunlord/github/ht_lens/src/ht_lens/api/static/index.html:7) and [viewer.html](/home/hyunlord/github/ht_lens/src/ht_lens/api/static/viewer.html:7). `index.html` is the document list page and does not render block text or chat messages. Linking KaTeX CSS there is pure scope creep for this phase.

- The plan claims inline `$...$` is the target, then silently expands to `$$...$$` display support and full font vendoring anyway ([plan.md](/home/hyunlord/github/ht_lens/.claude/phases/phase-6i/plan.md:23), [plan.md](/home/hyunlord/github/ht_lens/.claude/phases/phase-6i/plan.md:40)). That broadens behavior and test surface for little value in a fix that is supposed to address raw inline math leakage.

## 2. Hidden assumptions
- The biggest unstated assumption is that Phase 6i is valid at all. [WORKFLOW.md](/home/hyunlord/github/ht_lens/WORKFLOW.md:48) requires Goal/DoD mapping to align with ROADMAP, and forbids features outside it; [CLAUDE.md](/home/hyunlord/github/ht_lens/CLAUDE.md:25) repeats that scope rule. `ROADMAP.md` has Phase 6h and 7a-3, but no Phase 6i entry. This plan is inventing a phase and then mapping DoD to itself.

- [plan.md](/home/hyunlord/github/ht_lens/.claude/phases/phase-6i/plan.md:40) says `katex.min.js` is ESM and imports it from [render_markdown.js](/home/hyunlord/github/ht_lens/src/ht_lens/api/static/js/utils/render_markdown.js:10). KaTeX’s official docs distinguish `katex.min.js` script-tag usage from `katex.mjs` / `contrib/auto-render.mjs` ESM usage. If that assumption is wrong, the viewer fails at module load, not just at math render. Sources: https://katex.org/docs/browser and https://katex.org/docs/autorender.html

- Vendor acquisition is not reproducible. [plan.md](/home/hyunlord/github/ht_lens/.claude/phases/phase-6i/plan.md:88) assumes a specific `~/.vscode-server/.../node_modules/katex/` tree exists on every worker machine. That is not a repo contract, not a CI contract, and not even a stable local path.

- The DoD line for XSS is misleading. [plan.md](/home/hyunlord/github/ht_lens/.claude/phases/phase-6i/plan.md:212) credits `trust: false + DOMPurify`, but DOMPurify is not on the post-KaTeX path. If `trust: false` does not behave exactly as assumed, unsafe HTML is injected after sanitization.

## 3. Edge cases
- [plan.md](/home/hyunlord/github/ht_lens/.claude/phases/phase-6i/plan.md:56) gates viewer math with `text.includes("$")`. That will hit currency, shell variables, OCR noise, and prose about LaTeX syntax. The plan acknowledges `$5.00` in its own debate questions, then hand-waves it away with “v2_ko prompt standard.” Existing translated documents are not constrained by that promise.

- Viewer clipping is underplayed. [font_fit.js](/home/hyunlord/github/ht_lens/src/ht_lens/api/static/js/utils/font_fit.js:97) measures Noto/Inter text, not KaTeX glyph layout. Fractions, superscripts, `\sum`, and display math can exceed the bbox even when raw text “fits,” which collides directly with [block.js](/home/hyunlord/github/ht_lens/src/ht_lens/api/static/js/components/block.js:53) overflow-warning logic.

- Chat markdown still has hazardous mixed content: inline code, fenced code, escaped `\$`, and messages that explain LaTeX syntax rather than contain math. The plan only cites KaTeX’s default ignored tags; it does not prove the repo’s actual `marked` output plus `applyMath(body)` sequence leaves those cases intact.

- Font-path breakage is untested. KaTeX CSS expects `fonts/` relative to the CSS file. A wrong vendor layout will produce fallback glyphs or reflow after first paint, and the current plan has no browser-level assertion for that.

## 4. Alternative approaches
- Use KaTeX’s documented browser assets instead of pretending the minified files are ESM. Either vendor `katex.mjs` and `contrib/auto-render.mjs`, or load KaTeX via `<script>` in [viewer.html](/home/hyunlord/github/ht_lens/src/ht_lens/api/static/viewer.html:43). That matches the official integration model and avoids a fragile import hack.

- Keep [render_markdown.js](/home/hyunlord/github/ht_lens/src/ht_lens/api/static/js/utils/render_markdown.js:33) focused on markdown + sanitization, and do math rendering only at the component boundary. That removes the unnecessary DOMPurify MathML allowlist and makes the security boundary obvious.

- Replace `text.includes("$")` with at least a paired-delimiter gate. A cheap delimiter sanity check is better than invoking KaTeX on every translated block that happens to contain a dollar sign.

## 5. Missing tests
- Add `test_render_message_assistant_applies_math_and_preserves_related_blocks`. [message.js](/home/hyunlord/github/ht_lens/src/ht_lens/api/static/js/components/message.js:43) already has a fragile Phase 7a fallback path; the proposed tests never touch it.

- Add `test_render_message_user_content_with_dollar_stays_plain_text`. The phase changes assistant rendering, but it must also lock the invariant that user/system messages never pass through math rendering.

- Add `test_render_block_translation_math_preserves_click_and_contextmenu_contract`. [block.js](/home/hyunlord/github/ht_lens/src/ht_lens/api/static/js/components/block.js:83) owns custom events and [block.js](/home/hyunlord/github/ht_lens/src/ht_lens/api/static/js/components/block.js:103) owns retranslate context menus. A `<span class="katex">` assertion does not verify those behaviors survived DOM mutation.

- Add `test_apply_math_ignores_currency_or_unmatched_dollar` and `test_markdown_code_block_math_not_rendered`. Both risks are explicitly named in [plan.md](/home/hyunlord/github/ht_lens/.claude/phases/phase-6i/plan.md:221) and [plan.md](/home/hyunlord/github/ht_lens/.claude/phases/phase-6i/plan.md:232), but neither is locked.

- Add static-asset tests for KaTeX CSS plus at least one font URL, and assert only [viewer.html](/home/hyunlord/github/ht_lens/src/ht_lens/api/static/viewer.html:7) links KaTeX CSS. The current “`test_static_serving.py`가 있다면`” wording in [plan.md](/home/hyunlord/github/ht_lens/.claude/phases/phase-6i/plan.md:202) is not a test strategy.
