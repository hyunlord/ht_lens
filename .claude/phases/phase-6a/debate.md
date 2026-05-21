## 1. Over-engineering

- `.claude/phases/phase-6a/plan.md` §1 makes `SearchHit` carry `matched_field`, `match_start`, `match_end`, `preview`, and `block_local_id`. For the Roadmap Phase 6a DoD, the viewer only needs enough data to show a snippet and jump to a block. Offset-aware highlighting across original/translated text is extra complexity with real Unicode and truncation failure modes.

- The retranslate UI is spread across `src/ht_lens/api/static/js/components/block.js`, new `confirm_modal.js`, and optional `src/ht_lens/api/static/js/components/chat_panel.js` edits. `ROADMAP.md` only requires “block 우클릭 → 재번역”. Keep one trigger. Two entrypoints means two loading/error/state paths in `src/ht_lens/api/static/js/viewer.js`.

- The plan’s “FTS5 migration (필요 시 Phase 6b)” deferment is not grounded in `ROADMAP.md`. Phase 6b is extraction-quality debt, not search infrastructure. You are inventing a future scope bucket to absorb a possible miss on a current Phase 6a DoD.

## 2. Hidden assumptions

- The plan assumes `LOWER(...) LIKE '%q%'` on `blocks` plus `translations` can meet the Roadmap’s “latency < 200ms for 10K blocks”. Plan §12 only measures `sample_mixed.pdf = 102 blocks` and maybe extrapolates. That assumes wildcard LIKE, JOIN cost, and table growth stay benign. If wrong, the phase fails a written DoD.

- Plan §5 says export failures show a toast, but the actual approach is a bare `<a download>` click. That gives the frontend no response status/body to inspect on 404/500, so there is no reliable way to surface a toast. The UX promise and implementation strategy conflict.

- Plan §9 assumes `Cmd/Ctrl+K` and `Esc` priority can be dropped into `src/ht_lens/api/static/js/utils/keyboard.js` cleanly. Current `attachKeyboard()` exits early for `input, textarea` and always routes `Escape` to `onClosePanel`. Without a deliberate exception, search will not open from the chat input and Esc will close the panel before the search modal.

- Export markdown in plan §2 says message content is kept “그대로” and not escaped. That assumes nested markdown is harmless. It is not. Phase 5 already renders assistant markdown in `src/ht_lens/api/static/js/components/chat_panel.js`; headings, code fences, or raw HTML inside a message can break the outer export structure.

## 3. Edge cases

- Search hits where both `blocks.original_text` and `translations.translated_text` match. Plan §1 says “original 우선” but does not define which occurrence `match_start`/`match_end` point to when the term appears multiple times or after preview truncation. The client can highlight the wrong text.

- Search navigation via `viewer.html?doc=X&page=Y&block=B` is riskier than the plan admits. `src/ht_lens/api/static/js/viewer.js::parseQuery()` currently ignores `block`, `bootstrap()` restores panel state from localStorage, and `scrollIntoView` must happen after page render. This is exactly the kind of state ordering bug that already caused Phase 5 regressions.

- `POST /blocks/{block_id}/retranslate` against a block with an open thread can desync UI state. `ThreadDetail.block.translated_text` comes from `src/ht_lens/api/routers/threads.py::_block_to_schema`, but the plan only mentions opportunistic client-side cache mutation. A partial refresh path can leave the page overlay updated while the chat panel still shows the stale translation.

- Concurrent retranslate or concurrent CLI `src/ht_lens/translate/pipeline.py::translate_document()` on the same block/document is unresolved. Both paths upsert the same `translations` row with no version check or lock. `ROADMAP.md` explicitly lists this collision risk for Phase 6a, but the plan does not actually mitigate it.

## 4. Alternative approaches

- Use SQLite FTS5 now. `ROADMAP.md` already names “SQLite LIKE vs FTS5” as the core search risk, and FTS5 adds no new Python/JS dependency. If the phase DoD hard-requires 10K blocks under 200ms, choosing the architecture least likely to meet it is the wrong tradeoff.

- For retranslate, extract a shared single-block translation service from `src/ht_lens/translate/pipeline.py` and call it from the new router. The current plan duplicates cache-key generation, upsert behavior, model-name handling, and likely error mapping. Translation semantics should not diverge between CLI translate and API retranslate.

- Server-side markdown export is the right choice. If you still want frontend error toasts, switch only the download mechanism to `fetch` + `Blob` instead of the anchor-click trick.

## 5. Missing tests

- Add `test_search_10k_blocks_meets_latency_budget`. Without it, the team cannot honestly claim the Roadmap Phase 6a search DoD. A 102-block benchmark plus “추정만” is not evidence.

- Add `test_keyboard_cmd_k_works_from_chat_textarea_and_escape_closes_search_first`. `src/ht_lens/api/static/js/utils/keyboard.js` currently has the opposite behavior, so grep-only checks in `tests/integration/test_static_serving.py` are not enough.

- Add `test_search_result_block_param_restores_target_block_after_navigation` and `test_search_translated_only_match_builds_correct_preview_span`. The plan introduces both the `block` URL contract and dual-field highlighting but does not lock either.

- Add `test_retranslate_transient_llm_error_returns_502_and_preserves_existing_translation` and `test_retranslate_failed_llm_call_writes_no_partial_row`. `src/ht_lens/api/routers/messages.py` already enforces this pattern for chat; the new router should match it.

- Add `test_export_markdown_fences_assistant_markdown_content` and `test_export_markdown_handles_multiline_original_and_translated_text`. Current export tests only validate counts/order/headers, not whether the produced markdown is actually readable.
