## 1. Verification of automated checks

The lint/format/type/test/coverage rows in `.claude/phases/phase-1/verify.md:16-22` are plausible, but not fully credible for current `HEAD`: the recent log shows `8debd30 fix(phase-1): drop spanning-header lift + plan cleanup` landed after `0b0e7c6 chore(phase-1): verify (v4 final)` and changed source, tests, snapshots, and samples. There is no updated `verify.md` proving `uv run ruff`, `mypy`, `pytest`, or coverage were rerun after that code change.

CI is explicitly not verified. `.claude/phases/phase-1/verify.md:23` says “green expected,” while `WORKFLOW.md:130-137` requires GitHub Actions green and `.github/workflows/ci.yml:27-37` defines the actual job. This should remain unknown, not pass.

Coverage is useful but weakly gated. `pyproject.toml:51-62` enables coverage and branch coverage, but no `fail_under` threshold exists, so 92% is informational. The `__main__.py` 0% caveat is acceptable because subprocess tests exist.

The dependency row is only partially evidenced. New PDF deps are `pymupdf`, `pillow`, `langdetect` in `pyproject.toml:12-14`, but extractor runtime also imports Pydantic in `src/ht_lens/extract/models.py:11`. Because Pydantic was Phase 0 baseline, this is not necessarily a DoD violation, but the self-report’s “extract deps = …” wording is too clean.

Fitz isolation and dead API checks are credible for source: only `_fitz.py` imports `fitz`, and `save_images` is gone from source. CLI/lifecycle cleanup checks are covered by tests, but the `ht-lens` console script test can skip when `.venv/bin/ht-lens` is absent (`tests/integration/test_module_cli.py:51-58`).

## 2. Verification of functional checks

The pipeline is exercised on all three fixtures via in-process extraction and snapshots (`tests/integration/test_extract_pipeline.py:33-150`, `tests/integration/test_extract_snapshot.py:25-33`). The documented CLI path is only subprocess-tested on `sample_en.pdf` (`tests/integration/test_module_cli.py:20-33`), while `WORKFLOW.md:141-144` asks Phase 1 CLI verification with 3 sample PDFs. Korean and mixed fixtures should also be run through `python -m ht_lens.extract`, not just `extract_pdf()`.

The human-review DoD is only weakly automated. `docs/phases/phase-1/samples.md` exists, and the prior Korean page-5 ordering regression appears fixed (`docs/phases/phase-1/samples.md:296-312`). But `tests/integration/test_human_review.py:18-39` checks dump formatting for `sample_en.pdf` only, and `test_committed_samples_md_is_non_empty` only checks headings (`tests/integration/test_human_review.py:42-51`). It does not prove the committed dump matches current output or that all three samples are “human-reasonable.”

Some remaining output is acceptable for Phase 1 but should not be oversold. English page 1 graph/table-like content is highly fragmented (`docs/phases/phase-1/samples.md:20-47`), and Korean page 40 table rows are serialized as mixed cell text rather than meaningful table structure (`docs/phases/phase-1/samples.md:954-980`). That aligns with table/caption deferral, but limits the functional claim.

Rotation coverage is narrower than the test name says: `tests/integration/test_rotated_page.py:23-36` verifies rotation metadata and PNG orientation, not bbox-to-pixel overlay correctness.

## 3. Score audit

독창성 / 15: 12/15 is justified. `_fitz.py` isolation, raw line direction, render metadata, and minimal reading-order fallback are appropriate. No extra deduction.

완결성 / 35: 30/35 is too high. The current self-verify predates the latest source change, CI is unverified, only the English fixture uses the documented subprocess CLI, and the human-review artifact is not freshness-checked. Suggested: 27/35.

안정성 / 30: 27/30 is optimistic. Error handling is much better (`tests/integration/test_cli_errors.py:40-99`, `tests/integration/test_fitz_lifecycle.py:20-28`), but the current automated evidence is stale, the console-script test is environment-sensitive, and realistic rotated bbox/error-after-partial-output paths remain untested. Suggested: 25/30.

확장성 / 20: 17/20 is slightly high. The schema helps Phase 4, but `order_blocks()` is now intentionally just PyMuPDF order plus `(y0, x0)` fallback (`src/ht_lens/extract/reading_order.py:34-42`), mixed-language detection is fixture-tuned (`src/ht_lens/extract/language.py:18-19`), and `src/ht_lens/extract/__init__.py` does not expose the public API described in `.claude/phases/phase-1/plan.md:197`. Suggested: 16/20.

Fair score: 80/100.

## 4. Issues missed

The biggest process miss is stale verification. A source-changing commit after the final self-verify invalidates the automated-check evidence unless the commands were rerun and recorded. That should be surfaced directly in `verify.md`.

The plan still contradicts current implementation. `.claude/phases/phase-1/plan.md:97-99` describes a spanning-header lift, but `src/ht_lens/extract/reading_order.py:9-13` says that heuristic was removed. `.claude/phases/phase-1/plan.md:137` still mentions image extraction under `save_images=True`, even though the API was removed.

The reading-order tests do not cover realistic equal-y two-column ordering. `tests/unit/test_reading_order.py:23-35` makes plain `(y0, x0)` sorting produce the desired left-column-first result because right-column y-values are lower; row-aligned columns would interleave.

Header classification remains semantically loose. `Abstract` and `1 Introduction` are `text`, not `header`, in `docs/phases/phase-1/samples.md:15-18`. That may be acceptable for Phase 1, but it weakens future block-type assumptions.

The committed `samples.md` can go stale silently. The generator writes the real artifact (`scripts/dump_samples.py:45-53`), but tests do not compare committed content to freshly generated output for all three fixtures.

## 5. Verdict

**DOWNGRADE** — The implementation appears broadly usable for the Phase 1 “80%” target, and several prior critique points were addressed, but the self-assessment is not fully credible for current `HEAD` because source changed after the final self-verify and CI is still only “expected.” A fair score is about 80/100 pending a fresh verify run, subprocess CLI checks for all three fixtures, and cleanup of stale plan claims.