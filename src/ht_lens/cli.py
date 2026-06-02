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
    MineruError,
    OutputDirNotEmptyError,
    SchemaVersionMismatch,
)
from ht_lens.extract.pipeline import extract_pdf
from ht_lens.translate.cli import translate_command

app = typer.Typer(no_args_is_help=True, add_completion=False)

_DEFAULT_DB = Path("data/ht_lens.db")


def _db_path_from_env() -> Path:
    url = os.environ.get("HT_LENS_DB_URL", "")
    if not url:
        return _DEFAULT_DB
    if url.startswith("sqlite+aiosqlite:///"):
        return Path(url.removeprefix("sqlite+aiosqlite:///"))
    # Phase 8e-3 §2: fail loud on a malformed value instead of silently falling
    # back to the 1.x _DEFAULT_DB (would serve the wrong DB during cutover).
    raise ValueError(f"HT_LENS_DB_URL must be 'sqlite+aiosqlite:///<path>' or unset; got {url!r}")


app.command("translate")(translate_command)


@app.callback()
def _root() -> None:
    """ht_lens — PDF layout-preserving translator + chat tool."""


@app.command("serve")
def serve_command(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8080, "--port", min=1, max=65535),
    reload: bool = typer.Option(
        False, "--reload/--no-reload", help="Enable uvicorn auto-reload (dev only)."
    ),
    db: Path | None = typer.Option(  # noqa: B008
        None,
        "--db",
        resolve_path=True,
        help="SQLite DB path. Sets HT_LENS_DB_URL for the lifespan.",
    ),
    skip_llm_check: bool = typer.Option(
        False,
        "--skip-llm-check/--no-skip-llm-check",
        help="Skip the LLM health check during startup (use for dev/test).",
    ),
) -> None:
    """Run the FastAPI server."""
    import uvicorn

    if db is not None:
        os.environ["HT_LENS_DB_URL"] = f"sqlite+aiosqlite:///{db}"
    if skip_llm_check:
        os.environ["HT_LENS_SKIP_LLM_CHECK"] = "1"

    if reload:
        uvicorn.run(
            "ht_lens.api.app:create_app",
            host=host,
            port=port,
            factory=True,
            reload=True,
        )
        return

    from ht_lens.api.app import create_app

    uvicorn.run(create_app(), host=host, port=port)


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


@app.command("embed")
def embed_command(
    doc_id: int | None = typer.Option(
        None,
        "--doc-id",
        help="Embed only this document's translated blocks. Omit to embed all.",
    ),
    batch_size: int = typer.Option(16, "--batch-size", min=1, max=256, help="Encoder batch size."),
    db: Path | None = typer.Option(  # noqa: B008
        None,
        "--db",
        resolve_path=True,
        help="SQLite DB path. Defaults to HT_LENS_DB_URL env var or data/ht_lens.db.",
    ),
) -> None:
    """Phase 7a — backfill ``block_embeddings`` for translated blocks.

    Idempotent: blocks already at the current ``source_hash`` are skipped.
    Uses ``BAAI/bge-m3`` on CPU; first run downloads ~2 GB.
    """
    from ht_lens.dotenv_loader import load_repo_dotenv

    load_repo_dotenv()

    from ht_lens.db.session import make_engine, make_session_factory
    from ht_lens.embedding.backfill import backfill
    from ht_lens.embedding.factory import from_env_embedding

    db_path = db if db is not None else _db_path_from_env()

    async def _run() -> None:
        client = from_env_embedding()
        if client is None:
            typer.echo(
                "error: RAG_DISABLED is set — embedding subsystem disabled. "
                "Unset RAG_DISABLED or use EMBEDDING_PROVIDER=mock for dev.",
                err=True,
            )
            raise typer.Exit(code=5)
        engine = make_engine(db_path)
        factory = make_session_factory(engine)
        try:
            async with factory() as session:
                stats = await backfill(session, client, doc_id=doc_id, batch_size=batch_size)
            typer.echo(
                f"ok: doc_id={doc_id} candidates={stats['candidates']} "
                f"embedded={stats['embedded']} skipped={stats['skipped']}"
            )
        finally:
            await engine.dispose()

    try:
        asyncio.run(_run())
    except SchemaVersionMismatch as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=3) from exc
    except HtLensError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=exc.exit_code) from exc


