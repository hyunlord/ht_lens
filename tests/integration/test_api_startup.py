"""Phase 3 — FastAPI lifespan startup behaviour."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ht_lens.errors import SchemaVersionMismatch
from ht_lens.llm.errors import LLMHealthCheckFailed


class _HealthyLLM:
    model_name = "healthy"

    async def translate(self, text: str, src: str, tgt: str, *, context: str | None = None) -> str:
        return text

    async def chat(self, messages: list, *, system: str | None = None) -> str:
        return "ok"

    async def health_check(self) -> bool:
        return True


class _UnhealthyLLM(_HealthyLLM):
    async def health_check(self) -> bool:
        raise LLMHealthCheckFailed("boom")


class _FalsyLLM(_HealthyLLM):
    async def health_check(self) -> bool:
        return False


@pytest.fixture
def env_with_db(api_db_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("HT_LENS_DB_URL", f"sqlite+aiosqlite:///{api_db_path}")
    return api_db_path


def test_startup_skips_llm_check_with_env_flag(
    env_with_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HT_LENS_SKIP_LLM_CHECK", "1")
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    from ht_lens.api.app import create_app

    app = create_app()
    with TestClient(app) as client:
        resp = client.get("/documents")
        assert resp.status_code == 200


def test_startup_fails_when_llm_health_check_raises(
    env_with_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Phase 6e: patch BOTH scoped factories so the lifespan's loop hits the
    bad client. translate is checked first — its failure aborts startup."""
    monkeypatch.delenv("HT_LENS_SKIP_LLM_CHECK", raising=False)
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    from ht_lens.api import app as app_module

    monkeypatch.setattr(app_module, "from_env_translate", lambda: _UnhealthyLLM())
    monkeypatch.setattr(app_module, "from_env_chat", lambda: _UnhealthyLLM())
    app = app_module.create_app()
    with pytest.raises(LLMHealthCheckFailed), TestClient(app):
        pass


def test_startup_fails_when_llm_health_check_returns_false(
    env_with_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("HT_LENS_SKIP_LLM_CHECK", raising=False)
    from ht_lens.api import app as app_module

    monkeypatch.setattr(app_module, "from_env_translate", lambda: _FalsyLLM())
    monkeypatch.setattr(app_module, "from_env_chat", lambda: _FalsyLLM())
    app = app_module.create_app()
    with pytest.raises(LLMHealthCheckFailed), TestClient(app):
        pass


def test_startup_fails_when_translate_llm_health_check_fails_but_chat_ok(
    env_with_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Phase 6e R1 missing test (challenge §5-3): one provider healthy,
    the other unhealthy must still abort startup. translate is checked
    first → its failure aborts before chat is reached."""
    monkeypatch.delenv("HT_LENS_SKIP_LLM_CHECK", raising=False)
    from ht_lens.api import app as app_module
    from ht_lens.llm.mock import MockLLMClient

    monkeypatch.setattr(app_module, "from_env_translate", lambda: _UnhealthyLLM())
    monkeypatch.setattr(app_module, "from_env_chat", lambda: MockLLMClient())
    app = app_module.create_app()
    with pytest.raises(LLMHealthCheckFailed), TestClient(app):
        pass


def test_startup_fails_when_chat_llm_health_check_fails_but_translate_ok(
    env_with_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Phase 6e R1 missing test (challenge §5-3): converse — translate
    healthy but chat unhealthy must still abort startup (lifespan loop
    checks both)."""
    monkeypatch.delenv("HT_LENS_SKIP_LLM_CHECK", raising=False)
    from ht_lens.api import app as app_module
    from ht_lens.llm.mock import MockLLMClient

    monkeypatch.setattr(app_module, "from_env_translate", lambda: MockLLMClient())
    monkeypatch.setattr(app_module, "from_env_chat", lambda: _UnhealthyLLM())
    app = app_module.create_app()
    with pytest.raises(LLMHealthCheckFailed), TestClient(app):
        pass


def test_startup_rejects_schema_mismatch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """An empty (uninitialised) DB has no alembic_version → startup must abort."""
    db_path = tmp_path / "blank.db"
    # create empty file to ensure SQLite opens it
    db_path.write_bytes(b"")
    monkeypatch.setenv("HT_LENS_DB_URL", f"sqlite+aiosqlite:///{db_path}")
    monkeypatch.setenv("HT_LENS_SKIP_LLM_CHECK", "1")
    from ht_lens.api.app import create_app

    app = create_app()
    with pytest.raises(SchemaVersionMismatch), TestClient(app):
        pass


# ---------------------------------------------------------------------------
# Phase 7a-3 R1 verify-cross gap: API lifespan uses the embedding factory
# ---------------------------------------------------------------------------


def test_lifespan_uses_embedding_factory_with_mock_provider(
    env_with_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``api/app.py::_lifespan`` must wire to ``from_env_embedding`` so the
    same provider knobs that drive the CLI also drive the long-running
    API. Verified with ``EMBEDDING_PROVIDER=mock``: the lifespan should
    end up with a ``MockEmbeddingClient`` (dim=32) on ``app.state``.
    """
    monkeypatch.setenv("HT_LENS_SKIP_LLM_CHECK", "1")
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
    monkeypatch.delenv("RAG_DISABLED", raising=False)
    from ht_lens.api.app import create_app
    from ht_lens.embedding.service import MockEmbeddingClient

    app = create_app()
    with TestClient(app):
        client = getattr(app.state, "embedding_client", None)
        assert isinstance(client, MockEmbeddingClient), (
            f"expected MockEmbeddingClient on app.state, got {type(client).__name__}"
        )
        assert client.dim == 32


def test_lifespan_handles_embedding_factory_raise(
    env_with_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If ``from_env_embedding`` raises during startup (BgeM3Client init
    failure on a fresh machine, etc.), the lifespan must still come up
    with ``app.state.embedding_client = None`` rather than aborting.

    Phase 7a-3 verify-cross R1 §4: the lifespan's new factory path was
    not directly locked against init failure.
    """
    monkeypatch.setenv("HT_LENS_SKIP_LLM_CHECK", "1")
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.delenv("RAG_DISABLED", raising=False)
    from ht_lens.api import app as app_module

    def _boom() -> object:
        raise RuntimeError("simulated factory failure during lifespan")

    monkeypatch.setattr(app_module, "from_env_embedding", _boom, raising=False)
    # The factory is imported lazily inside _lifespan. Also patch the
    # source module so the local import inside the function picks it up.
    from ht_lens.embedding import factory as factory_module

    monkeypatch.setattr(factory_module, "from_env_embedding", _boom)

    app = app_module.create_app()
    with TestClient(app) as client:
        # API should still come up (fail-soft).
        resp = client.get("/documents")
        assert resp.status_code == 200
        # Embedding client left as None.
        assert getattr(app.state, "embedding_client", "missing") is None
