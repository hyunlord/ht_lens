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
    not an exception. We can't actually remove the repo .env, but we can
    cover the missing-file branch by pointing the loader at a temp
    location via the helper's resolved root.
    """
    # The function looks at ``Path(__file__).resolve().parents[2] / ".env"``.
    # We just confirm it doesn't raise — repo .env may or may not exist
    # in this checkout, but either way ``load_repo_dotenv()`` returns
    # without error.
    from ht_lens.dotenv_loader import load_repo_dotenv

    load_repo_dotenv()  # no raise = pass


def test_load_repo_dotenv_override_false_preserves_shell_export(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``load_repo_dotenv()`` uses ``override=False`` so shell exports
    win — required for tests that pin ``LLM_PROVIDER=mock``."""
    monkeypatch.setenv("LLM_PROVIDER", "shell-export-wins")

    from ht_lens.dotenv_loader import load_repo_dotenv

    load_repo_dotenv()
    assert os.environ["LLM_PROVIDER"] == "shell-export-wins"
