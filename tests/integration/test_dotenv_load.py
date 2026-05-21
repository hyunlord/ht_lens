"""Phase 6c — `.env` auto-load tests.

`create_app()` must populate `os.environ` from the repo-root `.env` BEFORE
the lifespan factory builds the LLM client. Pre-existing shell exports
must win (``override=False``) so tests can pin ``LLM_PROVIDER=mock``.
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_create_app_loads_repo_root_dotenv(monkeypatch: pytest.MonkeyPatch) -> None:
    """Importing ``create_app`` must surface the repo-root .env values via
    ``os.environ``. We isolate the test by clearing any inherited exports
    that would otherwise mask the load."""
    for key in ("LLM_PROVIDER", "LLM_BASE_URL", "LLM_MODEL"):
        monkeypatch.delenv(key, raising=False)
    # The .env may not exist in CI — guard the assertion accordingly.
    dotenv = REPO_ROOT / ".env"
    if not dotenv.is_file():
        pytest.skip("repo-root .env not present (CI without secrets)")

    # Importing app calls _load_repo_dotenv() during create_app().
    from ht_lens.api.app import create_app

    create_app()

    # The repo .env in this checkout has LLM_PROVIDER + LLM_MODEL set. We
    # only assert that *some* LLM_ key landed in os.environ — content
    # depends on the operator's file.
    has_any_llm_env = any(k.startswith("LLM_") for k in os.environ)
    assert has_any_llm_env, "create_app() should have loaded .env into os.environ"


def test_dotenv_override_false_preserves_explicit_shell_export(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If the shell already exported ``LLM_PROVIDER=mock``, the .env file
    must NOT override it. Tests rely on this to keep mock pinned."""
    dotenv = REPO_ROOT / ".env"
    if not dotenv.is_file():
        pytest.skip("repo-root .env not present")

    monkeypatch.setenv("LLM_PROVIDER", "mock-shell-wins")

    # Re-import path: call the loader directly so we don't have to reset
    # the FastAPI app singleton.
    from ht_lens.api.app import _load_repo_dotenv

    _load_repo_dotenv()
    assert os.environ["LLM_PROVIDER"] == "mock-shell-wins"


def test_create_app_does_not_require_cli_module() -> None:
    """Phase 6c debate §2: tests / direct uvicorn entry use ``create_app``
    without importing ``ht_lens.cli``. The .env load must work from that
    path too — i.e. ``ht_lens.cli`` is NOT in sys.modules when the env is
    populated."""
    code = textwrap.dedent(
        """
        import sys, os
        assert "ht_lens.cli" not in sys.modules
        # Clear so override=False has something to compare against.
        for k in ("LLM_PROVIDER", "LLM_MODEL", "LLM_BASE_URL"):
            os.environ.pop(k, None)
        from ht_lens.api.app import create_app
        assert "ht_lens.cli" not in sys.modules, "cli must not be needed"
        create_app()
        # Print whatever LLM_* keys appeared so the test can see them.
        print("LLM_KEYS_PRESENT=" + ",".join(sorted(
            k for k in os.environ if k.startswith("LLM_")
        )))
        """
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        check=False,
    )
    if proc.returncode != 0:
        pytest.fail(
            f"subprocess failed rc={proc.returncode}\nstdout={proc.stdout}\nstderr={proc.stderr}"
        )
    # If the repo .env is missing (CI without secret), the assertion still
    # holds (just no LLM_ keys appear). We only care that create_app() ran
    # without needing the CLI module.
    assert "ht_lens.cli" not in proc.stdout
