"""Phase 6e-2 — repo-root ``.env`` loader unit tests."""

from __future__ import annotations

import os
from pathlib import Path

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


def test_load_repo_dotenv_noop_when_file_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Missing repo-root .env is a no-op (common on fresh checkouts/CI),
    not an exception. Verify-cross R1 (Codex §4): genuinely exercise
    the missing-file branch by pointing ``_REPO_ROOT`` at a tmp dir
    that contains no ``.env`` file.
    """
    import ht_lens.dotenv_loader as loader_mod

    monkeypatch.delenv("PHASE_6E2_NOENV_PROBE", raising=False)
    # tmp_path is fresh from pytest — guaranteed no .env.
    assert not (tmp_path / ".env").exists()
    monkeypatch.setattr(loader_mod, "_REPO_ROOT", tmp_path)

    # Call. The branch ``if dotenv.is_file()`` must short-circuit;
    # otherwise we would somehow load a file that does not exist.
    loader_mod.load_repo_dotenv()  # no raise = branch taken

    # A non-existent file cannot have added env vars. Confirm by
    # checking a sentinel key did not appear (would be set if
    # load_dotenv() had been called on a stray file).
    assert os.environ.get("PHASE_6E2_NOENV_PROBE") is None


def test_load_repo_dotenv_override_false_preserves_shell_export(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``load_repo_dotenv()`` uses ``override=False`` so shell exports
    win — required for tests that pin ``LLM_PROVIDER=mock``."""
    monkeypatch.setenv("LLM_PROVIDER", "shell-export-wins")

    from ht_lens.dotenv_loader import load_repo_dotenv

    load_repo_dotenv()
    assert os.environ["LLM_PROVIDER"] == "shell-export-wins"
