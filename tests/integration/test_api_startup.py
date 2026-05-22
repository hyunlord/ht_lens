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
