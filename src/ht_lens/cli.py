"""Typer entry point for ``ht-lens`` and ``python -m ht_lens.extract``."""

from __future__ import annotations

import sys
from pathlib import Path

import typer

from ht_lens.errors import (
    CorruptedPDFError,
    EncryptedPDFError,
    HtLensError,
    OutputDirNotEmptyError,
)
from ht_lens.extract.pipeline import extract_pdf

app = typer.Typer(no_args_is_help=True, add_completion=False)


@app.callback()
def _root() -> None:
    """ht_lens — PDF layout-preserving translator + chat tool (Phase 1: extract)."""


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
    save_images: bool = typer.Option(
        False, "--save-images/--no-save-images", help="Extract image blocks to images/."
    ),
    overwrite: bool = typer.Option(
        False, "--overwrite/--no-overwrite", help="Replace managed files in out dir."
    ),
) -> None:
    """Extract a PDF to page PNGs + block JSONs + doc_meta.json."""
    try:
        result = extract_pdf(pdf, out, dpi=dpi, save_images=save_images, overwrite=overwrite)
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


def main(argv: list[str] | None = None) -> int:
    try:
        app(argv if argv is not None else sys.argv[1:], standalone_mode=False)
    except typer.Exit as exc:
        return int(exc.exit_code)
    except SystemExit as exc:
        return int(exc.code) if isinstance(exc.code, int) else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
