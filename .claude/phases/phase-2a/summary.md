# Phase 2a — Summary

## Status
**ESCALATE TO PLANNER** (cross-verify Round 2 DOWNGRADE)

## Score
- Self (v3, post RE-CODE): **89 / 100**
- Cross-verify Round 1: **REJECT** (~68/100) — Codex
- Cross-verify Round 2: **DOWNGRADE** (~76/100) — Codex
- Max rounds reached (2/2). Per CLAUDE.md, escalating to Planner.

---

## What was built

| Component | Files | Description |
|-----------|-------|-------------|
| DB schema | `src/ht_lens/db/` | 7-table ORM (Document, Page, Block, Translation, Thread, Message, Base), async engine, session factory, schema version gate |
| Alembic migration | `src/ht_lens/db/migrations/` | `0001_initial_schema` — hand-written, deterministic, mypy-clean |
| LLM abstraction | `src/ht_lens/llm/` | `LLMClient` Protocol, `MockLLMClient`, `from_env()` factory |
| Ingest pipeline | `src/ht_lens/ingest/` | `ingest_extract_dir` async function + `__main__.py` entry point |
| CLI | `src/ht_lens/cli.py` | `ht-lens ingest` subcommand added |
| Tests | `tests/` | 97 tests total (19 new ingest/alembic/LLM integration+unit) |

**Key fixes made during RE-CODE (Round 1 → Round 2):**
1. Overwrite cascade extended to cover `messages→threads/translations→blocks→pages→document`
2. `_load_page_docs` validates `page_doc.page_num` against filename-derived number
3. Tests added: FK-safe overwrite with seeded translation/thread/message rows; page_num mismatch

---

## Files changed (this phase vs origin/main)

32 files, +2418 / -15 lines. Key additions:
- `src/ht_lens/db/` (base, models, session, migrations)
- `src/ht_lens/ingest/` (pipeline, __init__, __main__)
- `src/ht_lens/llm/` (client, mock, factory)
- `src/ht_lens/cli.py` (+77 lines for ingest command)
- `alembic.ini`, `pyproject.toml` (3 new deps)
- 5 new test files (97 tests, all pass)

---

## Deviations from plan

| Plan item | Status | Reason |
|-----------|--------|--------|
| `ht-lens db migrate` subcommand | **OMITTED** | debate: "불필요", `alembic upgrade head` is functionally equivalent |
| `bg_image_path` relative vs absolute | **ABSOLUTE** | plan Decision 5 acknowledged as known debt |
| `translations.block_id` as lone PK | **AS PLANNED** | plan Decision 6, Phase 6 migration scheduled |
| `src_pdf_sha256` not persisted | **AS PLANNED** | prompt-fixed schema, not in Phase 2a scope |

---

## Worker position vs Codex position

**Worker (self-score 89/100, PASS_CANDIDATE):**
- All 97 tests green, mypy strict 0 violations, ruff clean
- RE-CODE fixed both code defects from Round 1 (FK cascade, page_num validation)
- Remaining deductions are plan-acknowledged debt or out-of-scope items
- `src_pdf_sha256` not persisted is NOT a defect — it was not in the prompt-fixed schema
- Filename-only identity is Phase 3 scope (when real DB concurrency arises)
- CI green is blocked on `git push`, which is Human's action per CLAUDE.md rules

**Codex (DOWNGRADE, ~76/100):**
- Affirms: Round 1 code defects (FK cascade, page_num) are fixed
- Remaining concerns:
  1. Self-score 89 < 95 threshold → workflow says RE-CODE, but Worker argues 89 is appropriate given acknowledged debt
  2. CI not run (not pushed) — Worker cannot push per CLAUDE.md
  3. Real-fixture DB row evidence limited — CLI test checks stdout only, not DB contents

**Planner judgment needed on:**
1. Is 89/100 acceptable for Phase 2a given the deviations are all plan-acknowledged?
2. Should `src_pdf_sha256` be persisted before closing Phase 2a (requires new migration)?
3. Is `ht-lens db migrate` omission acceptable?

---

## Evidence index

- plan: `.claude/phases/phase-2a/plan.md`
- debate: `.claude/phases/phase-2a/debate.md`
- challenge: `.claude/phases/phase-2a/challenge.md`
- verify v3: `.claude/phases/phase-2a/verify.md`
- verify-cross r1: `.claude/phases/phase-2a/verify-cross.md` (lines 1-49)
- verify-cross r2: `.claude/phases/phase-2a/verify-cross.md` (lines 50+)

---

## Known issues / debt

| Issue | Severity | Plan |
|-------|----------|------|
| `bg_image_path` absolute path | Low | Phase 3 (viewer relative path) |
| `translations.block_id` lone PK | Low | Phase 6 migration |
| `src_pdf_sha256` not in Document | Low | Phase 3 (if dedup needed) |
| `ht-lens db migrate` not implemented | Negligible | Alembic CLI is equivalent |
| CI not verified (not pushed) | Process | Human push triggers GH Actions |

---

## Recommended next (Phase 2b)

1. `OpenAICompatibleClient` implementing `LLMClient` (sglang endpoint)
2. Translation pipeline: `translate_document(doc_id, session, llm)` using `MockLLMClient` → then real
3. `enable_thinking=false` via `chat_template_kwargs` (confirmed working in Phase 0)
