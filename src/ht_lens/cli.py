"""Typer entry point for ``ht-lens`` and ``python -m ht_lens.extract``."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import typer

from ht_lens.errors import (
    CorruptedPDFError,
    DocumentAlreadyIngested,
    EncryptedPDFError,
    HtLensError,
    IngestError,
    OutputDirNotEmptyError,
    SchemaVersionMismatch,
)
from ht_lens.extract.pipeline import extract_pdf
from ht_lens.translate.cli import translate_command

app = typer.Typer(no_args_is_help=True, add_completion=False)

_DEFAULT_DB = Path("data/ht_lens.db")


def _db_path_from_env() -> Path:
    url = os.environ.get("HT_LENS_DB_URL", "")
    if url.startswith("sqlite+aiosqlite:///"):
        return Path(url.removeprefix("sqlite+aiosqlite:///"))
    return _DEFAULT_DB


app.command("translate")(translate_command)


@app.callback()
def _root() -> None:
    """ht_lens — PDF layout-preserving translator + chat tool."""


@app.command("extract")
def extract_command(
    pdf: Path = typer.Argument(  # noqa: B008
        ...,
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        resolve_path=True,
        help="Path to source PDF.",
    ),
    out: Path = typer.Option(  # noqa: B008
        ...,
        "-o",
        "--out",
        resolve_path=True,
        help="Output directory.",
    ),
    dpi: int = typer.Option(200, "--dpi", min=72, max=600),
    overwrite: bool = typer.Option(
        False, "--overwrite/--no-overwrite", help="Replace managed files in out dir."
    ),
) -> None:
    """Extract a PDF to page PNGs + block JSONs + doc_meta.json."""
    try:
        result = extract_pdf(pdf, out, dpi=dpi, overwrite=overwrite)
    except (EncryptedPDFError, OutputDirNotEmptyError) as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    except CorruptedPDFError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=3) from exc
    except HtLensError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=exc.exit_code) from exc

    typer.echo(f"ok: pages={result.num_pages} lang={result.lang_guess} out={result.out_dir}")


@app.command("ingest")
def ingest_command(
    extract_dir: Path = typer.Argument(  # noqa: B008
        ...,
        exists=True,
        file_okay=False,
        dir_okay=True,
        readable=True,
        resolve_path=True,
        help="Phase 1 extract directory (contains doc_meta.json and pages/).",
    ),
    src: str | None = typer.Option(
        None, "--src", help="Source language code (e.g. en, ko). Auto-detected if omitted."
    ),
    tgt: str = typer.Option("ko", "--tgt", help="Target language code."),
    overwrite: bool = typer.Option(
        False, "--overwrite/--no-overwrite", help="Replace an already-ingested document."
    ),
    db: Path = typer.Option(  # noqa: B008
        None,
        "--db",
        resolve_path=True,
        help="SQLite DB path. Defaults to HT_LENS_DB_URL env var or data/ht_lens.db.",
    ),
) -> None:
    """Ingest a Phase 1 extract directory into the SQLite database."""
    from ht_lens.db.session import make_engine, make_session_factory

    db_path = db if db is not None else _db_path_from_env()

    async def _run() -> None:
        from ht_lens.ingest.pipeline import ingest_extract_dir

        engine = make_engine(db_path)
        factory = make_session_factory(engine)
        try:
            async with factory() as session:
                stats = await ingest_extract_dir(
                    extract_dir, session, src=src, tgt=tgt, overwrite=overwrite
                )
                await session.commit()
            typer.echo(f"ok: doc_id={stats.document_id} pages={stats.pages} blocks={stats.blocks}")
        finally:
            await engine.dispose()

    try:
        asyncio.run(_run())
    except DocumentAlreadyIngested as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    except SchemaVersionMismatch as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=3) from exc
    except IngestError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    except HtLensError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=exc.exit_code) from exc


def main(argv: list[str] | None = None) -> int:
    try:
        app(argv if argv is not None else sys.argv[1:], standalone_mode=True)
    except SystemExit as exc:
        if isinstance(exc.code, int):
            return exc.code
        if exc.code is None:
            return 0
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
