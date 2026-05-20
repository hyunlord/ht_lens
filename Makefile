.PHONY: install fmt lint test test-fast check clean

install:
	uv sync --all-extras
	uv run pre-commit install

fmt:
	uv run ruff format .

lint:
	uv run ruff check .
	uv run mypy src/

test:
	uv run pytest

test-fast:
	uv run pytest -m "not llm and not slow"

check: fmt lint test-fast

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache .coverage htmlcov coverage.xml
	find . -type d -name __pycache__ -exec rm -rf {} +
