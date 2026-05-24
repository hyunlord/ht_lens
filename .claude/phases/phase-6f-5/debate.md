## 1. Over-engineering

- The plan bundles two separate decisions: operational rollback and translation-policy redesign. `ROADMAP.md:320-328` says Phase 6f should reuse Phase 6e infra with “도메인 코드 변경 0”, but the plan edits `src/ht_lens/llm/openai_compat.py:176-184`. That is scope creep. Do the qwen rollback as pure config/container work first; defer prompt rewrites to a separate phase.

- Rewriting `OLLAMA_*` and committing `.env.backup.gemma4_<ts>` is unnecessary blast radius. `src/ht_lens/llm/factory.py:162-203` reads `TRANSLATE_LLM_*`, `CHAT_LLM_*`, and `LLM_*`; it does not read `OLLAMA_*`. The backup file is an ops artifact, not product code. Keep it out of the phase unless an automated rollback path actually consumes it.

- Hardcoding a Korean-specific policy into `OpenAICompatibleClient._translate_system()` couples provider transport to translation strategy. That client is currently the generic OpenAI-compatible transport layer. If prompt tuning is worth shipping, it should live in a translate-policy layer, not inside the backend adapter.

## 2. Hidden assumptions

- The plan assumes the A/B harness matched the production call shape in `src/ht_lens/llm/openai_compat.py:84-99` exactly: same `top_p`, `presence_penalty`, `max_tokens`, and `extra_body`. The plan itself says the first qwen run was broken due to raw HTTP behavior, so this assumption is already known-false once. If eval and app call paths differ, “A/B validated exact string” is weak evidence.

- The branch `if src == "en" and tgt == "ko"` assumes normalized lower-case ISO codes. `src/ht_lens/llm/openai_compat.py:176-184` does no normalization. If any document carries `"EN"`, `"en-US"`, or mixed-language labels, the new prompt silently never runs.

- The E2E evidence plan is wrong on its face. `src/ht_lens/api/routers/blocks.py:95-99` stores `manual-retranslate:{base_model}:{timestamp}` after `POST /blocks/{id}/retranslate`, not bare `qwen3.6-27b`. A plan that cites impossible evidence for a DoD item is not ready.

- The cache assumption is the biggest unstated bet. `src/ht_lens/translate/pipeline.py:126` and `:166-200` key cache reuse by `text + src + tgt + model`. Rolling back to the same model name means old qwen outputs and new `v2_ko` outputs are indistinguishable. If that is unacceptable, this plan does not solve it.

## 3. Edge cases

- Previously translated qwen documents are not a corner case; they are the default rollback case. `translate_document()` skips `status=="translated"` before any LLM call (`src/ht_lens/translate/pipeline.py:156-160`), so old qwen rows will never pick up `v2_ko` unless manually retranslated or invalidated.

- The manual smoke test can fail for irrelevant reasons. `POST /blocks/{id}/retranslate` only accepts `text` and `header` blocks (`src/ht_lens/api/routers/blocks.py:28,69-73`). The plan says “doc 4에서 5 block” but never defines how those five are selected. Hit one `image` or `table` block and the test degrades into route misuse.

- The restart procedure ignores a roadmap-known defect. `ROADMAP.md:344-345` already records that `ht_lens` ignores SIGTERM and may need SIGKILL. “Use `pgrep -af "ht-lens serve"`” is not enough; a stale process can keep the old config alive or block the new bind.

- Readiness is hand-waved. The plan assumes qwen is ready in ~320s, but app startup health checks are strict. If `.env` flips to `localhost:8081` before the container is actually ready, the rollback will fail at startup and you will not know whether the fault is model quality or rollout sequencing.

## 4. Alternative approaches

- The cleaner approach is to honor Phase 6f’s boundary and perform a pure config rollback first: switch `.env`, start qwen, stop Gemma, run the existing E2E checks. That matches `ROADMAP.md:320-328` and isolates whether `qwen_current 0.867` alone already fixes the user-visible issue.

- If prompt tuning must ship, do not bury it in `OpenAICompatibleClient`. Put prompt selection behind a translate-policy setting or wrapper. That keeps the provider client generic and makes rollback/testing easier.

- If the team insists on same-model rollback plus prompt change, version the prompt in cache identity. High-level options are a prompt-version config or a model alias that feeds `make_cache_key`; otherwise cache reuse will keep serving stale qwen outputs under the new rollout.

## 5. Missing tests

- Add a regression test for actual retranslate provenance, e.g. `tests/integration/test_api_retranslate.py::test_retranslate_response_uses_manual_prefix_for_qwen_model`. The plan’s current DB-model assertion is wrong against `src/ht_lens/api/routers/blocks.py:97`.

- Add a cache-behavior test in `tests/integration/test_translate_pipeline_mock.py`, e.g. `test_translate_document_old_qwen_cache_blocks_v2ko_prompt` or the inverse if invalidation is intended. Right now the most important rollout behavior is unspecified and untested.

- Add an end-to-end scoped-config test that proves repo-root `.env` values drive the real app paths after restart. `tests/unit/test_dotenv_loader.py` proves loading and `tests/unit/test_factory_split.py` proves precedence, but nothing proves `ht-lens translate` and `/threads/{id}/explain` actually use the new 8081 qwen config from `.env`.

- Add a language-code test if the `en -> ko` branch remains, e.g. `tests/unit/test_translate_prompt.py::test_translate_prompt_branch_handles_normalized_lang_codes`. Without that, one casing or locale mismatch turns the feature off silently.
