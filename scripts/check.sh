#!/usr/bin/env bash
#
# check.sh — `make check`와 동일 동작. CI 외부에서 빠르게 검사할 때 사용.
#
set -euo pipefail

echo "[check] ruff format..." >&2
uv run ruff format .

echo "[check] ruff check..." >&2
uv run ruff check .

echo "[check] mypy strict..." >&2
uv run mypy src/

echo "[check] pytest (fast)..." >&2
uv run pytest -m "not llm and not slow"

echo "[check] OK" >&2
