"""Subprocess-level tests for the ingest CLI.

Covers ``python -m ht_lens.ingest <dir>`` and the ``ht-lens ingest`` console script
so the __main__.py entry point and the Typer wiring are exercised end-to-end.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
REPO = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# Fixture extract dir helpers (no pytest fixtures needed — purely functional)
# ---------------------------------------------------------------------------


def _make_extract_dir(
    tmp_path: Path,
    *,
    filename: str = "cli_test.pdf",
    num_pages: int = 1,
    lang_guess: str = "en",
    blocks_per_page: int = 1,
) -> Path:
    d = tmp_path / "extract"
    d.mkdir(parents=True, exist_ok=True)
    pages_dir = d / "pages"
    pages_dir.mkdir(exist_ok=True)

    meta = {
        "filename": filename,
        "num_pages": num_pages,
        "lang_guess": lang_guess,
        "src_pdf_sha256": "b" * 64,
        "extracted_at": "2025-01-01T00:00:00+00:00",
        "extractor_version": "1.0.0",
    }
    (d / "doc_meta.json").write_text(json.dumps(meta))

    for i in range(1, num_pages + 1):
        page = {
            "page_num": i,
            "width": 595.0,
            "height": 842.0,
            "rotation": 0,
            "render": {"dpi": 200, "pixel_width": 1654, "pixel_height": 2339, "scale": 2.778},
            "unit": "pt",
            "blocks": [
                {
                    "id": f"p{i}_b{j:03d}",
                    "type": "text",
                    "bbox": [10.0, 10.0, 200.0, 30.0],
                    "order": j - 1,
                    "text": f"page {i} block {j}",
                }
                for j in range(1, blocks_per_page + 1)
            ],
        }
        (pages_dir / f"page_{i:04d}.json").write_text(json.dumps(page))
        (pages_dir / f"page_{i:04d}.png").write_bytes(b"\x89PNG\r\n\x1a\n")

    return d


def _alembic_upgrade(db_path: Path) -> None:
    import os

    env = {**os.environ, "HT_LENS_DB_URL": f"sqlite+aiosqlite:///{db_path}"}
    proc = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        capture_output=True,
        text=True,
        cwd=str(REPO),
        env=env,
    )
    assert proc.returncode == 0, proc.stderr


# ---------------------------------------------------------------------------
# python -m ht_lens.ingest tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "sample_name,lang,num_pages",
    [
        ("sample_en.pdf", "en", 8),
        ("sample_ko.pdf", "ko", 52),
        ("sample_mixed.pdf", "mixed", 6),
    ],
)
def test_python_m_ingest_on_extracted_fixture(
    sample_name: str,
    lang: str,
    num_pages: int,
    tmp_path: Path,
) -> None:
    """Full round-trip: extract a PDF, then ingest the output via subprocess."""
    extract_out = tmp_path / "extract"
    db_path = tmp_path / "test.db"

    # Phase 1: extract
    proc_extract = subprocess.run(
        [
            sys.executable,
            "-m",
            "ht_lens.extract",
            str(FIXTURES / sample_name),
            "-o",
            str(extract_out),
        ],
        capture_output=True,
        text=True,
        cwd=str(REPO),
    )
    assert proc_extract.returncode == 0, proc_extract.stderr

    # Alembic migration
    _alembic_upgrade(db_path)

    # Phase 2a: ingest (mixed lang needs explicit --src)
    src_args = ["--src", "en"] if lang == "mixed" else []
    import os

    env = {**os.environ, "HT_LENS_DB_URL": f"sqlite+aiosqlite:///{db_path}"}
    proc_ingest = subprocess.run(
        [sys.executable, "-m", "ht_lens.ingest", str(extract_out), "--db", str(db_path), *src_args],
        capture_output=True,
        text=True,
        cwd=str(REPO),
        env=env,
    )
    assert proc_ingest.returncode == 0, (proc_ingest.stdout, proc_ingest.stderr)
    assert "ok: doc_id=" in proc_ingest.stdout
    assert f"pages={num_pages}" in proc_ingest.stdout


def test_python_m_ingest_duplicate_returns_exit_2(tmp_path: Path) -> None:
    extract_dir = _make_extract_dir(tmp_path)
    db_path = tmp_path / "dup.db"
    _alembic_upgrade(db_path)

    import os

    env = {**os.environ, "HT_LENS_DB_URL": f"sqlite+aiosqlite:///{db_path}"}
    args = [sys.executable, "-m", "ht_lens.ingest", str(extract_dir), "--db", str(db_path)]

    proc1 = subprocess.run(args, capture_output=True, text=True, cwd=str(REPO), env=env)
    assert proc1.returncode == 0, proc1.stderr

    proc2 = subprocess.run(args, capture_output=True, text=True, cwd=str(REPO), env=env)
    assert proc2.returncode == 2
    assert "already ingested" in proc2.stderr


def test_python_m_ingest_overwrite_flag_succeeds(tmp_path: Path) -> None:
    extract_dir = _make_extract_dir(tmp_path)
    db_path = tmp_path / "over.db"
    _alembic_upgrade(db_path)

    import os

    env = {**os.environ, "HT_LENS_DB_URL": f"sqlite+aiosqlite:///{db_path}"}
    base_args = [sys.executable, "-m", "ht_lens.ingest", str(extract_dir), "--db", str(db_path)]

    proc1 = subprocess.run(base_args, capture_output=True, text=True, cwd=str(REPO), env=env)
    assert proc1.returncode == 0, proc1.stderr

    proc2 = subprocess.run(
        [*base_args, "--overwrite"], capture_output=True, text=True, cwd=str(REPO), env=env
    )
    assert proc2.returncode == 0, proc2.stderr
    assert "ok: doc_id=" in proc2.stdout


def test_python_m_ingest_missing_extract_dir_returns_nonzero(tmp_path: Path) -> None:
    db_path = tmp_path / "err.db"
    _alembic_upgrade(db_path)
    missing = tmp_path / "no_such_dir"

    import os

    env = {**os.environ, "HT_LENS_DB_URL": f"sqlite+aiosqlite:///{db_path}"}
    proc = subprocess.run(
        [sys.executable, "-m", "ht_lens.ingest", str(missing), "--db", str(db_path)],
        capture_output=True,
        text=True,
        cwd=str(REPO),
        env=env,
    )
    assert proc.returncode != 0


def test_ht_lens_console_script_ingest(tmp_path: Path) -> None:
    """The installed ``ht-lens ingest`` console script."""
    script = REPO / ".venv" / "bin" / "ht-lens"
    if not script.exists():
        pytest.skip(f"ht-lens entry script not found at {script}")

    extract_dir = _make_extract_dir(tmp_path)
    db_path = tmp_path / "script.db"
    _alembic_upgrade(db_path)

    import os

    env = {**os.environ, "HT_LENS_DB_URL": f"sqlite+aiosqlite:///{db_path}"}
    proc = subprocess.run(
        [str(script), "ingest", str(extract_dir), "--db", str(db_path)],
        capture_output=True,
        text=True,
        cwd=str(REPO),
        env=env,
    )
    assert proc.returncode == 0, (proc.stdout, proc.stderr)
    assert "ok: doc_id=" in proc.stdout
