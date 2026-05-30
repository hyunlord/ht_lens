"""Phase 8a — CLI contract for ``ingest-mineru`` (verify-cross R1).

Drives the real Typer entrypoint (``main``) against an alembic-migrated DB
so the command wiring, exit codes, and already-ingested path are locked.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from ht_lens.cli import main

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "mineru" / "content_list_sample.json"
_IMAGES = ["eq1.jpg", "fig1.jpg", "chart1.jpg", "fig2.jpg"]


def _mineru_dir(tmp_path: Path) -> Path:
    auto = tmp_path / "doc" / "auto"
    (auto / "images").mkdir(parents=True)
    shutil.copy2(FIXTURE, auto / "doc_content_list.json")
    for name in _IMAGES:
        (auto / "images" / name).write_bytes(b"\x89PNG\r\n\x1a\n")
    return auto / "doc_content_list.json"


def test_ingest_mineru_cli_happy(tmp_path: Path, api_db_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    # Managed images land under CWD/data/extracts_v2; run inside tmp to stay hermetic.
    monkeypatch.chdir(tmp_path)
    cl = _mineru_dir(tmp_path)
    rc = main(
        [
            "ingest-mineru",
            str(cl),
            "--filename",
            "book2_ch.pdf",
            "--db",
            str(api_db_path),
        ]
    )
    assert rc == 0
    # The chunks landed in the DB.
    import sqlite3

    con = sqlite3.connect(api_db_path)
    try:
        n = con.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        extractor = con.execute("SELECT extractor FROM documents LIMIT 1").fetchone()[0]
    finally:
        con.close()
    assert n == 10
    assert extractor == "mineru"


def test_ingest_mineru_cli_already_ingested_exits_2(
    tmp_path: Path, api_db_path: Path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.chdir(tmp_path)
    cl = _mineru_dir(tmp_path)
    args = ["ingest-mineru", str(cl), "--filename", "dup.pdf", "--db", str(api_db_path)]
    assert main(args) == 0
    # Second ingest of the same filename without --overwrite → exit 2.
    assert main(args) == 2
    # With --overwrite → exit 0 again.
    assert main([*args, "--overwrite"]) == 0


def test_ingest_mineru_cli_accepts_output_dir(
    tmp_path: Path, api_db_path: Path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    """Passing the MinerU output dir (not the json) is auto-discovered."""
    monkeypatch.chdir(tmp_path)
    _mineru_dir(tmp_path)
    out_dir = tmp_path / "doc"
    rc = main(["ingest-mineru", str(out_dir), "--filename", "viadir.pdf", "--db", str(api_db_path)])
    assert rc == 0


# --- extract-mineru CLI (Phase 8a residual closed in 8b, verify-cross R2) ---


def test_extract_mineru_cli_missing_binary_exits_nonzero(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """extract-mineru maps MineruError (missing binary) to a nonzero exit."""
    pdf = tmp_path / "in.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    monkeypatch.setenv("HT_LENS_MINERU_BIN", "/nonexistent/mineru-xyz")
    rc = main(["extract-mineru", str(pdf), "-o", str(tmp_path / "out")])
    assert rc == 4  # MineruError.exit_code


def test_extract_mineru_cli_happy_with_fake_binary(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """A fake MinerU binary produces a content_list; CLI exits 0."""
    import stat

    pdf = tmp_path / "in.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    out = tmp_path / "out"
    fake = tmp_path / "mineru"
    fake.write_text(
        f'#!/bin/sh\nmkdir -p "{out}/in/auto"\nprintf "[]" > "{out}/in/auto/in_content_list.json"\n'
    )
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC | stat.S_IRUSR)
    monkeypatch.setenv("HT_LENS_MINERU_BIN", str(fake))
    rc = main(["extract-mineru", str(pdf), "-o", str(out)])
    assert rc == 0
