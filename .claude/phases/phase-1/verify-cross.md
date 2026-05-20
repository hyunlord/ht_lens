## 1. Verification of automated checks

Lint/format/type evidence in `.claude/phases/phase-1/verify.md:17-19` is plausible but not independently proven: it is only summarized terminal output, with no saved log. The commands match CI config in `.github/workflows/ci.yml:27-37`.

Test evidence is plausible but thin. The suite does include the claimed new coverage points: subprocess `python -m ht_lens.extract` tests in `tests/integration/test_module_cli.py:20-47` and close-on-exception in `tests/integration/test_fitz_lifecycle.py:20-28`. However, there is no persisted pytest log, and the `ht-lens extract` console script itself is not tested as an installed script; `tests/integration/test_cli_errors.py:15-16` only calls `main(["extract", ...])`.

Coverage evidence is internally inconsistent. The current `.coverage` report shows TOTAL 92%, but `src/ht_lens/extract/__main__.py` is still 0% covered, not 60% as claimed in `.claude/phases/phase-1/verify.md:38`. That is expected because `pyproject.toml:51-62` has no subprocess coverage configuration, so subprocess CLI tests prove behavior but do not contribute to coverage.

CI is not verified. `.claude/phases/phase-1/verify.md:22` says “green expected,” which is not evidence. The workflow exists and runs the right checks, but no green run is shown.

The dependency and fitz-isolation checks are mostly credible for source code: `src/ht_lens/extract/_fitz.py:16` is the only source `fitz` import, and `pyproject.toml:12-14` has the Phase 1 extract dependencies. The dead `save_images` API is gone from current source, but the plan still mentions it at `.claude/phases/phase-1/plan.md:126-139`.

## 2. Verification of functional checks

The module CLI deliverable from `ROADMAP.md:78-82` is now functionally exercised: `tests/integration/test_module_cli.py:20-33` invokes `python -m ht_lens.extract` successfully, and `tests/integration/test_module_cli.py:35-47` covers exit 2 on an existing output directory.

The `ht-lens extract` claim is weaker. `.claude/phases/phase-1/verify.md:57` equates single-process `main()` calls with the console entry point. That tests Typer routing and error mapping, but not the installed script declared in `pyproject.toml:28-29`.

The three sample PDFs are exercised through the pipeline for metadata, PNG/JSON pairing, schema, render scale, and snapshots in `tests/integration/test_extract_pipeline.py:26-150` and `tests/integration/test_extract_snapshot.py:25-33`. The human-review artifact exists at `docs/phases/phase-1/samples.md`, but automated “reasonable block JSON” checks remain narrow.

Reading-order verification does not really exercise the ROADMAP risk. The only real-fixture assertions are two checks on `sample_en.pdf` page 1 in `tests/integration/test_real_reading_order.py:28-56`. There is no Korean reading-order assertion, no mixed-document assertion, and no real multi-column fixture assertion.

The rotated-page check is accurately caveated in the verify report, but its name overclaims. `tests/integration/test_rotated_page.py:29-36` verifies rotation metadata and PNG dimensions, not that text bboxes map to rotated pixels.

## 3. Score audit

독창성 / 15: `12 / 15` is justified. `_fitz.py` isolation and per-page render metadata are useful, while `src/ht_lens/extract/reading_order.py:34-53` is intentionally simple. I would confirm 12/15.

완결성 / 35: `31 / 35` is high. The minimal DoD is mostly covered, but CI is unverified, installed `ht-lens` is not subprocess-tested, current coverage contradicts the `__main__.py` claim, and the phase plan still promises 1-3 column detection at `.claude/phases/phase-1/plan.md:13` while actual code does not implement it. Suggested: 28/35.

안정성 / 30: `28 / 30` is optimistic. Error tests cover several paths, but corrupted/encrypted inputs create output directories before failing because `extract_pdf()` creates `pages/` and `images/` before `open_pdf()` at `src/ht_lens/extract/pipeline.py:126-135`; tests only assert exit code in `tests/integration/test_cli_errors.py:68-81`. The coverage report also leaves `__main__.py` and fallback branches unmeasured. Suggested: 26/30.

확장성 / 20: `18 / 20` is generous. The schema helps Phase 4, but rotation bbox mapping is delegated, reading-order is not column-aware, and `_MIXED_RATIO = 0.20` is explicitly fixture-tuned in `src/ht_lens/extract/language.py:18-19` despite the plan saying 30% at `.claude/phases/phase-1/plan.md:117-120`. Suggested: 16/20.

Fair score: 84/100.

## 4. Issues missed

The coverage claim for `__main__.py` is wrong. Subprocess tests validate behavior, but without subprocess coverage support, the current coverage report still shows `src/ht_lens/extract/__main__.py` at 0%. This should be corrected in verify rather than presented as 60%.

The phase plan is stale relative to implementation. It still lists “Reading order (1~3컬럼 자동 감지)” and x-clustering in `.claude/phases/phase-1/plan.md:13` and `.claude/phases/phase-1/plan.md:96-103`, but `src/ht_lens/extract/reading_order.py:42-53` only separates page-spanning blocks and sorts the rest by `(y, x)`.

The reading-order unit test is weaker than its name. `tests/unit/test_reading_order.py:23-35` expects left-column then right-column output, but the fixture is constructed with y-values that make a plain `(y, x)` sort pass. It does not prove actual column grouping.

Failure cleanup is under-specified. For encrypted/corrupted PDFs, `extract_pdf()` creates output directories before parsing at `src/ht_lens/extract/pipeline.py:126-135`; a failed run can leave a non-empty output dir that blocks retry without `--overwrite`. Existing tests do not assert output cleanliness.

Vertical text is still semantically loose. The arXiv side stamp is classified as `header` in `docs/phases/phase-1/samples.md:16`; `group_page()` ignores `RawLine.direction` even though `_fitz.py` exposes it at `src/ht_lens/extract/_fitz.py:126-133`.

## 5. Verdict

**DOWNGRADE** — The implementation appears broadly sufficient for a Phase 1 extractor, and the v3 report honestly lowered its own score. But the automated evidence has a concrete contradiction around `__main__.py` coverage, CI is still unverified, the installed console command is not truly exercised, and reading-order proof remains much narrower than the plan implies. I would score this around 84/100: not a full reject, but not strong enough to accept the 89 without targeted corrections or a clearer “known limitations” update to the plan/verify artifacts.