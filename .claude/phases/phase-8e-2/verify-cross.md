## 1. Verification of automated checks

The evidence is partly credible but incomplete. `verify.md` was committed at HEAD `8a282ad` after the only code/test commit `3fda1a8`, and `git diff 3fda1a8..HEAD` shows only phase artifacts, so the self-verify is not stale for code. Current untracked `.claude/phases/phase-8e-2/verify-cross.md` is only the generated placeholder, not a prior round.

Their 5-A table omits the required format check: `uv run ruff format --check .` is in `WORKFLOW.md` but absent from `verify.md:5-14`. Coverage is also not reported as a distinct result, despite the required lint/format/type/test/coverage/CI set.

The lint/type/test evidence is plausible and matches the repo delta: `src/ht_lens/cli.py:268-284` adds `--timeout`, and `tests/integration/test_cli_mineru.py:166-190` adds one locking test. CI is honestly marked N/A, but calling local 769 tests “CI-equivalent” in `verify.md:12` overstates it because CI environment, dependency cache, and workflow wiring are not exercised.

## 2. Verification of functional checks

The DB count claims are credible: current `data/ht_lens_v2.db` matches `verify.md:18-26` with 5 docs, 3839 chunks, 3830 translated, 9 failed, and 2840 embeddings. The 1.x rollback check also matches `verify.md:43-47`: prod DB has alembic `0004`, 49,850 blocks, and no v2 chunk tables.

The functional verification does not actually prove “reflow viewer에서 전체 읽기” from `ROADMAP.md:260-263`. `verify.md` provides counts and says failed rows are suppressed, but it does not show per-doc `/v2/documents/{id}/reflow` API 200 results, UI load evidence, page image/cache checks, or a realistic full-reading pass across the 518-page doc.

Literal Roadmap DoD says “7 docs 2.0 DB 완료” (`ROADMAP.md:254-262`), while this phase verifies a consciously reduced 5-doc scope (`challenge.md:12`, `manifest.md:14-25`). That may be an accepted Planner deviation, but it should be scored as a subphase completion, not full Phase 8e DoD completion.

The debate point about `--short-only` was handled reasonably: challenge moved it to verification-driven use (`challenge.md:7-9`), and verify records no need for doc2/3 (`verify.md:40-41`). Cross-doc RAG live was also explicitly moved to 8e-3 (`challenge.md:7`, `verify.md:37-38`), so I would not penalize that as an 8e-2 miss.

## 3. Score audit

독창성 / 15: 11 is mostly justified. This is operational migration, not new architecture, but the manifest, go/no-go, and retry-drain practice are useful. I would keep 10-11/15; the timeout fix is simple and only partially solves the real timeout blocker.

완결성 / 35: 31 is too high against the literal DoD. The 5-doc DB is real, but `ROADMAP.md:261` still says 7 docs, book2 full is deferred (`verify.md:75`), and reflow reading is asserted without per-doc viewer/API evidence. Fair score: 27-29/35.

안정성 / 30: 28 is high. The test suite evidence is good, and failed translations are fail-preserved via `get_reflow` status gating (`src/ht_lens/api/routers/reflow.py:109-112`, tested at `tests/integration/test_reflow_api.py:82-93`). But the actual large-doc run required out-of-band env tuning and qwen concurrency reduction (`verify.md:54-56`), and format/CI were not run. Fair score: 25-26/30.

확장성 / 20: 18 is optimistic. `extract-mineru --timeout` only threads `timeout_s` to `subprocess.run` (`src/ht_lens/extract_mineru/runner.py:116-122`); the reported blocker was MinerU’s internal `MINERU_TASK_RESULT_TIMEOUT_SECONDS` (`manifest.md:23`), which is not modeled by the CLI option or test. Fair score: 15-16/20.

## 4. Issues missed (new this round)

The new `--timeout` path does not fully encode the real large-PDF requirement. `src/ht_lens/cli.py:268-284` passes `timeout_s` to `run_mineru`, but `run_mineru` only applies it to Python’s parent `subprocess.run` timeout (`runner.py:116-125`). The successful Aggarwal extraction also required `MINERU_TASK_RESULT_TIMEOUT_SECONDS=14400` inside MinerU (`verify.md:56`, `manifest.md:23`), so `extract-mineru --timeout 14400` alone can still fail at MinerU’s internal 3600s limit.

The new test locks only kwarg threading, not the real process environment behavior. `tests/integration/test_cli_mineru.py:166-190` mocks `run_mineru`, so it cannot catch the internal timeout gap above, nor does it assert any environment propagation or documented command recipe for large PDFs.

The accepted challenge item “translated text chunk ≥ 임계(doc 규모 대비)” was not actually evidenced. `challenge.md:20-22` promised stronger text/embedding eligibility thresholds, but `verify.md:18-38` reports only total chunks/translations/embeddings. A 518-page doc with 3338 chunks and 2543 embeddings is probably healthy, but the promised threshold check is absent.

The manifest’s source traceability is only partial. `manifest.md:6-12` stores 16-character SHA prefixes, and doc1 has no SHA at all; the live DB has `src_pdf_sha256` nullable and all five rows are NULL. That matches the deliberate “in-DB sha 미주장” decision, but it weakens cutover auditability and should weigh against completeness/rollback confidence.

## 5. Verdict

**DOWNGRADE** — The self-report is mostly honest and the migrated DB evidence is real, but the score should be lower than 88 because required automated checks are incomplete, reflow “전체 읽기” is asserted rather than demonstrated, the phase only satisfies a reduced 5-doc interpretation of a 7-doc Roadmap DoD, and the new timeout flag does not cover the MinerU internal timeout that actually blocked Aggarwal. A fair score is about **80-82**: no RE-CODE is mandatory for the batch data itself, but 8e-3 should not rely on `--timeout` alone for large PDFs and should provide explicit reflow/load evidence before cutover.
