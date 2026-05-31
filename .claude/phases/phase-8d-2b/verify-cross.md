## 1. Verification of automated checks

The v2 verify report is not stale for tracked source/tests: `dbd7281` only updates `verify.md`, and the last code/test commit it cites is current (`4e5171a`, after `3aba497`). Current `git status` has only untracked `.claude/phases/phase-8d-2b/summary.md`, so no source/test drift after verification.

The lint/format/type/test evidence in `.claude/phases/phase-8d-2b/verify.md:8-11` is credible but not independently rerun here. The reported fast suite excludes the new cross-lingual test by design: `pyproject.toml:71-75` registers `llm`, and `verify.md:11,15` reports 8 deselected. Coverage remains weak evidence: `verify.md:12` gives target percentages without command/raw output. CI is explicitly not run (`verify.md:13`), properly disclosed as n/a rather than passed.

## 2. Verification of functional checks

The Round 1 concrete defects were materially addressed. Section embedding failure is now inside a `try` with deterministic fallback in `src/ht_lens/api/routers/chunk_chat.py:183-196`, and `test_section_chat_graceful_on_embedding_failure` locks the API behavior at `tests/integration/test_chunk_chat_api.py:370-384`. The top-K budget cap exists at `src/ht_lens/api/chunk_chat_context.py:294-306`, and the positive relevance/budget test exists at `tests/integration/test_chunk_chat_context.py:283-329`.

Figure caption+neighbor chat is now API-level tested: `test_figure_anchor_post_uses_figure_context` posts to an image-anchored thread and checks caption/neighbors in the LLM system prompt (`tests/integration/test_chunk_chat_api.py:388-449`). Cross-lingual is present as an `@pytest.mark.llm` test at `tests/integration/test_chunk_search.py:187-246`; because it is excluded from the fast run, the evidence is test-presence rather than routine regression protection.

One Round 1 coverage concern is unchanged since Round 1: cross-doc RAG is still API-tested only for a normal text chunk (`tests/integration/test_chunk_chat_api.py:333-347`). Figure-specific cross-doc query wiring (`chunk_chat.py:216-218`) and section-anchor cross-doc behavior are not exercised end-to-end. The builder covers figure `query_text` (`tests/integration/test_chunk_chat_context.py:220-247`), but not the router’s `_cross_doc_refs` branch with returned `related_chunks`.

## 3. Score audit

독창성 / 15: `12/15` is justified. The chunk search machine, `RelatedChunkRef`, figure-as-image-chunk routing, and separate `build_section_context_topk` are reasonable extensions of prior patterns. Confirm `12/15`.

완결성 / 35: `31/35` is mostly justified after R1 fixes, but slightly high. ROADMAP DoD items for figure chat and chunk cross-doc are covered, but cross-doc API coverage is narrow to text chunk anchors, and the original plan’s neighbor retranslation/resize were deferred to 8d-2c despite being listed “In” in `plan.md`. Fair: `30/35`.

안정성 / 30: `28/30` is defensible but a little optimistic. The real section 500 regression is fixed and tested, but the new budget-cap path has only the happy “first relevant hit fits” case; it does not cover an oversized top hit followed by smaller usable hits. Fair: `27/30`.

확장성 / 20: `17/20` is justified. Brute-force is consciously deferred, and the schemas/contracts are clean enough for 8e. The remaining concern is that stored-vector reuse in `get_or_encode_chunk_vector` keys only on `source_hash` (`src/ht_lens/embedding/lookup.py:59-63`), so mixed-model future migrations can silently yield dim mismatch/no refs. Confirm with caution: `17/20`.

Suggested total: `86/100`.

## 4. Issues missed (new this round)

The budget-cap RE-CODE introduced an untested “oversized first hit” behavior. `build_section_context_topk` breaks immediately when a hit does not fit (`src/ht_lens/api/chunk_chat_context.py:302-304`). If the most similar chunk is too long but the next hit would fit, the function returns heading-only top-K context rather than continuing. The new test at `tests/integration/test_chunk_chat_context.py:283-329` does not cover this branch.

Figure cross-doc RAG remains untested unchanged since Round 1. The post-RE-CODE API test proves image anchors use caption+neighbors for the system prompt, but it does not provide an embedding client or a second document, so it cannot catch a bug in `_cross_doc_refs` for `anchor.type == "image"` (`src/ht_lens/api/routers/chunk_chat.py:216-221`) or verify `related_chunks` for figures.

Section cross-doc semantics are still thin. Section top-K uses the user question vector for within-section context (`chunk_chat.py:186-188`), but cross-doc refs for a section still use the heading chunk via `get_or_encode_chunk_vector` (`chunk_chat.py:216-220`). That may be an accepted contract (`verify.md:47` says cross-doc=anchor vec), but there is no test documenting that choice for section anchors.

The cross-lingual test is useful but not part of the fast quality gate. Since source embeddings are English and user questions are Korean, `test_korean_question_retrieves_english_chunk` being `@llm` and deselected means normal verification will not catch a regression in local multilingual retrieval assumptions.

## 5. Verdict

**DOWNGRADE** — The R1 blockers were fixed and the v2 self-assessment is substantially more credible, but `88/100` should come down slightly to about `86/100` for the untested budget-cap edge case and the still-uncovered figure/section cross-doc router paths. I would not recommend another broad RE-CODE at the two-round cap; these are concrete follow-up tests/design locks, not evidence that the phase is fundamentally broken.
