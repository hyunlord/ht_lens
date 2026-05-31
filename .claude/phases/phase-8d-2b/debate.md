## 1. Over-engineering

The plan exceeds ROADMAP Phase 8d’s DoD. ROADMAP only requires chunk click chat, figure caption+neighbor chat, chunk pins, and cross-doc RAG; `.claude/phases/phase-8d-2b/plan.md` also adds within-section top-K, neighbor retranslation, and chat panel resizing. `translate-chunks --short-only` is not a Phase 8d deliverable and should be deferred to Phase 8e where the plan already says “6곳 영어 fallback” belongs.

`build_section_context(..., question=None, embedding_client=None)` mixes context construction with retrieval orchestration. `src/ht_lens/api/chunk_chat_context.py` currently returns a deterministic `ChatContext`; adding embedding dependencies there makes tests and failure behavior depend on model availability. Keep section truncation stable in 8d-2b unless it is explicitly needed for the ROADMAP DoD.

The new `embedding/chunk_search.py` largely duplicates `src/ht_lens/embedding/search.py` and `store.load_all`. Some duplication is acceptable for block/chunk isolation, but the plan should not copy every Phase 7a detail without deciding whether chunk-specific metadata, translated previews, and `page_idx` links need different contracts.

Resize is pure UI polish and unrelated to “cross-doc RAG (chunk)” or “figure 클릭 → caption+이웃 기반 설명.” It adds DOM, CSS, storage, and jsdom test surface to the same phase as backend retrieval and LLM behavior, increasing regression risk in `src/ht_lens/api/static/js/chat.js` and `css/reflow.css`.

## 2. Hidden assumptions

The plan assumes Korean questions can retrieve English source embeddings. `src/ht_lens/embedding/chunk_backfill.py` explicitly embeds `Chunk.content`, not `ChunkTranslation.translated_text`; within-section top-K encodes the user question and compares it to source English chunks. That depends on bge-m3 cross-lingual quality, but the plan has no quality gate or fallback when Korean→English similarity is poor.

It assumes adding refs to `/v2/threads/{thread_id}/messages` is mechanically simple. `src/ht_lens/api/schemas.py` currently defines `ChunkMessageRead` with only `id/role/content/model/created_at`, and `src/ht_lens/api/routers/chunk_chat.py::post_message` returns an ORM `ChunkMessage`. Returning `refs` requires constructing a schema response, not just adding fields.

It assumes API embedding access exists in chunk chat. `post_message` currently injects `session`, `llm`, and `sem`, but not `get_embedding_client`; the plan mentions “embedding_client None” without specifying the dependency wiring or how app/test overrides in `tests/integration/_api_helpers.py` will provide it.

It assumes `content<60자` identifies bad short translations. That threshold is language- and type-sensitive: headings, equation labels, table cells, and captions can be legitimately short. Overwriting `ChunkTranslation` also invalidates any cached translation semantics while embeddings remain source-content based.

## 3. Edge cases

Empty or partial `chunk_embeddings` will be common: the plan states doc7 has `chunk_embeddings=0`, and `chunk_backfill` only embeds `type in (text, heading)` with source length >=30. `search_chunks(within_chunk_ids=...)` can return no hits for sections made mostly of equations, captions, tables, or short chunks; the plan needs an explicit fallback to the 8d-2a degraded context.

Figure anchors are fragile. Image chunks often have empty `content`, and captions may be empty; `get_or_encode_chunk_vector(anchor)` over an image chunk would encode an empty string unless cross-doc refs use caption+neighbors as the query text. The plan says figure chat uses `build_figure_context`, but cross-doc refs in `post_message` still appear anchor-based.

`min_chars=50` copied from block search can drop exactly the chunks this phase cares about: figure captions, theorem statements, numbered equations, and short academic definitions. That interacts badly with within-section top-K and cross-doc search.

The plan does not address zero-vector or wrong-dimension queries. `search.py` raises on dimension mismatch and normalizes nonzero vectors; `get_or_encode_chunk_vector` will likely mirror block lookup, but empty chunks or disabled embedding clients must not convert a user chat request into a 500.

Concurrent chat deletion behavior must be preserved. `chunk_chat.py::post_message` currently avoids orphan messages by doing the LLM call before DB writes and rechecking after `session.rollback()`. Adding cross-doc search before/after the LLM call must not reintroduce half-written user messages or stale thread snapshots.

## 4. Alternative approaches

Split this phase into a narrow backend RAG slice first: implement `load_all_chunks`, `search_chunks`, `get_or_encode_chunk_vector`, and chunk refs in `post_message`; defer resize and `--short-only` retranslation. That better matches ROADMAP 8d and gives one behavioral axis to verify.

Instead of embedding logic inside `build_section_context`, add a separate `build_section_context_topk` or a small retrieval service called by `chunk_chat.py::post_message`. That keeps `chunk_chat_context.py` as a pure context renderer and makes “embedding unavailable” handling explicit at the router layer.

Use the existing `RelatedBlockRef` pattern in `src/ht_lens/api/chat_context.py` as the contract model, but create a `RelatedChunkRef` dataclass/schema with `chunk_id`, `doc_id`, `filename`, `page_idx`, `score`, `original_preview`, and `translated_preview`. Do not hide refs only in the system prompt; return them in the API response so UI and tests can verify them.

For figure RAG query text, build a synthetic query from `caption_translated or caption` plus neighbor bodies, rather than the image chunk’s empty `content`. This is a more direct architecture fit for the ROADMAP’s “caption + 이웃 chunk → qwen, vision 불필요.”

## 5. Missing tests

Add `test_chunk_post_message_returns_related_chunks_schema`: verifies `/v2/threads/{id}/messages` returns `related_chunks`/refs, not just that refs were inserted into the system prompt.

Add `test_chunk_chat_preserves_no_write_on_embedding_failure`: force chunk search or query encoding to raise before LLM success and assert no `ChunkMessage` rows are persisted.

Add `test_figure_cross_doc_query_uses_caption_and_neighbors_not_empty_content`: image chunk with empty `content`, non-empty caption, and seeded embeddings should produce refs or at least call encode with caption/neighbor text.

Add `test_within_section_topk_empty_hits_falls_back_to_degraded_context`: section over budget, all candidate chunks under `min_chars` or no embeddings, must still include the heading and deterministic truncated context.

Add `test_load_all_chunks_mixed_dim_keeps_ids_matrix_aligned`: mirror `tests/integration/test_embedding_store_mixed_dim.py` for `ChunkEmbedding`; this exact bug already occurred in block search.

Add `test_korean_question_retrieves_english_chunk_fixture`: seeded English chunk embeddings with a Korean query should pass a minimal relevance check, or the plan should stop assuming cross-lingual source embeddings are sufficient.

Add `test_short_only_does_not_retranslate_heading_equation_caption_only_chunks`: locks the `<60자` selector so it does not overwrite valid short headings, math-dense equations, or image caption-only rows.
