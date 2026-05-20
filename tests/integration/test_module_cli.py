"""Subprocess-level tests for ``python -m ht_lens.extract``.

This is the user-facing module CLI named in ROADMAP Phase 1, separate from
the in-process `main()` call exercised elsewhere. We invoke a real subprocess
so the entry-point script in ``src/ht_lens/extract/__main__.py`` is actually
covered.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
REPO = Path(__file__).resolve().parents[2]


def test_python_m_ht_lens_extract_succeeds_on_sample_en(tmp_path: Path) -> None:
    out = tmp_path / "out"
    proc = subprocess.run(
        [sys.executable, "-m", "ht_lens.extract", str(FIXTURES / "sample_en.pdf"), "-o", str(out)],
        capture_output=True,
        text=True,
        cwd=str(REPO),
    )
    assert proc.returncode == 0, (proc.stdout, proc.stderr)
    assert "ok: pages=" in proc.stdout
    meta = json.loads((out / "doc_meta.json").read_text())
    assert meta["lang_guess"] == "en"
    assert meta["num_pages"] == 8


def test_python_m_ht_lens_extract_returns_2_on_existing_dir(tmp_path: Path) -> None:
    out = tmp_path / "out"
    out.mkdir()
    (out / "stash.txt").write_text("hi")
    proc = subprocess.run(
        [sys.executable, "-m", "ht_lens.extract", str(FIXTURES / "sample_en.pdf"), "-o", str(out)],
        capture_output=True,
        text=True,
        cwd=str(REPO),
    )
    assert proc.returncode == 2, (proc.stdout, proc.stderr)
    assert "output directory not empty" in proc.stderr
    # External file must survive.
    assert (out / "stash.txt").read_text() == "hi"


def test_ht_lens_console_script_extract(tmp_path: Path) -> None:
    """The installed ``ht-lens`` console script declared in pyproject.toml."""
    script = REPO / ".venv" / "bin" / "ht-lens"
    if not script.exists():
        # uv venv may use a different layout — skip explicitly.
        import pytest

        pytest.skip(f"ht-lens entry script not found at {script}")
    out = tmp_path / "out"
    proc = subprocess.run(
        [str(script), "extract", str(FIXTURES / "sample_en.pdf"), "-o", str(out)],
        capture_output=True,
        text=True,
        cwd=str(REPO),
    )
    assert proc.returncode == 0, (proc.stdout, proc.stderr)
    assert "ok: pages=8 lang=en" in proc.stdout
    assert (out / "doc_meta.json").exists()
