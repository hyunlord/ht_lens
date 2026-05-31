## 1. Verification of automated checks

The verify report is not stale relative to tracked code: `72a015a` is the last code/test commit and `85c99de` only adds `.claude/phases/phase-8d-2b/verify.md`; `git diff HEAD -- src tests .claude/phases/phase-8d-2b/verify.md` is empty. The current untracked placeholder `verify-cross.md` does not indicate a prior committed round.

The lint/format/type/test evidence in `.claude/phases/phase-8d-2b/verify.md:8-11` is plausible and reported against current HEAD, but I did not independently rerun the 577s pytest suite. Coverage is weaker evidence: `.claude/phases/phase-8d-2b/verify.md:12` gives percentages but no command or raw report. CI is explicitly not run (`verify.md:13`), which is acceptable only as a disclosed gap, not a passed check.

## 2. Verification of functional checks

The ROADMAP Phase 8d DoD is chunk chat, figure caption+neighbor chat, pins, and cross-doc RAG (`ROADMAP.md:244-248`). This phase targets the remaining figure/cross-doc/top-K slice; pins and base chunk chat came from 8d-2a.

Cross-doc RAG is exercised for a normal text chunk via `test_post_message_returns_related_chunks` (`tests/integration/test_chunk_chat_api.py:333-347`), including API response refs. However, cross-doc behavior is not tested for section anchors or figure anchors, even though those paths now route through different query construction in `src/ht_lens/api/routers/chunk_chat.py:183-214`.

Figure context is covered as a pure builder (`tests/integration/test_chunk_chat_context.py:206-233`) and the UI label is covered (`tests/integration/test_chat_ui_js.py:218-239` per grep), but there is no API-level post to an image-anchored thread asserting the LLM system prompt actually receives the caption+neighbor context through `_build_context` (`chunk_chat.py:190-191`).

Within-section top-K is not functionally verified. The only cited test is the empty-hit fallback (`tests/integration/test_chunk_chat_context.py:237-265`). There is no positive test that an over-budget section with embeddings selects relevant hits, orders them correctly, or stays within any context budget.

The accepted cross-lingual relevance test is missing. Challenge required `test_korean_question_retrieves_english_chunk` (`.claude/phases/phase-8d-2b/challenge.md:35`, also R9 at `:48`), but `rg` finds only a comment in `tests/integration/test_chunk_search.py:3-5`, not a test.

## 3. Score audit

독창성 / 15: `12/15` is mostly justified. The separate `build_section_context_topk` avoids polluting the old deterministic renderer, and the figure-as-chunk anchor preserves the schema. I would deduct one more point because section RAG now has split query semantics across top-K and cross-doc without a clear contract. Fair: `11/15`.

완결성 / 35: `31/35` is too high. Figure and text cross-doc have partial evidence, but positive top-K is not tested, figure API integration is not tested, and the promised cross-lingual test is absent despite challenge acceptance. Fair: `27/35`.

안정성 / 30: `28/30` is not supported. The report claims embedding failure is graceful (`verify.md:35-36`), but that only covers chunk cross-doc failure. Section anchors call `encode_query` before any protective `try` (`chunk_chat.py:183-189`), so an embedding failure breaks section chat before LLM/write. Fair: `23/30`.

확장성 / 20: `17/20` is slightly high but defensible. `RelatedChunkRef` is a useful contract, and brute-force is knowingly deferred. Deduct for the top-K budget gap and lack of section/figure RAG tests before 8e scales to seven docs. Fair: `15/20`.

Suggested total: `76/100`.

## 4. Issues missed (new this round)

Section chat now has an embedding-failure regression. In 8d-2a, section chat could build deterministic context without embeddings. In this phase, `_build_context` calls `encode_query(embedding_client, question)` whenever an embedding client exists (`src/ht_lens/api/routers/chunk_chat.py:183-189`). That call is outside the `_cross_doc_refs` best-effort `try` (`:208-218`). `test_chat_graceful_on_embedding_failure` only covers chunk anchors (`tests/integration/test_chunk_chat_api.py:351-366`), so section anchors can 500 on embedding backend failure.

`build_section_context_topk` has no positive-path test and appears to ignore its own budget once hits exist. It uses `budget` only to decide whether the section is large (`src/ht_lens/api/chunk_chat_context.py:280-281`), then includes heading plus up to six hit chunks without checking cumulative text length (`:282-307`). A few long chunks can produce a much larger prompt than the degraded budgeted path it replaces.

The figure router branch is untested. The code branches on `anchor.type == "image"` in `_build_context` (`src/ht_lens/api/routers/chunk_chat.py:190-191`), but the tests only cover the builder directly and the frontend label. A wiring mistake in thread creation/posting for image chunks would pass the current suite.

The cross-lingual acceptance item was silently downgraded from a test to a comment/live assertion. `.claude/phases/phase-8d-2b/challenge.md:35` explicitly accepted a `test_korean_question_retrieves_english_chunk`; no such test exists. Given embeddings are source English (`src/ht_lens/embedding/chunk_backfill.py:8-11`) and user questions are Korean, this remains a real quality risk for within-section top-K and cross-doc search.

## 5. Verdict

**REJECT** — The self-verification is honest about an `88/100`, but it misses a concrete section-chat regression and overstates top-K coverage. RE-CODE should add graceful fallback around section query embedding, add a positive within-section top-K test that locks relevance and prompt size behavior, and add API-level image-anchor posting coverage. The current evidence is not strong enough to push as a completed 8d-2b verification.
