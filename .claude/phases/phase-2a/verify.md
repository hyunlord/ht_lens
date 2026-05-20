# Phase 2a — Verify (self) v3

**Date**: 2026-05-20
**HEAD**: cda24bd
**git status at write time**: clean

---

## 5-A. Automated checks

| Check | Command | Result |
|-------|---------|--------|
| Lint | `uv run ruff check .` | All checks passed! |
| Format | `uv run ruff format --check .` | 53 files already formatted |
| Type | `uv run mypy src/` | Success: no issues found in 31 source files |
| Test | `uv run pytest -q` | **97 passed**, 5 warnings in 47.26s |
| Coverage | `uv run pytest -q` (global cov enabled) | TOTAL 82% (pipeline.py 95%) |
| CI | — | not yet pushed; local checks all green |

## 5-B. Functional checks

### DB schema
- `alembic upgrade head` creates 7 ORM tables + `alembic_version` ✓
- `current_schema_version()` returns `"0001"` == `ALEMBIC_HEAD` ✓
- PRAGMA `foreign_keys=ON` enforced on every connection ✓

### LLMClient
- `MockLLMClient.translate("Hello", src="en", tgt="ko")` → `"[KO] Hello"` ✓
- `MockLLMClient.chat(messages)` → `"mock: <last user content>"` ✓
- `MockLLMClient.health_check()` → `True` ✓
- `from_env()` default → MockLLMClient; unknown → NotImplementedError ✓
- Zero `httpx`/`openai`/`requests` imports in `src/` ✓

### Ingest pipeline (happy path + error path)
- Single-page en: pages=1, blocks=3 — IngestStats correct ✓
- 3-page ko: pages=3, blocks=6, tgt="en" ✓
- Row counts verified in separate session after commit ✓
- `--overwrite` with empty DB: document replaced, count=1 ✓
- `--overwrite` with seeded Translation/Thread/Message rows: cascade deletes
  messages→threads/translations→blocks→pages→document without FK error ✓ (new in RE-CODE)
- Duplicate without `--overwrite` → `DocumentAlreadyIngested` ✓
- `lang_guess="mixed"` without `--src` → `IngestError` (ambiguous) ✓
- `lang_guess="unknown"` without `--src` → `IngestError` (ambiguous) ✓
- Schema version mismatch → `SchemaVersionMismatch` ✓
- Missing `alembic_version` → `SchemaVersionMismatch` ✓
- Missing `doc_meta.json` → `IngestError` ✓
- Missing PNG → `IngestError` ✓
- `num_pages` mismatch → `IngestError(match="mismatch")` ✓
- page_num JSON ≠ filename → `IngestError(match="page_num mismatch")` ✓ (new in RE-CODE)
- Non-existent extract dir → `IngestError(match="not found")` ✓

### CLI (subprocess round-trip)
- `python -m ht_lens.ingest <dir> --db <db>` on all 3 real fixtures:
  - sample_en.pdf: `ok: doc_id=1 pages=8 blocks=...` ✓
  - sample_ko.pdf: `ok: doc_id=1 pages=52 blocks=...` ✓
  - sample_mixed.pdf (--src en): `ok: doc_id=1 pages=6 blocks=...` ✓
- Duplicate → exit 2, "already ingested" in stderr ✓
- `--overwrite` → exit 0 ✓
- Missing dir → exit ≠ 0 ✓

## 5-C. Scoring (100, self-assessment)

| Item | Score / Max | Evidence |
|------|-------------|---------|
| 독창성 | 12 / 15 | 7-table async ORM + Alembic hand-written migration + Protocol/factory pattern. `-3`: `ht-lens db migrate` 미구현 (debate에서 "불필요" 의견, alembic CLI가 동등) |
| 완결성 | 32 / 35 | 97 tests pass, 3 fixture CLI round-trip, all error paths covered, RE-CODE issues fixed. `-3`: bg_image_path 절대경로 (plan-acknowledged known debt) |
| 안정성 | 27 / 30 | FK-safe full overwrite cascade, page_num validation, schema version gate, single-transaction rollback. `-3`: src_pdf_sha256 미저장 (prompt-fixed schema 이탈 없이 filename-only identity; Phase 3+ 이슈) |
| 확장성 | 18 / 20 | Protocol/factory pattern for LLM, session factory injection. `-2`: async session DI FastAPI 전환 시 리팩토링 예상 |
| **Total** | **89 / 100** | |

## 5-D. Self verdict

- [x] PASS_CANDIDATE (≥80) — 기능 완결, 97 tests green, mypy/ruff clean, RE-CODE 완료
- [ ] FAIL → RE-CODE
- [ ] FAIL → RE-PLAN

> **Note on threshold**: WORKFLOW.md §5 scoring table shows `≥95` for `CONFIRM_PASS` (Codex cross-verify verdict) and `<95` triggers RE-CODE from Codex side. The self-score here (89) is below 95 — this is expected: the cross-verify Round 2 will decide CONFIRM_PASS or further RE-CODE. The `PASS_CANDIDATE` checkbox means "ready to submit for cross-review", not "auto-pass."

감점 요약:
1. `ht-lens db migrate` 미구현 (-3): Phase 2a scope에 있었으나 debate에서 "불필요" 의견이 강했음
2. `bg_image_path` 절대경로 (-3): plan Decision 5 acknowledged debt
3. `src_pdf_sha256` 미저장 (-3): prompt-fixed schema에 없음, Phase 3+ 논의 예정
4. FastAPI DI 리팩토링 예상 (-2): Phase 3에서 자연 처리
