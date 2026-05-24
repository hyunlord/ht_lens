## 1. Over-engineering

- The `_bootstrap.py` extraction plus module-level side effect in `src/ht_lens/cli.py` is broader than the bug. The failure happens where `src/ht_lens/translate/cli.py:50-56` constructs the LLM, but this plan would make `extract`, `ingest`, `serve --help`, and any plain `ht_lens.cli` import load `.env` too. That is a cross-cutting startup mutation to fix one translate path.

- The “status analysis” item is scope creep. You already classify `_finalize_document_status()` in `src/ht_lens/translate/pipeline.py:284-296` as scope-out, yet the plan still spends scope and review budget on analyzing it. Remove it from this phase or make it a separate follow-up; otherwise this P0 fix stops being a single-purpose repair.

- The proposed new unit files duplicate the wrong coverage. `tests/integration/test_dotenv_load.py` already covers API-side dotenv loading. The missing evidence is not another import-level loader test; it is a real subprocess translation regression on the broken launcher.

## 2. Hidden assumptions

- The plan assumes `ht-lens translate` is the only affected entry point. That is false. The existing CLI regression suite executes `python -m ht_lens.translate` in `tests/integration/test_translate_cli.py:23-29`, which goes through `src/ht_lens/translate/__main__.py:3-5` and `src/ht_lens/translate/cli.py`, completely bypassing `src/ht_lens/cli.py`.

- It assumes `_isolate_llm_env` in `tests/conftest.py:24-49` makes module-level dotenv loading safe. It does not. `tests/integration/test_cli_errors.py:10` imports `ht_lens.cli` at module import time, before fixtures run, so a module-level `load_repo_dotenv()` would mutate `os.environ` during collection and defeat the isolation strategy.

- It assumes auto-loading `.env` is enough to satisfy the plan’s own “Silent mock 방지” DoD. It is not. `from_env_translate()` still defaults to `"mock"` in `src/ht_lens/llm/factory.py:136-158`. Missing `.env`, incomplete `.env`, bad repo-root detection, or installed-package execution outside a repo checkout will still silently select mock.

- It assumes `override=False` preserves explicit mock pins. That only holds for the same key. Because `from_env_translate()` prefers `TRANSLATE_LLM_*` over `LLM_*`, a repo `.env` with scoped vars can still beat a shell or test that only exports `LLM_PROVIDER=mock`.

## 3. Edge cases

- `python -m ht_lens.translate --doc-id ...` remains broken unless `src/ht_lens/translate/cli.py` or `src/ht_lens/translate/__main__.py` is changed. Your current subprocess suite hits that path, not `ht_lens.cli`.

- `python -m ht_lens.extract` and direct `from ht_lens.cli import main` imports will now load `.env` even though they never build an LLM. That is unnecessary startup mutation on non-LLM code paths and a credible source of test flakiness.

- A checkout without `.env` is common in CI and on fresh machines. The plan’s smoke command uses `--dry-run`, but `src/ht_lens/translate/cli.py:57-61` skips `health_check()` in dry-run mode, so that smoke cannot prove the provider is real. The original bug can survive while the smoke still passes.

- Empty or partial shell exports are not addressed. If a wrapper exports `LLM_PROVIDER=` or only part of the required `LLM_*` set, `load_dotenv(..., override=False)` may not refill it, and `_resolve()` will fall back to mock anyway.

## 4. Alternative approaches

- The minimal fix is to call the shared loader only at the actual LLM-construction sites: keep `src/ht_lens/api/app.py:150-154` as-is and add the same call inside `src/ht_lens/translate/cli.py` before line 55. That fixes API and standalone translate without polluting `extract`, `ingest`, or help paths.

- The stronger P0 fix is fail-closed behavior in `translate_command()`: if resolution lands on `MockLLMClient` and the user did not explicitly request mock, exit with an error instead of translating. That addresses the dangerous default in `src/ht_lens/llm/factory.py:138` instead of assuming `.env` is always present and correct.

- If a shared module is still needed, `_bootstrap.py` is the wrong name. Use something explicit like `env.py` or `dotenv_loader.py`; `_bootstrap` becomes a junk drawer immediately.

## 5. Missing tests

- Add `tests/integration/test_translate_cli.py::test_module_entrypoint_loads_repo_root_dotenv_without_env_exports`. Run `python -m ht_lens.translate` with `LLM_*` and `TRANSLATE_LLM_*` cleared and a repo-root `.env` pointing to an unreachable `openai_compat` endpoint; expected result is exit `4`, not mock success.

- Add the same assertion for the installed subcommand path, e.g. `test_ht_lens_translate_subcommand_loads_repo_root_dotenv_without_env_exports`. The plan currently proves neither launcher.

- Add a regression test that importing `ht_lens.cli` does not mutate LLM env during collection-time use. Without that, the proposed module-level load can reintroduce exactly the cross-test leakage `tests/conftest.py:24-49` was added to prevent.

- Add a scoped-vs-legacy precedence test under dotenv load: repo `.env` provides `TRANSLATE_LLM_PROVIDER=openai_compat`, shell exports only `LLM_PROVIDER=mock`. Decide the intended behavior and lock it. The current plan incorrectly treats this as covered by `override=False`.
