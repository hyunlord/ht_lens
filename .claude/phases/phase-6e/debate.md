## 1. Over-engineering

- `.claude/phases/phase-6e/plan.md` already narrows `ROADMAP.md` Phase 6e to one bullet, "모델 빠른 토글", but still proposes a broad refactor across `src/ht_lens/llm/*`, `src/ht_lens/api/*`, tests, `.env.example`, and new docs. That is too much transitional plumbing for a phase that still does not implement the actual user-facing DoD, especially "viewer 재시작 불필요 정도".

- The dual `TranslateLLMClient` / `ChatLLMClient` Protocols, legacy `LLMClient` alias, `from_env()` deprecation, and `app.state.llm` compatibility alias are all migration scaffolding. Defer the alias/warning layer until there is a second concrete client or real toggle UI/API. Right now it adds surface area without proving the roadmap deliverable.

- Rewriting `tests/conftest.py::_isolate_llm_env` as a 20+ key allowlist is complexity for its own sake. The current prefix-snapshot approach already fixed the Phase 6c leak for `LLM_*` and `OLLAMA_*`; a hardcoded list will drift again the next time a new env var is added.

## 2. Hidden assumptions

- The plan assumes API dependency injection is the only runtime consumer of the singleton LLM. False. `src/ht_lens/jobs/pipeline.py::process_upload_job` reads `app.state.llm` and uses it for both `translate_document()` and `summarize_document()`. That file is absent from "File-level changes", so the split is incomplete. With `LLMClient = TranslateLLMClient`, that omission is also a mypy problem, not just a routing bug.

- The plan assumes `tests/integration/_api_helpers.py` only needs env pinning. Wrong. `make_test_client()` currently overrides only `get_llm_client`, and `tests/integration/test_api_messages.py`, `test_api_retranslate.py`, and `test_api_summarize.py` all depend on that path. Once routes switch to `get_chat_llm_client` / `get_translate_llm_client`, those tests stop overriding the intended client unless the helper API changes too.

- `_resolve(scoped > legacy > default)` assumes empty strings are valid scoped values. `TRANSLATE_LLM_MODEL=""` or `CHAT_LLM_BASE_URL=""` will override working `LLM_*` values and fail later with a broken client. Current `from_env()` fails fast on missing required env; this plan adds a quieter, worse failure mode.

- The "DoD mapping" in `.claude/phases/phase-6e/plan.md` is not a mapping to `ROADMAP.md` Phase 6e. It maps internal refactor steps, not the actual DoD items "모델 env 1줄 변경으로 swap, viewer 재시작 불필요 정도" and "README 일주일 실사용 캡처".

## 3. Edge cases

- One provider healthy, the other unhealthy. `src/ht_lens/api/app.py::_lifespan` will fail startup if either `translate_llm.health_check()` or `chat_llm.health_check()` fails. The plan never states whether a chat-only outage should also take down `/documents`, `/pages`, and manual retranslate.

- Mixed scoped and legacy envs. Example: `TRANSLATE_LLM_PROVIDER=mock`, `CHAT_LLM_PROVIDER=openai_compat`, only `LLM_BASE_URL` and `LLM_MODEL` set. The precedence rules need to be explicit for every key, or you will get half-configured clients with different fallback behavior.

- Direct `OpenAICompatibleClient(...)` call sites exist in `tests/conftest.py::live_llm_client`, `tests/integration/test_health_check_live.py`, and `tests/integration/test_translate_pipeline_live.py`. Changing constructor defaults to `temperature=0.0` changes those paths too, even when no split factory is involved.

- Failure injection is asymmetric. `src/ht_lens/llm/mock.py::FailMockLLMClient` only breaks `translate()`. After the split, there is no built-in mock for chat-only failures, summarize failures, or chat health-check failures.

## 4. Alternative approaches

- Keep `src/ht_lens/llm/client.py::LLMClient` unchanged and split only configuration, not protocols. A small `LLMConfig` or `from_env(prefix="TRANSLATE" | "CHAT")` layer lets `src/ht_lens/api/app.py` build two `OpenAICompatibleClient` instances without touching most type annotations, dependency helpers, or test overrides.

- If the real target is the roadmap DoD "viewer 재시작 불필요", environment splitting is the wrong boundary. A runtime settings store or model registry exposed through the viewer/API is a better fit, because env changes still require process restart in both `src/ht_lens/api/app.py` and `src/ht_lens/translate/cli.py`.

## 5. Missing tests

- `tests/integration/test_jobs_pipeline.py::test_process_upload_job_routes_summary_to_chat_llm` should exist. It will catch the currently unplanned `app.state.llm` usage in `src/ht_lens/jobs/pipeline.py`.

- `tests/integration/test_api_messages.py::test_llm_override_reaches_chat_dependency` and `tests/integration/test_api_retranslate.py::test_llm_override_reaches_translate_dependency` should exist. Otherwise `tests/integration/_api_helpers.py::make_test_client` can silently stop overriding the intended client.

- `tests/integration/test_api_startup.py::test_startup_fails_when_chat_llm_health_check_fails` and the converse case for translate should exist. Startup semantics materially change from the current single-client model.

- `tests/unit/test_factory_split.py::test_scoped_empty_string_falls_back_to_legacy` should exist if `_resolve()` stays. The current test list only covers happy-path precedence.

- `tests/integration/test_translate_cli.py::test_translate_cli_prefers_translate_scoped_env_over_legacy` is missing. Current CLI coverage only exercises `LLM_*`, not `TRANSLATE_LLM_*`.

- `tests/integration/test_api_summarize.py::test_summarize_uses_chat_scoped_env` is missing. Without it, the plan proves factory construction, not that summarization actually routes to the chat profile.
