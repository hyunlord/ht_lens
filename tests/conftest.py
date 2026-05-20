"""Shared pytest fixtures (Phase 0 placeholders).

실제 fixture PDF는 Phase 1에서 추가된다. 그 전까지는 파일이 없으면 skip.
"""

from pathlib import Path
from typing import Any

import pytest

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


class _LLMMock:
    """Placeholder LLM client. Phase 2에서 실제 fake로 교체된다."""

    def __call__(self, *_args: Any, **_kwargs: Any) -> Any:
        raise NotImplementedError("LLM mock은 Phase 2에서 구현된다")

    def complete(self, *_args: Any, **_kwargs: Any) -> Any:
        raise NotImplementedError("LLM mock은 Phase 2에서 구현된다")


@pytest.fixture
def llm_mock() -> _LLMMock:
    return _LLMMock()
