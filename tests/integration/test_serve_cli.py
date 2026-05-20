"""Phase 3 — ``ht-lens serve`` CLI registration smoke test.

We do NOT actually start uvicorn here; we only verify that the subcommand is
registered and `--help` lists the expected options.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def test_serve_help_lists_expected_options() -> None:
    proc = subprocess.run(
        [sys.executable, "-m", "ht_lens.cli", "serve", "--help"],
        capture_output=True,
        text=True,
        cwd=str(REPO),
        check=False,
    )
    assert proc.returncode == 0, (proc.stdout, proc.stderr)
    out = proc.stdout
    for opt in ["--host", "--port", "--reload", "--db", "--skip-llm-check"]:
        assert opt in out, f"missing {opt} in serve --help output"
