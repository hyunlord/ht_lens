"""Phase 6e-2 — importing ``ht_lens.cli`` must not mutate LLM env.

Debate §2 (Codex): if ``cli.py`` calls ``load_repo_dotenv()`` at module
level, ``from ht_lens.cli import main`` in tests (e.g.
``tests/integration/test_cli_errors.py:10``) writes into ``os.environ``
**at pytest collection time**, before the ``_isolate_llm_env`` autouse
fixture can snapshot. That leaks the repo .env values across the entire
session.

This regression test runs an isolated subprocess that imports
``ht_lens.cli`` and asserts ``os.environ`` did not gain any LLM-related
key. Subprocess (not in-process) so we measure the actual import-time
side effects rather than fixture-managed state.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def test_importing_ht_lens_cli_does_not_set_llm_env_vars() -> None:
    code = textwrap.dedent(
        """
        import os
        # Clear any inherited LLM keys to make the assertion meaningful.
        PREFIXES = ("LLM_", "TRANSLATE_LLM_", "CHAT_LLM_", "OLLAMA_")
        for k in list(os.environ):
            if k.startswith(PREFIXES):
                del os.environ[k]
        before = {k for k in os.environ if k.startswith(PREFIXES)}

        import ht_lens.cli  # noqa: F401

        after = {k for k in os.environ if k.startswith(PREFIXES)}
        leaked = after - before
        if leaked:
            print(f"LEAK={sorted(leaked)}")
            raise SystemExit(1)
        print("CLEAN")
        """
    ).strip()
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        cwd=str(REPO),
    )
    assert result.returncode == 0, (
        f"ht_lens.cli import leaked env. stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "CLEAN" in result.stdout
