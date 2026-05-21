## 1. Over-engineering

- The markdown stack in [phase-5 plan](/home/hyunlord/github/ht_lens/.claude/phases/phase-5/plan.md:42) is larger than the DoD requires. `marked + DOMPurify + highlight.js + 3 language packs + theme + LICENSE bundling` is a lot of moving parts for a phase whose roadmap only says “마크다운/코드블럭 렌더링”; syntax highlighting and external-link hooks can wait until Phase 6.

- The client state model in [phase-5 plan](/home/hyunlord/github/ht_lens/.claude/phases/phase-5/plan.md:20) and [later state section](/home/hyunlord/github/ht_lens/.claude/phases/phase-5/plan.md:249) is overbuilt before the basic chat loop is proven. `threadsByDoc`, `messagesByThread`, `creatingThreadFor`, tab scroll restoration, `lastDocId/lastPageNum`, and panel persistence are a lot of cache invalidation surface on top of a viewer that is currently URL-driven in [state.js](/home/hyunlord/github/ht_lens/src/ht_lens/api/static/js/state.js:3).

- “Phase 6 미리 준비” in [phase-5 plan](/home/hyunlord/github/ht_lens/.claude/phases/phase-5/plan.md:348) is explicit scope creep. Reuse for future search/export/SSE is not a Phase 5 DoD item in `ROADMAP.md`; designing around future phases now is exactly how this frontend becomes harder to reason about than the current product warrants.

## 2. Hidden assumptions

- The vendor plan assumes the downloaded minified files are importable ES modules: see [phase-5 plan](/home/hyunlord/github/ht_lens/.claude/phases/phase-5/plan.md:49) and the imports in [render_markdown.js sketch](/home/hyunlord/github/ht_lens/.claude/phases/phase-5/plan.md:54). That is not guaranteed for `marked.min.js`, `highlight.min.js`, or `purify.min.js`; if even one is UMD/IIFE, `viewer.html` fails at boot.

- The plan assumes the write endpoints already fit the UI state model, but [explain_thread()](/home/hyunlord/github/ht_lens/src/ht_lens/api/routers/messages.py:84) and [post_message()](/home/hyunlord/github/ht_lens/src/ht_lens/api/routers/messages.py:135) return only the assistant row. The user row is written to the DB but never returned, so `messagesByThread` cannot be correct unless the client does optimistic append or immediate refetch; the plan never says which.

- The DoD mapping for “닫았다 다시 열어도 핀/스레드 그대로” in [phase-5 plan](/home/hyunlord/github/ht_lens/.claude/phases/phase-5/plan.md:419) quietly assumes panel state is equivalent to thread persistence. But the same plan explicitly does not persist `activeThreadId` at [line 278](/home/hyunlord/github/ht_lens/.claude/phases/phase-5/plan.md:278), while the current viewer treats only `doc/page` as URL truth in [viewer.js](/home/hyunlord/github/ht_lens/src/ht_lens/api/static/js/viewer.js:15). On reload, you cannot actually restore the open thread.

## 3. Edge cases

- Multiple threads on one block are already legal. [create_thread()](/home/hyunlord/github/ht_lens/src/ht_lens/api/routers/threads.py:78) has no uniqueness guard, and [list_threads()](/home/hyunlord/github/ht_lens/src/ht_lens/api/routers/threads.py:41) returns all rows, but the pin design in [phase-5 plan](/home/hyunlord/github/ht_lens/.claude/phases/phase-5/plan.md:145) assumes a single `threadsByBlock.get(blockId)` and one tooltip title.

- `/explain` is explicitly non-idempotent today; [test_explain_is_not_idempotent](/home/hyunlord/github/ht_lens/tests/integration/test_api_messages.py:84) locks that in. The plan only dedupes `POST /threads` at [phase-5 plan](/home/hyunlord/github/ht_lens/.claude/phases/phase-5/plan.md:314), so double-clicking “설명 요청” or repeated `Cmd/Ctrl+Enter` can create duplicate user/assistant pairs.

- Phase 4’s stale-response guard only covers document/page loads via `navToken` in [viewer.js](/home/hyunlord/github/ht_lens/src/ht_lens/api/static/js/viewer.js:35). Phase 5 adds async thread-list, thread-detail, and message-post flows, but the plan never extends cancellation to them; a slow response from page A can repaint the panel after the user has already navigated to page B.

## 4. Alternative approaches

- Use `GET /threads/{id}` as the client cache unit and refetch it after every successful write. [get_thread()](/home/hyunlord/github/ht_lens/src/ht_lens/api/routers/threads.py:140) already returns ordered history plus block/page metadata, which is simpler than maintaining `messagesByThread` against assistant-only write responses.

- Do not generate default thread titles in the browser. Let the server’s [_default_thread_title()](/home/hyunlord/github/ht_lens/src/ht_lens/api/routers/threads.py:172) remain the single source of truth, which is already covered by [test_create_thread_with_default_title](/home/hyunlord/github/ht_lens/tests/integration/test_api_threads.py:14); the client-side title logic in [phase-5 plan](/home/hyunlord/github/ht_lens/.claude/phases/phase-5/plan.md:218) duplicates that contract for no real gain.

- For markdown, `marked + DOMPurify` is enough this phase. If syntax highlighting matters later, add it once there is an actual browser runtime test harness; right now `highlight.js` is extra complexity with no matching verification depth.

## 5. Missing tests

- `test_viewer_runtime_imports_vendor_modules` should exist. The current static checks in [test_static_serving.py](/home/hyunlord/github/ht_lens/tests/integration/test_static_serving.py:23) only prove 200 responses and grep markers; they will not catch a broken ESM import or runtime exception in `viewer.html`.

- `test_chat_post_roundtrip_shows_user_and_assistant_messages` should exist. It needs to lock the exact UI behavior after one `POST /threads/{id}/messages`, because the backend contract in [messages.py](/home/hyunlord/github/ht_lens/src/ht_lens/api/routers/messages.py:130) does not return the full exchange.

- `test_multiple_threads_same_block_show_single_pin_and_distinct_sidebar_entries` should exist. The backend already permits that state, and the plan currently has no proof that pin rendering and thread navigation stay coherent.

- `test_reload_restores_active_thread_or_intentionally_closes_panel` should exist. The roadmap DoD promises persistence, but the plan currently persists `panelOpen` without persisting `activeThreadId`, which is an obvious mismatch.

- `test_markdown_sanitization_strips_script_and_javascript_href` should exist. A screenshot of a fenced code block is not enough when model output is flowing through `DOMPurify` hooks and HTML-profile sanitization in [phase-5 plan](/home/hyunlord/github/ht_lens/.claude/phases/phase-5/plan.md:69).
