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
