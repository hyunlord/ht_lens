# Phase 2a — Verify (self)

**Date**: 2026-05-20
**HEAD**: 4302837
**git status at write time**: clean

---

## 5-A. Automated checks

| Check | Command | Result |
|-------|---------|--------|
| Lint | `uv run ruff check src/ tests/` | All checks passed! |
| Format | `uv run ruff format --check src/ tests/` | (hooks auto-format on commit — clean at HEAD) |
| Type | `uv run mypy src/` | Success: no issues found in 31 source files |
| Test | `uv run pytest -q` | **95 passed**, 5 warnings in 47.18s |
| Coverage | (ingest pipeline) | pipeline.py 94%, llm/mock.py 85% |
| CI | — | not yet pushed; local checks all green |

## 5-B. Functional checks

### DB schema
- `alembic upgrade head` creates 7 ORM tables + `alembic_version` (confirmed by `test_alembic_upgrade_head_creates_all_tables`)
- `current_schema_version()` returns `"0001"` == `ALEMBIC_HEAD`
- PRAGMA `foreign_keys=ON` enforced via event listener (overwrite cascade test exercises FK enforcement)

### LLMClient
- `MockLLMClient.translate("Hello", src="en", tgt="ko")` → `"[KO] Hello"` ✓
- `MockLLMClient.chat([{"role":"user","content":"Hi"}])` → `"mock: Hi"` ✓
- `MockLLMClient.health_check()` → `True` ✓
- `from_env()` with `LLM_PROVIDER=mock` → MockLLMClient ✓
- `from_env()` with unknown provider → `NotImplementedError` ✓
- No `httpx`/`openai`/`requests` imports anywhere in `src/`

### Ingest pipeline
- Single-page en: pages=1, blocks=3 — IngestStats correct ✓
- 3-page ko: pages=3, blocks=6, tgt="en" ✓
- Row counts verified in separate session after commit ✓
- `--overwrite`: bottom-up bulk delete avoids FK violation; document replaced ✓
- Duplicate without `--overwrite` → `DocumentAlreadyIngested` ✓
- `lang_guess="mixed"` without `--src` → `IngestError` (ambiguous) ✓
- `lang_guess="unknown"` without `--src` → `IngestError` (ambiguous) ✓
- Schema version mismatch (version="9999") → `SchemaVersionMismatch` ✓
- Missing `alembic_version` table → `SchemaVersionMismatch` ✓
- Missing `doc_meta.json` → `IngestError` ✓
- Missing PNG → `IngestError` ✓
- `num_pages` mismatch (declare 2, write 1) → `IngestError(match="mismatch")` ✓
- Non-existent extract dir → `IngestError(match="not found")` ✓

### CLI (subprocess round-trip)
- `python -m ht_lens.ingest <dir> --db <db>` on all 3 fixtures:
  - sample_en.pdf: `ok: doc_id=1 pages=8 blocks=...` ✓
  - sample_ko.pdf: `ok: doc_id=1 pages=52 blocks=...` ✓
  - sample_mixed.pdf (--src en): `ok: doc_id=1 pages=6 blocks=...` ✓
- Duplicate → exit 2, "already ingested" in stderr ✓
- `--overwrite` → exit 0 ✓
- Missing dir → exit ≠ 0 (Typer validates `exists=True`) ✓
- `ht-lens ingest` console script: tested (skipped if .venv/bin/ht-lens absent)

## 5-C. Scoring (100, self-assessment)

| Item | Score / Max | Evidence |
|------|-------------|---------|
| 독창성 | 12 / 15 | 7-table async ORM + Alembic hand-written migration. `-3`: `ht-lens db migrate` 편의 명령 plan-in-scope였으나 미구현 |
| 완결성 | 32 / 35 | 95 tests pass, 3 fixture CLI round-trip, all error paths covered. `-3`: bg_image_path 절대경로 (known debt) |
| 안정성 | 28 / 30 | FK-safe overwrite, schema version gate, single-transaction rollback. `-2`: translations.block_id PK multi-model collision (plan-acknowledged Phase 6 debt) |
| 확장성 | 18 / 20 | Protocol/factory pattern for LLM, session factory injection. `-2`: async session 전달 방식이 FastAPI dependency injection 패턴으로 전환 시 리팩토링 필요 |
| **Total** | **90 / 100** | |

## 5-D. Self verdict

- [x] PASS_CANDIDATE (≥80) — 기능 완결, 테스트 95/95 green, mypy/ruff clean
- [ ] FAIL → RE-CODE
- [ ] FAIL → RE-PLAN

감점 요약:
1. `ht-lens db migrate` 미구현 (-3): debate에서 "불필요" 의견 있었고 `alembic upgrade head` 직접 사용이 기능적으로 동등
2. `bg_image_path` 절대경로 (-3): plan Decision 5 acknowledged debt
3. `translations.block_id` PK (-2): plan Decision 6 acknowledged, Phase 6 migration 예정
4. FastAPI DI 리팩토링 예상 (-2): Phase 3에서 자연스럽게 처리될 scope