@app.command("extract-mineru")
def extract_mineru_command(
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
        help="MinerU output directory.",
    ),
    lang: str = typer.Option("en", "--lang", help="OCR language hint (en, korean, ch, ...)."),
    backend: str = typer.Option("pipeline", "--backend", help="MinerU backend."),
    timeout: int = typer.Option(
        3600,
        "--timeout",
        min=1,
        help="MinerU subprocess timeout in seconds. Raise for large PDFs "
        "(e.g. a 500+ page textbook on CPU may exceed the 3600s default).",
    ),
) -> None:
    """ht_lens 2.0 — run MinerU (CPU) on a PDF; print the content_list path.

    MinerU must be installed and on ``PATH`` or pointed to by
    ``HT_LENS_MINERU_BIN``. Extraction is a one-time CPU batch.
    """
    from ht_lens.extract_mineru.runner import run_mineru

    try:
        result = run_mineru(pdf, out, lang=lang, backend=backend, timeout_s=timeout)
    except MineruError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=exc.exit_code) from exc
    typer.echo(
        f"ok: content_list={result.content_list_path} "
        f"images={result.images_dir} md={result.markdown_path}"
    )


@app.command("ingest-mineru")
def ingest_mineru_command(
    content_list: Path = typer.Argument(  # noqa: B008
        ...,
        exists=True,
        readable=True,
        resolve_path=True,
        help="MinerU *_content_list.json (or its output dir).",
    ),
    filename: str = typer.Option(..., "--filename", help="Display filename for the document."),
    src: str = typer.Option("en", "--src", help="Source language code."),
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
    """ht_lens 2.0 — ingest a MinerU content_list.json into the chunks schema."""
    from ht_lens.db.session import make_engine, make_session_factory
    from ht_lens.extract_mineru.runner import _discover_outputs

    # Accept either the content_list.json file or the MinerU output dir.
    if content_list.is_dir():
        try:
            discovered = _discover_outputs(content_list)
        except MineruError as exc:
            typer.echo(f"error: {exc}", err=True)
            raise typer.Exit(code=exc.exit_code) from exc
        cl_path = discovered.content_list_path
        images_dir = discovered.images_dir
        md_path = discovered.markdown_path
    else:
        cl_path = content_list
        cand = cl_path.parent / "images"
        images_dir = cand if cand.is_dir() else None
        md_matches = sorted(cl_path.parent.glob("*.md"))
        md_path = md_matches[0] if md_matches else None

    db_path = db if db is not None else _db_path_from_env()

    async def _run() -> None:
        from ht_lens.ingest_mineru.pipeline import ingest_mineru_output

        engine = make_engine(db_path)
        factory = make_session_factory(engine)
        try:
            async with factory() as session:
                stats = await ingest_mineru_output(
                    cl_path,
                    session,
                    filename=filename,
                    src=src,
                    tgt=tgt,
                    images_dir=images_dir,
                    markdown_path=md_path,
                    overwrite=overwrite,
                )
                await session.commit()
            typer.echo(
                f"ok: doc_id={stats.document_id} chunks={stats.chunks} images={stats.images}"
            )
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


@app.command("repair-images")
def repair_images_command(
    doc_id: int = typer.Option(..., "--doc-id", help="2.0 (MinerU) document id to repair."),
    seed: Path = typer.Option(  # noqa: B008
        ...,
        "--seed",
        exists=True,
        readable=True,
        help="Reviewed repair seed JSON (image_allowlist + captions), e.g. repair_seeds/doc1.json.",
    ),
    pdf: Path = typer.Option(  # noqa: B008
        None, "--pdf", help="Source PDF. Defaults to *_origin.pdf in the doc's MinerU output dir."
    ),
    apply: bool = typer.Option(
        False, "--apply/--dry-run", help="Write manifest + clip-rendered images (default dry-run)."
    ),
    db: Path = typer.Option(  # noqa: B008
        None, "--db", resolve_path=True, help="SQLite DB (default HT_LENS_DB_URL/data/ht_lens.db)."
    ),
) -> None:
    """Phase 8e-5 — regenerate a doc's non-destructive image/caption overrides.

    Deterministic + re-ingest-safe: clip-renders degraded figures from the
    source PDF and merges the reviewed caption corrections from ``seed`` into
    ``<extracts>/<doc_id>/overrides.json``. DB is never mutated."""
    import json

    from sqlalchemy import select

    from ht_lens.db.models import Chunk, Document
    from ht_lens.db.session import make_engine, make_session_factory
    from ht_lens.image_repair import CaptionOverride, build_and_save_overrides

    seed_data = json.loads(seed.read_text())
    allowlist = set(seed_data.get("image_allowlist") or []) or None
    captions = [
        CaptionOverride(c["page_idx"], c["orig_basename"], c["bbox"], c["caption"])
        for c in seed_data.get("captions", [])
    ]
    extracts_root = Path(os.environ.get("HT_LENS_EXTRACTS_V2_DIR", "data/extracts_v2"))
    db_path = db if db is not None else _db_path_from_env()

    async def _run() -> tuple[list[str], int]:
        engine = make_engine(db_path)
        factory = make_session_factory(engine)
        try:
            async with factory() as session:
                doc = await session.get(Document, doc_id)
                if doc is None:
                    raise typer.BadParameter(f"document {doc_id} not found")
                pdf_path = pdf
                if pdf_path is None and doc.markdown_path:
                    cands = sorted(Path(doc.markdown_path).parent.glob("*_origin.pdf"))
                    pdf_path = cands[0] if cands else None
                if pdf_path is None or not Path(pdf_path).is_file():
                    raise typer.BadParameter("source PDF not found (pass --pdf)")
                rows = (
                    await session.execute(
                        select(Chunk)
                        .where(Chunk.doc_id == doc_id, Chunk.type == "image")
                        .order_by(Chunk.order_idx)
                    )
                ).scalars()
                chunks: list[tuple[int, str | None, list[float] | None]] = [
                    (c.page_idx, c.img_path, c.bbox) for c in rows
                ]
            ov, report = build_and_save_overrides(
                chunks=chunks,
                pdf_path=pdf_path,
                dest_root=extracts_root / str(doc_id),
                caption_overrides=captions,
                allowlist_basenames=allowlist,
                dry_run=not apply,
            )
            return [o.fixed_basename for o in ov.images], sum(1 for c in report if c.detected)
        finally:
            await engine.dispose()

    fixed, detected = asyncio.run(_run())
    mode = "applied" if apply else "dry-run"
    typer.echo(
        f"ok ({mode}): detected={detected} images, written={len(fixed)}, "
        f"captions={len(captions)} -> {extracts_root / str(doc_id) / 'overrides.json'}"
    )


@app.command("translate-chunks")
def translate_chunks_command(
    doc_id: int = typer.Option(..., "--doc-id", help="2.0 (MinerU) document id to translate."),
    concurrency: int = typer.Option(7, "--concurrency", min=1, max=32),
    retry_failed: bool = typer.Option(
        False, "--retry-failed/--no-retry-failed", help="Re-process status='failed' chunks only."
    ),
    short_only: bool = typer.Option(
        False,
        "--short-only/--no-short-only",
        help="Re-translate only short low-context chunks (<--max-chars) WITH neighbour "
        "context, bypassing the content cache (cache_key=NULL). Excludes reference "
        "numbers and math.",
    ),
    max_chars: int = typer.Option(
        25, "--max-chars", min=1, help="Length bound for --short-only candidate selection."
    ),
    chunk_id: list[int] = typer.Option(  # noqa: B008
        None,
        "--chunk-id",
        help="Re-translate these explicit chunk id(s) with neighbour context (repeatable). "
        "Implies the --short-only re-translation path; ignores --max-chars selection.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run/--no-dry-run",
        help="With --short-only/--chunk-id: print before/after without writing the DB.",
    ),
    db: Path = typer.Option(  # noqa: B008
        None,
        "--db",
        resolve_path=True,
        help="SQLite DB path (default HT_LENS_DB_URL or data/ht_lens.db).",
    ),
) -> None:
    """ht_lens 2.0 — translate a document's chunks (qwen + math placeholder protect)."""
    from ht_lens.dotenv_loader import load_repo_dotenv

    load_repo_dotenv()
    from ht_lens.db.schema_guard import require_schema_head
    from ht_lens.db.session import make_engine, make_session_factory
    from ht_lens.llm.factory import from_env_translate

    db_path = db if db is not None else _db_path_from_env()

    async def _run() -> None:
        # --dry-run only has meaning for the re-translation branch; the full
        # translate_chunks path has no dry-run mode and would WRITE. Reject the
        # misuse fail-fast (exit 2) instead of silently ignoring the flag and
        # mutating the DB (verify-cross 8d-2c R1 defect A).
        if dry_run and not (short_only or chunk_id):
            raise ValueError(
                "--dry-run requires --short-only or --chunk-id "
                "(the full translate-chunks path has no dry-run and would write)"
            )
        engine = make_engine(db_path)
        factory = make_session_factory(engine)
        try:
            # Schema-head BEFORE the LLM (verify-cross 8e-3 §2): a stale/1.x DB
            # gets a clean SchemaVersionMismatch (exit 3), not an LLM health
            # exit 4. Makes the contract hold for the --short-only path too.
            async with factory() as session:
                await require_schema_head(session)
            llm = from_env_translate()
            # Verify endpoint health before starting (fail-fast, mirrors the 1.x
            # `translate` command). Without this the LLMHealthCheckFailed branch
            # below is unreachable since per-chunk errors become failed rows
            # (verify-cross R2).
            await llm.health_check()
            async with factory() as session:
                # --short-only / --chunk-id: neighbour-context re-translation
                # (Phase 8d-2c). Bypasses the content cache and writes
                # cache_key=NULL so a context-specific phrase can't poison a
                # future identical-source chunk (challenge R1).
                if short_only or chunk_id:
                    from sqlalchemy import select

                    from ht_lens.db.models import Document
                    from ht_lens.translate.short_retranslate import retranslate_short

                    doc = (
                        await session.execute(select(Document).where(Document.id == doc_id))
                    ).scalar_one_or_none()
                    if doc is None:
                        raise ValueError(f"unknown 2.0 doc_id={doc_id}")
                    rstats = await retranslate_short(
                        session,
                        doc,
                        llm,
                        max_chars=max_chars,
                        chunk_ids=set(chunk_id) if chunk_id else None,
                        dry_run=dry_run,
                    )
                    for cid, before, after in rstats.previews:
                        typer.echo(f"  chunk {cid}: {before!r} -> {after!r}")
                    typer.echo(
                        f"ok: doc_id={doc_id} mode={'dry-run' if dry_run else 'apply'} "
                        f"candidates={rstats.candidates} retranslated={rstats.retranslated} "
                        f"failed={rstats.failed}"
                    )
                    if rstats.failed > 0:
                        typer.echo(
                            f"warning: {rstats.failed} chunk(s) failed re-translation", err=True
                        )
                        raise typer.Exit(code=1)
                    return

                from ht_lens.translate.chunk_pipeline import translate_chunks

                stats = await translate_chunks(
                    doc_id, session, llm, concurrency=concurrency, retry_failed=retry_failed
                )
            typer.echo(
                f"ok: doc_id={stats.document_id} translated={stats.translated} "
                f"passthrough={stats.passthrough} cached={stats.cached} "
                f"skipped={stats.skipped} failed={stats.failed}"
            )
            # Non-zero exit when any chunk failed, so batch/automation (8e
            # migration) detects failures instead of silently proceeding —
            # the real defect verify-cross R2 caught. Mirrors 1.x translate.
            if stats.failed > 0:
                typer.echo(f"warning: {stats.failed} chunk(s) failed translation", err=True)
                raise typer.Exit(code=1)
        finally:
            await engine.dispose()

    from ht_lens.llm.errors import LLMConfigurationError, LLMHealthCheckFailed

    try:
        asyncio.run(_run())
    except LLMConfigurationError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=5) from exc
    except LLMHealthCheckFailed as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=4) from exc
    except SchemaVersionMismatch as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=3) from exc
    except ValueError as exc:  # translate_chunks raises on unknown doc_id
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    except HtLensError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=exc.exit_code) from exc


