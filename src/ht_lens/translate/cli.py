"""Translate CLI — Phase 2b.

Standalone: ``python -m ht_lens.translate --doc-id <id>``
Main app:   ``ht-lens translate --doc-id <id>``
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import typer

from ht_lens.errors import SchemaVersionMismatch
from ht_lens.llm.errors import LLMHealthCheckFailed

app = typer.Typer(add_completion=False)

_DEFAULT_DB = Path("data/ht_lens.db")


def _db_path_from_env() -> Path:
    url = os.environ.get("HT_LENS_DB_URL", "")
    if url.startswith("sqlite+aiosqlite:///"):
        return Path(url.removeprefix("sqlite+aiosqlite:///"))
    return _DEFAULT_DB


def translate_command(
    doc_id: int = typer.Option(..., "--doc-id", help="Document ID to translate."),
    concurrency: int = typer.Option(
        7,
        "--concurrency",
        min=1,
        max=50,
        help=(
            "Concurrent LLM calls. Default 7 matches sglang's "
            "effective_max_running_requests_per_dp."
        ),
    ),
    max_retries: int = typer.Option(3, "--max-retries", min=0),
    retry_failed: bool = typer.Option(
        False,
        "--retry-failed/--no-retry-failed",
        help="Re-translate blocks with status='failed'.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run/--no-dry-run",
        help="Estimate cache stats without calling LLM.",
    ),
    db: Path | None = typer.Option(  # noqa: B008
        None, "--db", resolve_path=True, help="SQLite DB path."
    ),
) -> None:
    """Translate all text/header blocks for a document."""
    # Phase 6e-2: pull repo-root .env into os.environ BEFORE building the
    # LLM. Without this, missing shell exports silently fall through to
    # MockLLMClient and the run pollutes the DB with ``[KO] <english>``
    # output. Function-local (not module-level) so importing this module
    # in tests does not mutate env at collection time.
    from ht_lens.dotenv_loader import load_repo_dotenv

    load_repo_dotenv()

    from ht_lens.db.session import make_engine, make_session_factory
    from ht_lens.llm.errors import LLMConfigurationError
    from ht_lens.llm.factory import from_env_translate
    from ht_lens.translate.pipeline import translate_document

    db_path = db if db is not None else _db_path_from_env()
    try:
        llm = from_env_translate()
    except LLMConfigurationError as exc:
        typer.echo(f"error: LLM not configured: {exc}", err=True)
        raise typer.Exit(code=5) from exc

    async def _run() -> None:
        if not dry_run:
            # Verify endpoint health before starting (reasoning_tokens == 0 regression guard).
            # Skipped in dry-run so offline cache-estimation works without a live endpoint.
            await llm.health_check()

        engine = make_engine(db_path)
        factory = make_session_factory(engine)
        try:
            async with factory() as session:
                stats = await translate_document(
                    doc_id,
                    session,
                    llm,
                    concurrency=concurrency,
                    max_retries=max_retries,
                    retry_failed=retry_failed,
                    dry_run=dry_run,
                )
            if not dry_run and stats.failed > 0:
                typer.echo(
                    f"warning: {stats.failed} block(s) failed translation",
                    err=True,
                )
                raise typer.Exit(code=1)
            if dry_run:
                total = stats.translated + stats.cached
                typer.echo(
                    f"dry_run: doc_id={stats.document_id} "
                    f"total={total} cache_hits={stats.cached} "
                    f"estimated_llm_calls={stats.translated}"
                )
            else:
                typer.echo(
                    f"ok: doc_id={stats.document_id} "
                    f"translated={stats.translated} cached={stats.cached} "
                    f"skipped={stats.skipped} failed={stats.failed}"
                )
        finally:
            await engine.dispose()

    try:
        asyncio.run(_run())
    except typer.Exit:
        raise
    except LLMHealthCheckFailed as exc:
        typer.echo(f"error: health_check failed: {exc}", err=True)
        raise typer.Exit(code=4) from exc
    except SchemaVersionMismatch as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=3) from exc
    except ValueError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    except Exception as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc


# Register in standalone app
app.command()(translate_command)


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
