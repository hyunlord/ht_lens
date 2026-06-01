## 1. Over-engineering

- The plan bundles two unrelated risks into `.claude/phases/phase-8e-1/plan.md`: math-loss recovery in `src/ht_lens/translate/chunk_pipeline.py` and a MinerU bold backend spike in `src/ht_lens/extract_mineru/runner.py`. ROADMAP Phase 8e DoD is “7 docs 2.0 DB 완료 / reflow viewer에서 전체 읽기 / 1.x 롤백 가능”; bold extraction is not a blocker for migration and should be deferred unless it is already proven CPU-feasible.

- `_segment_translate(text, ...)` is too much machinery for six known doc7 failures. It adds sentence splitting, per-segment translation, reassembly semantics, and new partial-failure states when the direct lever is simply retrying `_translate_protected` after `restore_math(...).missing` is non-empty.

- The sentinel “format candidate” experiment risks turning a narrow bug fix into empirical prompt engineering. `math_protect.py` already has `token_prefix`; changing `PH_OPEN` / `PH_CLOSE` globally expands the blast radius across `tests/unit/test_math_protect.py`, `short_retranslate.py`, and existing 8b contracts.

- The plan’s “possible reingest + reflow `<strong>` render verification” for bold is premature. `render_markdown.js` already supports marked GFM per the plan itself, so testing Markdown bold rendering is not the hard problem; MinerU extraction fidelity is.

## 2. Hidden assumptions

- The plan assumes qwen’s placeholder loss is stochastic and retryable. If the model deterministically drops the same sentinel for a given prompt, “bounded 재번역” in `_translate_protected` only burns extra calls and still fails the DoD evidence.

- The plan assumes the six doc7 failures are caused by sentinel shape. Chunk 72 having one inline span proves “many placeholders” is insufficient, but it does not prove U+27E6/U+27E7 is the cause. The real cause could be prompt refusal, output truncation, provider stop tokens, or `llm.translate` returning a malformed/empty response.

- `translate_chunks_command` in `src/ht_lens/cli.py` does not expose `max_retries`; it calls `translate_chunks(... retry_failed=retry_failed)` with the current default. The plan says “N회(기본 2)” but does not say whether CLI behavior, function default, or test-only parameters change.

- Segment fallback assumes sentence boundaries are safe units for academic prose. In math-heavy PDF text, boundaries often include “Eq. 28.116”, “Fig. 3.”, initials, decimal values, and formula-adjacent “where”; naive regex splitting will degrade exactly the content Phase 8d-2c had to repair.

- The bold spike assumes `run_mineru(... backend="vlm"/"hybrid")` maps cleanly to MinerU 3.2.1 CLI backend names. The plan cites `-b pipeline` but does not verify the exact accepted backend strings or whether `CUDA_VISIBLE_DEVICES=""` must be disabled for VLM attempts.

## 3. Edge cases

- Duplicate chunks using `pending_futures` in `translate_chunks`: one math-loss failure currently fans out to all waiters for the same `cache_key`. New math-loss retry must ensure the owner future retries internally before setting an exception, or identical chunks can all fail from one dropped placeholder.

- Body and caption translation share the same chunk status. If `chunk.content` succeeds but `chunk.caption` loses math, `_process` marks the whole `ChunkTranslation` failed and discards the body. The plan does not cover image/table captions with inline math.

- Segment fallback has contradictory semantics: the plan says “missing 0인 세그먼트만 결합” but also “일부 실패 시 status='failed'(영어 fallback)”. It must choose one. Writing a partially Korean string into a failed row is useless because `src/ht_lens/api/routers/reflow.py` suppresses failed translations.

- `math_protect.py` intentionally does not handle `\(...\)` or `\[...\]`; `short_retranslate.is_math_dense` explicitly detects those as math. If MinerU emits escaped delimiters in some docs, the new retry loop will not protect them and the 8b byte-identical contract is not actually covered.

- Currency false positives like `$5 to $10` are currently “safe” only because restoration is byte-identical. Segment fallback may isolate such text and leave monetary phrases untranslated or cause the LLM to restructure around placeholders unnaturally.

## 4. Alternative approaches

- Start with the smallest fix: move `restore_math` validation inside a retry loop in `_translate_protected`, without segment fallback or global sentinel changes. This directly addresses the identified unused lever and is easy to lock with `test_math_loss_retries_before_failed`.

- Prefer an ASCII sentinel change as a single controlled constant only if live evidence shows retry alone fails. For example, add a local sentinel strategy to `protect_math` while preserving `PH_OPEN` / `PH_CLOSE` compatibility in tests, instead of broad “candidate” experimentation.

- Use the existing Phase 8d-2c explicit retranslation path for the six known chunks as a fallback before inventing generic sentence segmentation. `src/ht_lens/translate/short_retranslate.py` already handles context-specific retranslations with `cache_key=NULL`; extending that pattern is safer than content-cache poisoning.

- For bold, first inspect MinerU `content_list.json` / markdown outputs for span-level style metadata before running GPU backends. If the structured output has no bold signal under CPU `pipeline`, document “not available in current extractor” and defer the VLM decision to 8e-2 or a separate spike.

## 5. Missing tests

- Add `test_math_loss_retries_same_chunk_until_placeholder_restored` in `tests/integration/test_chunk_translate.py`: first LLM call drops `⟦MATH0⟧`, second preserves it, final row is `status="translated"` and math is byte-identical.

- Add `test_math_loss_retry_exhaustion_preserves_failed_no_cache`: repeated placeholder loss writes `status="failed"`, `translated_text=""`, and no reusable translated row exists for the source `cache_key`.

- Add `test_math_loss_retry_with_duplicate_chunks_only_calls_until_success_once`: two identical chunks should share the recovered future and end as one translated plus one cached, not two failures or duplicate retry storms.

- Add `test_caption_math_loss_does_not_discard_successful_body_without_policy`: force body success and caption math loss; assert the intended all-or-nothing behavior explicitly.

- Add `test_segment_fallback_does_not_split_equation_references_or_decimals` if `_segment_translate` survives challenge. Include “Eq. 28.116”, “Fig. 2.”, “p=0.05”, and formula-adjacent “where”.

- Add a MinerU runner test such as `test_run_mineru_accepts_backend_parameter_without_forcing_cpu_for_gpu_mode` before any bold backend work; otherwise the spike can silently test the wrong execution mode.
