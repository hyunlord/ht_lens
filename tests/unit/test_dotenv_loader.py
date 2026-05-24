"""Phase 6e-2 — repo-root ``.env`` loader unit tests."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest


def test_load_repo_dotenv_uses_repo_root_not_cwd(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A stray ``.env`` in the CWD must NOT be loaded — only the repo
    root's. Phase 6c debate §3 carried into Phase 6e-2.
    """
    monkeypatch.delenv("PHASE_6E2_DECOY", raising=False)
    decoy = tmp_path / ".env"
    decoy.write_text("PHASE_6E2_DECOY=stray-cwd-value\n")
    monkeypatch.chdir(tmp_path)

    from ht_lens.dotenv_loader import load_repo_dotenv

    load_repo_dotenv()
    assert os.environ.get("PHASE_6E2_DECOY") is None, "loader must not pick up CWD-local .env files"


def test_load_repo_dotenv_skips_load_dotenv_when_file_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Genuine missing-file branch lock — verify-cross R2 §4 #1.

    The previous test (``_noop_when_file_missing``) only checked that
    the call does not raise, but ``python-dotenv.load_dotenv()`` on a
    missing path is silent: if the ``if dotenv.is_file():`` branch
    were removed and ``load_dotenv()`` called unconditionally, the test
    would still pass.

    Here we mock ``load_dotenv`` itself and assert it is **never
    invoked** when the file is missing. This is the true branch lock.
    """
    import ht_lens.dotenv_loader as loader_mod

    assert not (tmp_path / ".env").exists(), "fresh tmp_path must have no .env"
    monkeypatch.setattr(loader_mod, "_REPO_ROOT", tmp_path)

    mock_load = MagicMock(return_value=False)
    monkeypatch.setattr(loader_mod, "load_dotenv", mock_load)

    loader_mod.load_repo_dotenv()

    assert mock_load.call_count == 0, (
        f"load_dotenv must NOT be called when .env is missing; "
        f"was called {mock_load.call_count} times"
    )


def test_load_repo_dotenv_calls_load_dotenv_when_file_exists(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Complement to the missing-file branch lock — verify-cross R2 §4 #1.

    When ``.env`` exists in ``_REPO_ROOT``, ``load_dotenv`` MUST be
    invoked exactly once with the correct path and ``override=False``.
    Together with the missing-file test, both branches of ``if
    dotenv.is_file()`` are genuinely locked.
    """
    import ht_lens.dotenv_loader as loader_mod

    env_file = tmp_path / ".env"
    env_file.write_text("TEST_KEY=test_value\n")
    monkeypatch.setattr(loader_mod, "_REPO_ROOT", tmp_path)

    mock_load = MagicMock(return_value=True)
    monkeypatch.setattr(loader_mod, "load_dotenv", mock_load)

    loader_mod.load_repo_dotenv()

    assert mock_load.call_count == 1, (
        f"load_dotenv must be called exactly once when .env exists; "
        f"was called {mock_load.call_count} times"
    )
    _args, kwargs = mock_load.call_args
    # The loader passes dotenv_path as a kwarg.
    assert Path(kwargs["dotenv_path"]) == env_file, (
        f"expected dotenv_path={env_file}, got {kwargs.get('dotenv_path')}"
    )
    assert kwargs.get("override") is False, (
        f"override must be False to preserve shell exports; got {kwargs.get('override')!r}"
    )


def test_load_repo_dotenv_override_false_preserves_shell_export(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``load_repo_dotenv()`` uses ``override=False`` so shell exports
    win — required for tests that pin ``LLM_PROVIDER=mock``."""
    monkeypatch.setenv("LLM_PROVIDER", "shell-export-wins")

    from ht_lens.dotenv_loader import load_repo_dotenv

    load_repo_dotenv()
    assert os.environ["LLM_PROVIDER"] == "shell-export-wins"
