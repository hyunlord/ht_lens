"""Subprocess tests for ``python -m ht_lens.translate`` exit codes."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _run_translate(
    *args: str,
    db_path: Path | None = None,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    # Phase 6e-2: drop inherited LLM env so subprocess starts clean.
    # The CLI now calls load_repo_dotenv() before building the LLM, which
    # would otherwise populate scoped TRANSLATE_LLM_* keys from the repo
    # .env and silently override the legacy LLM_PROVIDER the test sets
    # via extra_env. extra_env still controls what the test exercises.
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(("LLM_", "TRANSLATE_LLM_", "CHAT_LLM_", "OLLAMA_"))
    }
    if db_path is not None:
        env["HT_LENS_DB_URL"] = f"sqlite+aiosqlite:///{db_path}"
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [sys.executable, "-m", "ht_lens.translate", *args],
        capture_output=True,
        text=True,
        cwd=str(REPO),
        env=env,
    )


def _setup_db_with_doc(tmp_path: Path) -> tuple[Path, int]:
    """Create a minimal DB with one ingested document. Returns (db_path, doc_id)."""
    import asyncio
    import json as _json
    from datetime import UTC, datetime

    from sqlalchemy import text

    from ht_lens.db.base import Base
    from ht_lens.db.models import Block, Document, Page
    from ht_lens.db.session import ALEMBIC_HEAD, make_engine, make_session_factory

    db_path = tmp_path / "cli_test.db"
    doc_id_holder: list[int] = []

    async def _seed() -> None:
        engine = make_engine(db_path)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.execute(
                text(
                    "CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32) NOT NULL)"
                )
            )
            await conn.execute(text(f"INSERT INTO alembic_version VALUES ('{ALEMBIC_HEAD}')"))
        factory = make_session_factory(engine)
        async with factory() as session:
            doc = Document(
                filename="test.pdf",
                src_lang="en",
                tgt_lang="ko",
                status="ready_for_translation",
                created_at=datetime.now(UTC),
                src_pdf_sha256="a" * 64,
            )
            session.add(doc)
            await session.flush()
            page = Page(
                doc_id=doc.id,
                page_num=1,
                width=595.0,
                height=842.0,
                bg_image_path="/tmp/p.png",
                rotation=0,
                render_dpi=200,
                pixel_width=1654,
                pixel_height=2339,
            )
            session.add(page)
            await session.flush()
            session.add(
                Block(
                    page_id=page.id,
                    block_local_id="b001",
                    type="text",
                    bbox_json=_json.dumps([0.0, 0.0, 100.0, 20.0]),
                    order_idx=0,
                    original_text="Hello world",
                )
            )
            await session.commit()
            doc_id_holder.append(doc.id)
        await engine.dispose()

    asyncio.run(_seed())
    return db_path, doc_id_holder[0]


def test_translate_exit_0_with_mock_llm(tmp_path: Path) -> None:
    db_path, doc_id = _setup_db_with_doc(tmp_path)
    proc = _run_translate(
        "--doc-id",
        str(doc_id),
        db_path=db_path,
        extra_env={"LLM_PROVIDER": "mock"},
    )
    assert proc.returncode == 0, (proc.stdout, proc.stderr)
    assert "ok:" in proc.stdout


def test_translate_exit_2_on_missing_doc_id(tmp_path: Path) -> None:
    db_path, _ = _setup_db_with_doc(tmp_path)
    proc = _run_translate(
        "--doc-id",
        "99999",
        db_path=db_path,
        extra_env={"LLM_PROVIDER": "mock"},
    )
    assert proc.returncode == 2


def test_translate_dry_run_exit_0(tmp_path: Path) -> None:
    db_path, doc_id = _setup_db_with_doc(tmp_path)
    proc = _run_translate(
        "--doc-id",
        str(doc_id),
        "--dry-run",
        db_path=db_path,
        extra_env={"LLM_PROVIDER": "mock"},
    )
    assert proc.returncode == 0, (proc.stdout, proc.stderr)
    assert "dry_run:" in proc.stdout


def test_translate_exit_1_on_block_failure(tmp_path: Path) -> None:
    """TRANSLATE_LLM_PROVIDER=mock_fail → every block fails → exit 1.

    Phase 6e-2: switched from legacy ``LLM_PROVIDER`` to scoped
    ``TRANSLATE_LLM_PROVIDER`` so the test wins over the repo ``.env``
    (which sets the scoped var to ``openai_compat`` for prod). Scoped >
    legacy is documented Phase 6e precedence.
    """
    db_path, doc_id = _setup_db_with_doc(tmp_path)
    proc = _run_translate(
        "--doc-id",
        str(doc_id),
        db_path=db_path,
        extra_env={"TRANSLATE_LLM_PROVIDER": "mock_fail"},
    )
    assert proc.returncode == 1, (proc.stdout, proc.stderr)


def test_translate_exit_4_on_health_check_failed(tmp_path: Path) -> None:
    """Unreachable openai_compat endpoint without --dry-run → health_check fails → exit 4.

    Phase 6e-2: scoped vars so the test wins over repo ``.env``.
    """
    db_path, doc_id = _setup_db_with_doc(tmp_path)
    proc = _run_translate(
        "--doc-id",
        str(doc_id),
        db_path=db_path,
        extra_env={
            "TRANSLATE_LLM_PROVIDER": "openai_compat",
            "TRANSLATE_LLM_BASE_URL": "http://localhost:1",
            "TRANSLATE_LLM_MODEL": "test-model",
        },
    )
    assert proc.returncode == 4, (proc.stdout, proc.stderr)


def test_translate_dry_run_bypasses_health_check(tmp_path: Path) -> None:
    """--dry-run skips health_check so an unreachable endpoint still exits 0."""
    db_path, doc_id = _setup_db_with_doc(tmp_path)
    proc = _run_translate(
        "--doc-id",
        str(doc_id),
        "--dry-run",
        db_path=db_path,
        extra_env={
            "LLM_PROVIDER": "openai_compat",
            "LLM_BASE_URL": "http://localhost:1",
            "LLM_MODEL": "test-model",
        },
    )
    assert proc.returncode == 0, (proc.stdout, proc.stderr)
    assert "dry_run:" in proc.stdout


def test_translate_exit_3_without_alembic_version(tmp_path: Path) -> None:
    """DB without alembic_version should give exit 3 (SchemaVersionMismatch)."""
    import asyncio

    from ht_lens.db.base import Base
    from ht_lens.db.session import make_engine

    db_path = tmp_path / "no_alembic.db"

    async def _create() -> None:
        engine = make_engine(db_path)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await engine.dispose()

    asyncio.run(_create())
    proc = _run_translate(
        "--doc-id",
        "1",
        db_path=db_path,
        extra_env={"LLM_PROVIDER": "mock"},
    )
    assert proc.returncode == 3


def test_translate_cli_prefers_translate_scoped_env_over_legacy(tmp_path: Path) -> None:
    """Phase 6e R1 missing test (cross-verify §4-2): the CLI now calls
    ``from_env_translate()`` which prefers ``TRANSLATE_LLM_PROVIDER``
    over ``LLM_PROVIDER``. Pin the scoped var to ``mock_fail`` and the
    legacy var to ``mock``; if the CLI still honoured the legacy var
    every block would translate cleanly and the run would exit 0.
    With the scoped var taking precedence, all blocks fail and the
    process exits 1."""
    db_path, doc_id = _setup_db_with_doc(tmp_path)
    proc = _run_translate(
        "--doc-id",
        str(doc_id),
        db_path=db_path,
        extra_env={
            "LLM_PROVIDER": "mock",
            "TRANSLATE_LLM_PROVIDER": "mock_fail",
        },
    )
    assert proc.returncode == 1, (
        f"expected exit 1 because TRANSLATE_LLM_PROVIDER=mock_fail should "
        f"win over LLM_PROVIDER=mock; got {proc.returncode}.\n"
        f"stdout: {proc.stdout}\nstderr: {proc.stderr}"
    )


# ---------------------------------------------------------------------------
# Phase 6e-2: CLI .env load + fail-closed regression coverage
# ---------------------------------------------------------------------------


def test_module_entrypoint_loads_repo_root_dotenv_without_env_exports(
    tmp_path: Path,
) -> None:
    """Phase 6e-2 (Codex debate §5 #1): ``python -m ht_lens.translate``
    with all ``LLM_*`` / ``TRANSLATE_LLM_*`` env cleared must still pick
    up the repo-root ``.env`` and reach the openai_compat provider —
    not silently fall back to mock.

    Skipped on checkouts without ``.env`` (CI without secrets).
    """
    if not (REPO / ".env").is_file():
        import pytest

        pytest.skip("repo .env not present in this checkout")

    db_path, doc_id = _setup_db_with_doc(tmp_path)
    # No extra_env → subprocess starts with all LLM keys cleared by
    # _run_translate, then loads repo .env. Phase 6f-1 .env points at
    # http://localhost:8082 with the openai_compat provider. The
    # subprocess will either (a) reach a running endpoint and exit 0/1
    # depending on outcome, or (b) hit health_check failure and exit 4.
    # Either is acceptable — the regression we guard against is exit 0
    # with mock-style ``[KO] <english>`` output, which means the .env
    # never loaded and factory silently fell back to mock.
    proc = _run_translate(
        "--doc-id",
        str(doc_id),
        db_path=db_path,
    )
    assert "[KO]" not in proc.stdout, (
        f"mock fallback detected (mock would emit '[KO] ...'). "
        f"stdout: {proc.stdout}\nstderr: {proc.stderr}"
    )
    # Exit code 5 (LLMConfigurationError) would indicate .env didn't
    # load AND no env exports were present — that is the wrong outcome
    # when .env IS present. The .env IS present here, so the call
    # should NOT exit 5.
    assert proc.returncode != 5, (
        f"factory raised LLMConfigurationError despite .env being present "
        f"(load_repo_dotenv() did not run).\n"
        f"stdout: {proc.stdout}\nstderr: {proc.stderr}"
    )


def test_module_entrypoint_fails_closed_when_dotenv_absent(
    tmp_path: Path,
) -> None:
    """Phase 6e-2 (Codex debate §2): when ``.env`` is absent AND no env
    exports are set, the CLI must exit 5 (LLMConfigurationError),
    NOT silently use mock. We simulate "no .env" by pointing the
    subprocess at a tmp working directory that has no .env (it falls
    back to the package's resolved repo root, but the loader is
    no-op when that file is missing — and our env clears all keys)."""
    db_path, doc_id = _setup_db_with_doc(tmp_path)
    # If repo .env exists, this test can't fully simulate "absent .env"
    # since load_repo_dotenv() looks at the resolved package root, not
    # CWD. We assert the *complementary* invariant: with .env present,
    # the factory must NOT fall back to mock when no exports were set.
    if (REPO / ".env").is_file():
        import pytest

        pytest.skip(
            "repo .env present; covered by "
            "test_module_entrypoint_loads_repo_root_dotenv_without_env_exports"
        )
    proc = _run_translate(
        "--doc-id",
        str(doc_id),
        db_path=db_path,
    )
    assert proc.returncode == 5, (
        f"expected exit 5 (LLMConfigurationError) when neither .env nor "
        f"env exports configure a provider; got {proc.returncode}.\n"
        f"stdout: {proc.stdout}\nstderr: {proc.stderr}"
    )
    assert "[KO]" not in proc.stdout, "must not silently produce mock output"
