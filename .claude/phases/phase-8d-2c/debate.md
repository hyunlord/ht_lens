## 1. Over-engineering

The `short_retranslate.py` selector stack in `.claude/phases/phase-8d-2c/plan.md:11,20-25` is a lot of machinery for one observed defect: doc7 has one bad `<60` chunk, `where`. A context-aware retranslation subsystem, CLI mode, dry-run mode, and new heuristics are broader than ROADMAP Phase 8d requires; ROADMAP Phase 8d is chat/pins/RAG chunk reanchor, figure chat, and cross-doc RAG, not translation repair.

The resize work in `.claude/phases/phase-8d-2c/plan.md:13,27-29` is also outside ROADMAP Phase 8d’s DoD. It may be useful UX, but mixing a translation data mutation path with fixed-drawer layout behavior makes verification noisy. This should be split or deferred unless the Planner explicitly treats it as the only remaining user blocker.

The plan proposes a new `src/ht_lens/translate/short_retranslate.py` rather than extending the existing chunk translation contract narrowly. If this is truly one doc7 correction, a safer path is dry-run reporting plus manual accept for selected chunk ids. Automatic heuristics can wait until 8e when all 7 docs expose the real distribution.

## 2. Hidden assumptions

The threshold is based on “doc7 `<60`자 text chunk 10개” in `.claude/phases/phase-8d-2c/plan.md:7`. The plan assumes that sample represents the other six docs and future MinerU outputs. If not, `<25` will miss real short-context errors like `where:`, `if`, `then`, `as follows`, or overselect normal glossary/list fragments.

The plan assumes context-dependent retranslations can safely overwrite `chunk_translations`. Existing `src/ht_lens/translate/chunk_pipeline.py:109-117,216-233` uses a content-only `cache_key(content, src, tgt, model)` for cross-run/cross-doc reuse. If a chunk `where` is rewritten to a context-specific Korean phrase while retaining or recomputing the same content cache key, future chunks with identical source may reuse the wrong context-specific translation.

The file-level plan points to `src/ht_lens/translate/cli.py` in `.claude/phases/phase-8d-2c/plan.md:35`, but the actual Typer command is `src/ht_lens/cli.py:372-443`. That is not a harmless path typo: tests and implementation need to target the right CLI surface and exit-code behavior.

The prompt plan assumes “대상만 추출” works reliably from an LLM response (`plan.md:24`). There is no stated delimiter, JSON schema, or parser failure behavior. If qwen returns explanations, quotes both neighbor and target, or empty output, the overwrite path can silently degrade a valid translation.

## 3. Edge cases

`is_repeated(content, all_contents)` in `.claude/phases/phase-8d-2c/plan.md:22` treats duplicate content as boilerplate. That will exclude legitimate repeated academic fragments such as “where”, “Proof.”, “Definition.”, “Sampling”, or repeated table/list labels, exactly the category this phase wants to fix.

`is_reference_number` as described in `.claude/phases/phase-8d-2c/plan.md:21` does not cover common reference forms: `Eq. (28.116)`, `[12]`, `Fig. 2`, `Table 1`, `28.4.2`, or `(A.1)-(A.3)`. The “digit-ratio high” fallback can also exclude meaningful short text like `K=10`, `p=0.5`, or `N samples`.

`is_math_dense` relies on `has_math`, but `src/ht_lens/translate/math_protect.py:17-24,83-85` explicitly does not handle `\(...\)` / `\[...\]` and can protect currency-like paired dollar spans. The plan says 8e owns math hardening, yet this phase’s selector safety depends on math detection being complete.

Neighbor radius 1 with “text only” (`plan.md:11,24`) can remove the very context needed for short fragments: headings, preceding equations, image captions, and table headers often define what `where` refers to. Skipping non-text neighbors may reproduce the original low-context failure.

Resize has mobile and compare-mode edge cases. `.chat` currently uses fixed `width: 380px; max-width: 90vw` in `src/ht_lens/api/static/css/reflow.css:135-138`; adding `.pane--reflow margin-right` can squeeze compare mode, overflow the PDF pane, or create a stale blank right gutter after close unless mode toggles and resize restoration are tested together.

## 4. Alternative approaches

For translation repair, prefer an explicit `--chunk-id ... --with-neighbors --dry-run/--apply` flow first. It avoids global heuristics, avoids corrupting cache semantics, and matches the measured defect count: one known bad chunk. Heuristic discovery can still print candidates without writing.

If automatic selection is required, store context-retranslated rows with `cache_key = NULL` or a context-aware cache key including neighbor chunk ids/order hashes. That aligns with the existing cache design in `chunk_pipeline.py:109-117` instead of poisoning content-only reuse.

For resize, a CSS-first approach using a small drag handler that only sets `--chat-w` on `.chat` is safer than coupling `applyChatWidth` to `.pane--reflow` globally. Alternatively, make the drawer overlay-only for compare mode and reserve margin only in single reading mode.

## 5. Missing tests

Add `test_short_retranslate_clears_or_contextualizes_cache_key`: retranslate `where` with neighbor A, then translate another `where` with neighbor B and prove content-only DB cache does not reuse A’s Korean output.

Add `test_short_retranslate_duplicate_where_not_excluded_as_boilerplate`: two legitimate `where` chunks in one doc should remain candidates unless the duplicate matches a known boilerplate pattern, not merely `count >= 2`.

Add `test_short_retranslate_llm_malformed_output_preserves_existing`: mocked LLM returns both neighbor and target, empty text, or delimiter-free prose; existing `ChunkTranslation.translated_text` must remain unchanged.

Add CLI subprocess tests against `ht_lens translate-chunks --short-only --dry-run` in `src/ht_lens/cli.py`, including missing doc exit 2, LLM health failure, no-write DB assertion, and `stats.failed` exit behavior.

Add `test_resize_compare_mode_does_not_squeeze_pdf_pane` and `test_resize_close_then_mode_toggle_clears_margin`: jsdom should verify drawer close, reopen, session restore, and single/compare radio toggles together, not only raw drag/clamp state.