@app.command("embed-chunks")
def embed_chunks_command(
    doc_id: int | None = typer.Option(
        None, "--doc-id", help="Embed only this 2.0 document's chunks."
    ),
    batch_size: int = typer.Option(16, "--batch-size", min=1, max=256),
    db: Path = typer.Option(  # noqa: B008
        None,
        "--db",
        resolve_path=True,
        help="SQLite DB path (default HT_LENS_DB_URL or data/ht_lens.db).",
    ),
) -> None:
    """ht_lens 2.0 — backfill ``chunk_embeddings`` for translated text/heading chunks."""
    from ht_lens.dotenv_loader import load_repo_dotenv

    load_repo_dotenv()
    from ht_lens.db.session import make_engine, make_session_factory
    from ht_lens.embedding.factory import from_env_embedding

    db_path = db if db is not None else _db_path_from_env()

    async def _run() -> None:
        client = from_env_embedding()
        if client is None:
            typer.echo(
                "error: RAG_DISABLED is set — embedding subsystem disabled. "
                "Unset RAG_DISABLED or use EMBEDDING_PROVIDER=mock for dev.",
                err=True,
            )
            raise typer.Exit(code=5)
        engine = make_engine(db_path)
        factory = make_session_factory(engine)
        try:
            async with factory() as session:
                from ht_lens.embedding.chunk_backfill import backfill_chunks

                stats = await backfill_chunks(session, client, doc_id=doc_id, batch_size=batch_size)
            typer.echo(
                f"ok: doc_id={doc_id} candidates={stats['candidates']} "
                f"embedded={stats['embedded']} skipped={stats['skipped']}"
            )
        finally:
            await engine.dispose()

    try:
        asyncio.run(_run())
    except SchemaVersionMismatch as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=3) from exc
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
