## 1. Verification of automated checks
Lint/format/type/test evidence is mostly credible for current HEAD: `git rev-parse --short HEAD` is `8a355bd`, the verify commit, and the last Phase 8a code/test commits are `f823259` and `bf241e6`. No later code commit makes `verify.md` stale. Current untracked files are phase workflow artifacts only.

Coverage evidence is not credible as stated. `pyproject.toml:69-72` configures pytest with `--cov=ht_lens`, but verify used `--no-cov` and then marked coverage n/a. That may be a policy choice, but it is not the Stage 5 automated check in `WORKFLOW.md:143-145`, where coverage is included in pytest.

CI is not verified. `verify.md` says pending push, so it should not be treated as evidence.

They also should have run or reported targeted CLI/runner tests for the two new Typer commands and subprocess wrapper. The self-report acknowledges this gap, but the 5-D table overstates `resolve_mineru_bin` / runner as “locked” by one smoke run.

## 2. Verification of functional checks
The parser and ingest functional checks cover much of the DoD: structure preservation is tested in `tests/integration/test_mineru_ingest.py:77-105`, image copy in `tests/integration/test_mineru_ingest.py:110-138`, rollback on missing image in `tests/integration/test_mineru_ingest.py:143-168`, and no invalid `Page` rows in `tests/integration/test_mineru_ingest.py:173-192`.

The doc 7 E2E evidence is plausible but not independently reproducible from committed artifacts. `verify.md` reports `doc_id=1 chunks=103 images=30`, but there is no command transcript, fixture, or checked-in output for the real 990-1000 content list.

The main functional gap is “1.x DB 무손상 (병행)” under filename collision. `ingest_mineru_output` looks up existing documents by `Document.filename` only, then blocks or deletes them on overwrite (`src/ht_lens/ingest_mineru/pipeline.py:83-95`). The preservation test uses `legacy.pdf` and `mineru.pdf` as different filenames (`tests/integration/test_mineru_ingest.py:232-294`), so it does not exercise the realistic parallel case where the MinerU re-ingest uses the same PDF filename as an existing 1.x document.

CLI behavior is also not functionally verified. The new commands are in `src/ht_lens/cli.py:248-369`, but `rg` finds no `extract-mineru` / `ingest-mineru` tests under `tests/`.

## 3. Score audit
독창성 / 15: `12/15` is broadly justified. The implementation kept MinerU external, added a typed parser boundary, and deferred chunk translation/embedding tables after debate. No major deduction beyond maybe 1 point for filename-based coupling in the “parallel” design.

완결성 / 35: `31/35` is too generous. The happy-path DoD is substantially covered, but CLI commands are untested, the real doc7 E2E evidence is external to the repo, and same-filename parallel ingest is untested and currently unsafe. Suggested score: `27/35`.

안정성 / 30: `27/30` is too high. Runner subprocess failure branches are untested despite being a debate item; CLI error mapping is untested; `parse_content_list` can still raise raw `ValueError` on invalid `text_level` at `src/ht_lens/ingest_mineru/content_list.py:128-132`; and overwrite can target legacy documents by filename. Suggested score: `23/30`.

확장성 / 20: `18/20` is too high. `chunks.page_idx` without `Page` FK is a good 8a choice, but filename uniqueness across extractor generations blocks clean Phase 8e coexistence, and absolute managed `img_path` values (`src/ht_lens/ingest_mineru/pipeline.py:109-158`) may make future DB portability harder. Suggested score: `15/20`.

Fair total: about `77-80/100`, not `88`.

## 4. Issues missed (new this round)
The biggest missed issue is same-filename collision with 1.x documents. `ingest_mineru_output` selects by filename only (`src/ht_lens/ingest_mineru/pipeline.py:83-85`). With `overwrite=False`, a MinerU v2 ingest of an already-ingested PDF is blocked even though `Document.extractor` was added to allow parallel pipelines. With `overwrite=True`, it attempts to bulk-delete the existing `Document` (`src/ht_lens/ingest_mineru/pipeline.py:90-95`), which can either fail on legacy `pages` FKs or risk deleting non-MinerU rows. This directly weakens the “1.x DB 무손상 (병행)” DoD.

The preservation test does not cover that scenario. `test_1x_data_untouched_by_mineru_ingest` deliberately avoids collision by seeding `legacy.pdf` and ingesting `mineru.pdf` (`tests/integration/test_mineru_ingest.py:232-294`). Add a test where an existing `extractor='pymupdf'` document has the same filename as the MinerU ingest, and define the expected behavior explicitly.

The accepted debate requirement “runner 경로 discovery(가짜 출력 트리)” from `.claude/phases/phase-8a/challenge.md` was not implemented as a test. `src/ht_lens/extract_mineru/runner.py:42-133` has real logic for env/PATH resolution, timeout, nonzero exit, and glob discovery, but no tests reference `run_mineru`, `resolve_mineru_bin`, or `_discover_outputs`.

Invalid `text_level` is not normalized into the parser’s domain error. `page_idx` has explicit `ContentListError` handling (`src/ht_lens/ingest_mineru/content_list.py:80-87`), but heading level uses `int(level)` directly (`src/ht_lens/ingest_mineru/content_list.py:128-132`). A malformed MinerU item can escape as raw `ValueError`, bypassing the `ContentListError` wrapping in `src/ht_lens/ingest_mineru/pipeline.py:74-77`.

## 5. Verdict
**REJECT** — The implementation is close on the core happy path, and the self-verifier was honest about several gaps, but the same-filename overwrite/collision behavior is a concrete threat to the Phase 8a parallel-DB/1.x-preservation DoD. Before this phase passes, RE-CODE should lock the intended coexistence policy by `extractor` and add targeted tests for same-filename legacy documents plus runner discovery/failure branches.
