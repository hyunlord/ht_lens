"""Phase 3 — ``ht-lens serve`` CLI registration smoke test.

We do NOT actually start uvicorn here; we only verify that the subcommand is
registered and `--help` lists the expected options.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

# typer/Rich emits ANSI color sequences when FORCE_COLOR is set (GitHub
# Actions runners do this). Those sequences are inserted between characters
# of option names like ``--host`` (rendered as ``\x1b[..m-\x1b[0m\x1b[..m-host\x1b[0m``),
# which breaks naive ``"--host" in stdout`` checks. Strip them before checking.
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


def test_serve_help_lists_expected_options() -> None:
    env = {k: v for k, v in os.environ.items() if k not in {"FORCE_COLOR"}}
    env["NO_COLOR"] = "1"
    proc = subprocess.run(
        [sys.executable, "-m", "ht_lens.cli", "serve", "--help"],
        capture_output=True,
        text=True,
        cwd=str(REPO),
        env=env,
        check=False,
    )
    assert proc.returncode == 0, (proc.stdout, proc.stderr)
    out = _strip_ansi(proc.stdout)
    for opt in ["--host", "--port", "--reload", "--db", "--skip-llm-check"]:
        assert opt in out, f"missing {opt} in serve --help output: {out!r}"
