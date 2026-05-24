"""Repo-root ``.env`` loader — Phase 6e-2.

Shared by ``api/app.py`` (called during ``create_app()``) and
``translate/cli.py`` (called inside ``translate_command()``). Both entry
points need ``os.environ`` populated before any LLM client is built.

Design notes (carried from Phase 6c debate §3):

- We look only at the repo root, not CWD. A stray ``.env`` in the user's
  current document folder must not be able to switch the LLM provider
  out from under them.
- ``override=False`` keeps explicit shell exports authoritative so test
  suites can pin ``LLM_PROVIDER=mock`` without the file overriding them.
- Callers invoke at the LLM-construction site, not at module import,
  so importing ``ht_lens.cli`` (e.g. ``from ht_lens.cli import main`` in
  ``tests/integration/test_cli_errors.py``) does not mutate
  ``os.environ`` at pytest collection time — that was the regression
  trap Phase 6e-2 debate (Codex §2) flagged.
"""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

# This file lives at ``src/ht_lens/dotenv_loader.py``. Repo root is two
# parents up. (``api/app.py`` was three because of the extra ``api``
# directory — we compute fresh here.)
_REPO_ROOT = Path(__file__).resolve().parents[2]


def load_repo_dotenv() -> None:
    """Load the repo-root ``.env`` into ``os.environ`` if it exists.

    No-op if the file is missing (common on fresh checkouts and in CI).
    Always uses ``override=False`` so pre-existing shell exports win.
    """
    dotenv = _REPO_ROOT / ".env"
    if dotenv.is_file():
        load_dotenv(dotenv_path=dotenv, override=False)
