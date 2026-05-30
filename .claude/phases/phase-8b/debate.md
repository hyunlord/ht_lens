## 1. Over-engineering

- `.claude/phases/phase-8b/plan.md` proposes new `embedding/chunk_store.py` plus `chunk_backfill.py` while `src/ht_lens/embedding/store.py` already has generic vector serialization and SQLite upsert patterns. Creating a parallel store risks copy-paste drift; the phase only needs `chunk_id` storage, not a second embedding subsystem.

- The “missing placeholder recovery” strategy in `translate/math_protect.py` is too clever for Phase 8b. Appending lost formulas as a comment does not satisfy ROADMAP’s “byte-identical 보존”; it preserves bytes somewhere else while corrupting reading order and translation output. Missing placeholders should fail the chunk or mark it `failed`, not silently mutate content.

- Adding both `translate-chunks` and `embed-chunks` CLIs is reasonable, but the plan also pulls in “extract-mineru CLI 테스트 (8a 잔존)” under Phase 8b. That is explicitly 8a cleanup and should be separated unless it blocks 8b DoD.

- `chunk_translations.caption_translated` bakes image-specific behavior into the translation table while table captions and chart content already exist in `src/ht_lens/ingest_mineru/content_list.py`. A normalized “translated caption for any caption-bearing chunk” contract is needed, or defer caption translation until 8c rendering.

## 2. Hidden assumptions

- The plan assumes chunk types are `text/heading/equation/image/table`, but ROADMAP’s schema lists `title`, and Phase 7 block translation uses `header` in `src/ht_lens/translate/pipeline.py`. This mismatch will leak into filters such as `chunk_backfill: chunk.type in (text,heading)` unless explicitly locked.

- The plan says `cache_key=hash(content)` even though `src/ht_lens/translate/cache.py` keys on `(text, src, tgt, model)`. Hashing only content will reuse English-to-Korean translations across model upgrades or language pairs.

- “이웃 chunk context” is a ROADMAP Phase 8b deliverable, but the plan unilaterally moves it to 8d because it conflicts with dedup. That is a scope change, not just an implementation decision; the challenge document needs explicit Planner/user approval.

- `Semaphore(7)` assumes the same sglang capacity applies to chunk workloads. MinerU chunks can be much longer than old PyMuPDF blocks, especially tables, so 7-way concurrency may increase timeouts or context-length failures rather than preserve the Phase 7a-2 5.66x result.

- Embedding `chunk.content` assumes raw source text is the right retrieval source. Existing Phase 7a embeds `Block.original_text`, but Phase 8d Korean chat/RAG may work better against `chunk_translations.translated_text`. The plan should decide this now because `source_hash` semantics depend on it.

## 3. Edge cases

- The proposed inline regex `(?<!\$)\$[^$\n]+?\$(?!\$)` will mishandle escaped dollars, LaTeX text like `\text{$5}`, currency ranges such as `$5 to $10`, unmatched OCR dollars, and inline math split by line wrapping. These are common in academic PDFs.

- Placeholder delimiters `⟦MATHi⟧` can already appear in source text or be normalized/reordered by the LLM. A test for “source contains placeholder-looking text” is mandatory.

- Display math extraction with `$$...$$` first does not cover `\[…\]`, `\(...\)`, `\begin{equation}`, `align`, or MinerU equation chunks that store bare LaTeX without delimiters.

- Image handling ignores chart `content`: `parse_content_list()` maps `chart` to chunk type `image` while preserving `content`, but the plan translates only captions and sets `translated_text=""`. That loses chart text before Phase 8c/8d can use it.

- Table handling assumes markdown pipes are safe. MinerU tables may be HTML or LaTeX (`text_format` can matter), and translating raw markup can damage tags, column counts, escaped pipes, or math inside cells.

- The chunk pipeline plan does not mention cancellation, partial commits, `retry_failed`, or document status transitions. `src/ht_lens/translate/pipeline.py` has explicit contracts for these; dropping them will regress CLI resumability.

## 4. Alternative approaches

- Instead of duplicating `chunk_pipeline.py` from `translate_document`, extract the concurrency/cache/retry engine from `src/ht_lens/translate/pipeline.py` behind a small adapter for “translatable item”. That keeps Phase 7a-2 behavior testable in one place while still supporting chunk-specific type dispatch.

- Instead of `caption_translated`, store all chunk translation output in one row with fields that mirror the source: `translated_text` for `content`, plus a generic translated caption only when `Chunk.caption` exists. This covers images, charts, and tables consistently.

- For math protection, use a small tokenizer that scans characters and tracks escapes/delimiter kinds instead of regex-only matching. This avoids adding dependencies but handles escaped dollars and `\(...\)`/`\[...\]` deterministically.

- For embeddings, either parameterize the existing `embedding.store.upsert_embedding` over table/model class or create a tiny shared serialization/upsert helper. A full parallel `chunk_store.py` is only justified if chunk retrieval semantics diverge in Phase 8d.

## 5. Missing tests

- Add `test_chunk_translate_cache_key_includes_src_tgt_model`, proving model/language changes do not reuse stale chunk translations.

- Add `test_chunk_translate_peak_concurrency_is_bounded_and_parallel`, not just duplicate-content dedup. The DoD says Phase 7a-2 concurrency applies; counting one LLM call does not prove parallelism.

- Add `test_math_protect_escaped_dollar_and_latex_text_currency`, covering `\$`, `\text{$5}`, `$x=\$5$`, and `$5 to $10`.

- Add `test_math_protect_source_placeholder_collision`, where original text already contains `⟦MATH0⟧`.

- Add `test_chunk_translate_chart_image_preserves_content_and_caption`, because `chart` becomes `image` in `parse_content_list()`.

- Add `test_chunk_translate_table_html_not_corrupted`, with an HTML table containing math and pipes.

- Add `test_chunk_translation_fk_cascade_on_document_delete`, verifying `chunk_translations` and `chunk_embeddings` disappear when a 2.0 document is deleted.

- Add CLI tests: `test_translate_chunks_cli_schema_mismatch_exits_nonzero`, `test_translate_chunks_cli_retry_failed_only_reprocesses_failed`, and `test_embed_chunks_cli_embedding_client_unavailable_exits_cleanly`.

- Add `test_chunk_backfill_model_change_refreshes_existing_embedding`, matching the Phase 7a regression already fixed in `embedding/backfill.py`.
