## 1. Verification of automated checks

`verify.md` is not stale. Current HEAD is `61bd5ec`, which only updates `.claude/phases/phase-8a/verify.md`; the last code/test commit is `e7720f5`, matching `verify.md:3`. `git status --short` shows only untracked `.claude/phases/phase-8a/summary.md`, so no code changed after verification.

Lint/format/type/test evidence is plausible but I could not independently rerun even targeted pytest because this invocation is read-only and `uv` failed creating a cache temp file under `/home/hyunlord/.cache/uv`. I therefore audited the committed tests and code instead.

Coverage remains unchanged since Round 1: `verify.md:15` marks it n/a, but `WORKFLOW.md:140-145` includes coverage in the automated checks and `pyproject.toml:69-72` enables `--cov=ht_lens` by default. Treat this as a policy deviation, not fresh evidence of failure.

CI is still not evidence. `verify.md:16` says “pending push”; it cannot support the self-verification score.

## 2. Verification of functional checks

The R1 critical functional gaps are materially addressed. Same-filename 1.x/MinerU coexistence is now enforced by `Document.filename == filename` plus `Document.extractor == "mineru"` in `src/ht_lens/ingest_mineru/pipeline.py:89-96`, and tested with overwrite in `tests/integration/test_mineru_ingest.py:228-293`. The malformed `text_level` path now raises `ContentListError` at `src/ht_lens/ingest_mineru/content_list.py:129-135`, with a direct test at `tests/unit/test_content_list_parser.py:125-129`.

Runner discovery and most subprocess branches now have tests: env/PATH/missing binary, glob discovery, nonzero exit, success-without-output, CPU env, and missing PDF are covered in `tests/integration/test_mineru_runner.py:27-150`. The self-report is honest that `TimeoutExpired` remains untested.

The remaining functional gap is unchanged since Round 1 for the extraction CLI half: `extract-mineru` is implemented in `src/ht_lens/cli.py:248-284`, but `rg` finds no `extract-mineru` tests under `tests/`. `tests/integration/test_cli_mineru.py:1-76` only drives `ingest-mineru`. The lower-level `run_mineru` tests reduce risk, but they do not verify Typer argument wiring, output text, or CLI exit-code mapping for extraction.

The doc7 live E2E remains external evidence only: `doc_id=1 chunks=103 images=30` is plausible, but not reproducible from committed fixtures. The fixture-based parser/ingest tests are the reproducible DoD evidence.

## 3. Score audit

독창성 / 15: `12/15` is justified. The subprocess boundary, parser normalization, and extractor-scoped coexistence are appropriate rather than novel. No deduction.

완결성 / 35: `33/35` is slightly high. DoD coverage is now strong, including same-filename coexistence, image copy, chunk preservation, additive migration, and ingest CLI. Deduct for unreproducible doc7 E2E and missing `extract-mineru` CLI test. Suggested: `31/35`.

안정성 / 30: `28/30` is also a little high. R1 safety issues were fixed, but coverage/CI are not verified, `TimeoutExpired` is explicitly untested, and extraction CLI error mapping is untested. Suggested: `26/30`.

확장성 / 20: `17/20` is fair. `extractor` scoping makes coexistence viable, and deferring pages is consistent with current non-null model constraints. Absolute `img_path` and basename-only image copy in `src/ht_lens/ingest_mineru/pipeline.py:154-170` remain future portability/collision risks, but they are known and not Phase 8a blockers. Confirm `17/20`.

Fair total: `86/100`.

## 4. Issues missed (new this round)

No major new regression from RE-CODE is visible. The main R1 rejection issue was fixed rather than reframed: the lookup is now extractor-scoped, and `test_same_filename_1x_and_mineru_coexist` explicitly covers both coexistence and overwrite.

Newly visible from the RE-CODE tests: the new `test_cli_mineru.py` locks only `ingest-mineru`; it does not cover `extract-mineru` despite `extract_mineru_command` being a new CLI handler at `src/ht_lens/cli.py:248-284`. This is a partial unresolved R1 CLI gap, not a reason to reject by itself because `run_mineru` has lower-level coverage.

The overwrite test does not assert filesystem cleanup for the replaced MinerU document. `ingest_mineru_output` deletes old `Chunk` and `Document` rows at `src/ht_lens/ingest_mineru/pipeline.py:101-107`, then writes a new managed image directory under the new document id at `pipeline.py:121-126`. Old managed image directories can be orphaned. This does not violate the Phase 8a DB-preservation DoD, but it should be noted before repeated re-ingests become common.

The timeout path is surfaced by self-verify, so I am not counting it as missed. It remains an explicit residual risk in `src/ht_lens/extract_mineru/runner.py:124-125`.

## 5. Verdict

**DOWNGRADE** — R1’s concrete blockers are fixed and tested well enough that I do not recommend another RE-CODE. The self-score is still optimistic because coverage and CI are not verified, the real doc7 evidence is external, and `extract-mineru` CLI wiring remains untested. A fair score is about `86/100`; pass should depend on Planner tolerance for those residual Phase 8a risks rather than another automated repair loop.
