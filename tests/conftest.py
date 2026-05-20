"""Shared pytest fixtures."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ht_lens.db.base import Base
from ht_lens.db.session import make_engine, make_session_factory
from ht_lens.llm.client import LLMClient
from ht_lens.llm.mock import MockLLMClient

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def tmp_workdir(tmp_path: Path) -> Path:
    """Isolated working directory rooted under pytest tmp_path."""
    work = tmp_path / "work"
    work.mkdir()
    return work


def _fixture_pdf(name: str) -> Path:
    path = FIXTURES_DIR / name
    if not path.exists():
        pytest.skip(f"fixture PDF 없음: {name}")
    return path


@pytest.fixture
def sample_en_pdf() -> Path:
    return _fixture_pdf("sample_en.pdf")


@pytest.fixture
def sample_ko_pdf() -> Path:
    return _fixture_pdf("sample_ko.pdf")


@pytest.fixture
def sample_mixed_pdf() -> Path:
    return _fixture_pdf("sample_mixed.pdf")


@pytest.fixture
def llm_mock() -> LLMClient:
    """Deterministic mock LLM client. Replaces the Phase 0 placeholder."""
    return MockLLMClient()


@pytest.fixture
def tmp_db_path(tmp_path: Path) -> Path:
    """Disposable SQLite path under pytest tmp_path."""
    return tmp_path / "test.db"


@pytest_asyncio.fixture
async def async_session_factory(
    tmp_db_path: Path,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """Fresh async session factory bound to an empty ORM-created schema.

    Alembic itself is exercised separately by ``integration/test_alembic.py``.
    """
    engine = make_engine(tmp_db_path)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = make_session_factory(engine)
    try:
        yield factory
    finally:
        await engine.dispose()


@pytest.fixture
def api_db_path(tmp_path: Path) -> Path:
    """SQLite DB path with alembic head applied. Used by API integration tests."""
    import subprocess
    import sys

    db_path = tmp_path / "api.db"
    env = {**os.environ, "HT_LENS_DB_URL": f"sqlite+aiosqlite:///{db_path}"}
    repo_root = Path(__file__).resolve().parents[1]
    proc = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=str(repo_root),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        pytest.fail(f"alembic upgrade failed: {proc.stdout}\n{proc.stderr}")
    return db_path


@pytest.fixture
def live_llm_client() -> LLMClient:
    """Real OpenAICompatibleClient — skip if LLM_BASE_URL / LLM_MODEL not set."""
    from ht_lens.llm.openai_compat import OpenAICompatibleClient

    base_url = os.environ.get("LLM_BASE_URL")
    model = os.environ.get("LLM_MODEL")
    if not base_url or not model:
        pytest.skip("LLM_BASE_URL / LLM_MODEL not set — skipping live LLM test")
    return OpenAICompatibleClient(base_url=base_url, model=model)
