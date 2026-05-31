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


# --- translate-chunks CLI error mapping (verify-cross R1 §4) ---


def test_translate_chunks_cli_unknown_doc_exits_2(
    tmp_path: Path, api_db_path: Path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    """Unknown doc_id → ValueError → clean exit 2 (not a traceback)."""
    monkeypatch.setenv("TRANSLATE_LLM_PROVIDER", "mock")
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    rc = main(["translate-chunks", "--doc-id", "99999", "--db", str(api_db_path)])
    assert rc == 2


def _ingest_doc(tmp_path: Path, db: Path, monkeypatch) -> int:  # type: ignore[no-untyped-def]
    """Ingest the fixture as a 2.0 doc; return doc_id (always 1 in a fresh DB)."""
    monkeypatch.chdir(tmp_path)
    cl = _mineru_dir(tmp_path)
    assert main(["ingest-mineru", str(cl), "--filename", "x.pdf", "--db", str(db)]) == 0
    import sqlite3

    con = sqlite3.connect(db)
    try:
        return int(con.execute("SELECT id FROM documents LIMIT 1").fetchone()[0])
    finally:
        con.close()


def test_translate_chunks_cli_failure_exits_1(
    tmp_path: Path, api_db_path: Path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    """verify-cross R2 (real defect): when chunks fail translation the CLI
    must exit non-zero so 8e batch detects it (was exit 0)."""
    doc_id = _ingest_doc(tmp_path, api_db_path, monkeypatch)
    monkeypatch.setenv("TRANSLATE_LLM_PROVIDER", "mock_fail")
    monkeypatch.setenv("LLM_PROVIDER", "mock_fail")
    rc = main(["translate-chunks", "--doc-id", str(doc_id), "--db", str(api_db_path)])
    assert rc == 1  # FailMock → all text chunks failed → exit 1


def test_translate_chunks_cli_health_check_failure_exits_4(
    tmp_path: Path, api_db_path: Path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    """health_check() is now called (fail-fast); a failing endpoint → exit 4."""
    doc_id = _ingest_doc(tmp_path, api_db_path, monkeypatch)
    monkeypatch.setenv("TRANSLATE_LLM_PROVIDER", "mock")
    monkeypatch.setenv("LLM_PROVIDER", "mock")

    from ht_lens.llm.errors import LLMHealthCheckFailed
    from ht_lens.llm.mock import MockLLMClient

    async def _boom(self) -> bool:  # type: ignore[no-untyped-def]
        raise LLMHealthCheckFailed("endpoint down")

    monkeypatch.setattr(MockLLMClient, "health_check", _boom)
    rc = main(["translate-chunks", "--doc-id", str(doc_id), "--db", str(api_db_path)])
    assert rc == 4


def test_extract_mineru_cli_supports_timeout_option(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Phase 8e-2 R6 / debate §5.1: extract-mineru exposes --timeout and threads
    it to run_mineru(timeout_s=...), so a 500+ page CPU extraction is not capped
    at the 3600s default. Mocks run_mineru to capture the kwarg (no real MinerU)."""
    import ht_lens.extract_mineru.runner as runner_mod
    from ht_lens.extract_mineru.runner import MineruResult

    captured: dict[str, object] = {}

    def _fake_run(pdf, out_dir, *, lang="en", backend="pipeline", cpu=True, timeout_s=3600):  # type: ignore[no-untyped-def]
        captured["timeout_s"] = timeout_s
        captured["backend"] = backend
        cl = Path(out_dir) / "x_content_list.json"
        cl.parent.mkdir(parents=True, exist_ok=True)
        cl.write_text("[]")
        return MineruResult(
            content_list_path=cl, images_dir=None, markdown_path=None, out_dir=Path(out_dir)
        )

    monkeypatch.setattr(runner_mod, "run_mineru", _fake_run)
    pdf = tmp_path / "big.pdf"
    pdf.write_bytes(b"%PDF-1.7\n%%EOF\n")
    rc = main(["extract-mineru", str(pdf), "--out", str(tmp_path / "out"), "--timeout", "9000"])
    assert rc == 0
    assert captured["timeout_s"] == 9000
