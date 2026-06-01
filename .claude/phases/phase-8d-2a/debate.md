## 1. Over-engineering

The plan duplicates the whole Phase 3/5 chat persistence stack as `chunk_threads`/`chunk_messages` instead of first proving a minimal v2 anchor path. Given `src/ht_lens/db/models.py:214` already has `Thread`/`Message`, the new parallel stack plus separate router/schemas/UI list is a lot for 8d-2a. A smaller core could add only section/chunk Q&A first, then pins/list management after the context path is proven.

“핀 = 앵커된 thread” is an overloaded model. The plan says `POST /v2/threads` both starts conversation and represents a pin, which will create empty threads just to pin a chunk/section. That complicates message counts, deletion semantics, and UI copy. Pin persistence should be separate or explicitly deferred.

Section Q with deterministic truncation (`build_section_context`, budget 6000) is trying to deliver the user’s “핵심 가치” while knowingly deferring the only relevance mechanism to 8d-2b. For large sections, this may produce confidently bad answers. The plan should narrow 8d-2a to small/medium section Q and make large-section behavior a hard degraded state, not a core feature.

The frontend scope is too broad: drawer, selection state, message UI, assistant markdown rendering, pins list, click jump, and integration with `reflow.js` all in one subphase. `src/ht_lens/api/static/js/reflow.js:145` is still a compact single-module loader; adding chat side effects there risks turning 8d-2a into a frontend rewrite.

## 2. Hidden assumptions

The plan assumes `sec_no` is unique per document. `sections.js` keys section identity only by parsed numeric prefix (`src/ht_lens/api/static/js/sections.js:14`), but real books repeat numbers in appendices, chapter excerpts, examples, or references. If `28.4` appears twice, `section_chunks(doc_id, sec_no)` will pick the wrong range or merge intent ambiguously.

It assumes numeric dotted headings are sufficient. Existing tests explicitly treat `Appendix A.1` as unparseable (`tests/integration/test_reflow_sections_js.py:90`), so section chat will silently fail for appendices or non-numbered academic sections unless the plan defines fallback anchors.

The migration design assumes the `doc_id` on `chunk_threads` stays consistent with `chunk_id`. A CHECK can enforce chunk-vs-section XOR, but not “this `chunk_id` belongs to this `doc_id`.” Without explicit validation in `POST /v2/threads`, `/v2/documents/{id}/threads` can show anchors for the wrong document.

The plan treats a 6000-character budget as a token budget. Mixed Korean, LaTeX, tables, and markdown can produce very different token counts. `llm.chat(..., system=block_ctx)` in `src/ht_lens/api/routers/messages.py:120` has no local token guard, so section prompts can still exceed provider limits once history is included.

It assumes Python porting of `computeSectionChunks` will remain identical to the JS implementation. The JS relies on response order because `ReflowChunk` does not expose `order_idx` (`src/ht_lens/api/static/js/sections.js:26`); the server path will query by `order_idx`. Drift between the two will be hard to see unless tested against the same fixture.

## 3. Edge cases

Duplicate or repeated section numbers must be handled. Two headings with the same `secNo` should not both map to one `/v2/threads` section anchor, and selecting the second one in the UI currently emits only `{secNo, chunkIds}` (`src/ht_lens/api/static/js/sections.js:95`), not a heading chunk id.

Sections with no following same-or-shallower heading can span to document end. For a chapter-level heading near the start, `build_section_context` may include hundreds of chunks, then keep only the first budget slice. That will bias answers toward introductions and miss the selected subsection’s actual relevant passage.

Failed or missing translations need defined context behavior. `get_reflow` hides failed translations by returning `translated=None` (`src/ht_lens/api/routers/reflow.py:109`), but the plan says “번역 우선(없으면 원문)” without distinguishing untranslated, failed, image-only, equation, or table chunks. The LLM context can become mixed Korean/English/LaTeX without labels.

Concurrent message posts to the same thread can race. The old router loads history before the LLM call and writes after (`src/ht_lens/api/routers/messages.py:175`), so two simultaneous posts can both answer stale history. The v2 plan reuses that pattern but adds longer section prompts, making the race more likely.

Deleting a thread during an in-flight message is unspecified. `DELETE /v2/threads/{id}` plus “LLM-call→DB-write” can produce a late write into a deleted parent unless FK enforcement and error handling are tested.

## 4. Alternative approaches

Use a stable section anchor of `(doc_id, heading_chunk_id)` instead of only `(doc_id, sec_no)`. `sec_no` is display identity; `heading_chunk_id` is the actual source row. This avoids duplicate-section ambiguity and lets the server compute range from a concrete heading.

For 8d-2a, expose `order_idx` or `section_id` in `/v2/documents/{doc_id}/reflow` and have the UI send the selected heading chunk id. The current API model in `src/ht_lens/api/routers/reflow.py:49` omits `order_idx`, forcing both client and server to infer identity through text parsing.

Consider a separate `chunk_pins` table instead of treating empty threads as pins. Threads are conversation containers; pins are bookmarks. Keeping them separate makes message counts, deletion, and “question list” behavior clearer.

For context building, reuse the existing `build_block_context_with_refs` structure conceptually but return a typed object: rendered prompt text plus included chunk ids and truncation metadata. That would make API tests assert what the model actually saw, not just that a response was persisted.

## 5. Missing tests

Add `test_create_chunk_thread_rejects_chunk_doc_mismatch`: create two docs, pass `doc_id` for doc A and `chunk_id` from doc B, assert 422/400 and no row.

Add `test_section_context_duplicate_secno_uses_selected_heading_chunk`: two `28.4` headings in one doc must not resolve to the first one when the UI selected the second. This likely requires changing the anchor contract.

Add `test_section_context_appendix_or_unnumbered_heading_graceful`: `Appendix A.1` or an unnumbered heading should either be selectable with a stable heading anchor or return a clear unsupported-section error.

Add `test_v2_message_llm_failure_writes_no_messages`: mirror the old router’s transaction guarantee from `src/ht_lens/api/routers/messages.py:3`; if chat LLM raises, neither user nor assistant row should persist.

Add `test_v2_delete_thread_during_inflight_message_no_orphan`: simulate delete before DB write and assert no orphaned `chunk_messages` and a deterministic API error.

Add `test_build_section_context_reports_truncation_metadata`: for over-budget sections, assert the prompt includes heading, included chunk ids are deterministic, and the response can expose/record that the answer used only a partial section.

Add `test_chat_markdown_sanitizes_assistant_html`: marked/DOMPurify is mentioned, but the plan needs a malicious assistant payload test proving `<script>`/event handlers do not survive rendering.
