## 1. Verification of automated checks

- Lint/format/type/test evidence in `.claude/phases/phase-1/verify.md:7-10` is plausible and specific enough, but it is only copied summary output, not an attached log. I see matching config for ruff/mypy/pytest in `pyproject.toml:38-62`.
- Coverage evidence is credible because pytest has `--cov=ht_lens --cov-report=term-missing` in `pyproject.toml:51-53`, but verify lists “(pytest --cov)” rather than the exact command and there is no coverage threshold/fail-under.
- CI is not verified. `.claude/phases/phase-1/verify.md:12` says “green expected,” while workflow requires GitHub Actions green. `.github/workflows/ci.yml:27-37` runs the right commands, but expectation is not evidence.
- Dependency evidence is incomplete. The grep in `.claude/phases/phase-1/verify.md:13` proves the three expected PDF deps exist, not that no extra extractor dependency leaked in. The actual dependency list includes existing `pydantic`, `pydantic-settings`, `structlog`, and `typer` in `pyproject.toml:7-15`; that may be Phase 0 carryover, but the verification method is weak.
- Missing automated check: no test asserts `--save-images` behavior, even though CLI advertises it in `src/ht_lens/cli.py:45-46`.

## 2. Verification of functional checks

The functional checks exercise the happy-path CLI over three fixtures and several synthetic errors, which covers much of Phase 1. `tests/integration/test_extract_pipeline.py:26-150` checks fixture existence, metadata, JSON/PNG pairing, schema, render scale, and PNG dimensions. `tests/integration/test_cli_errors.py:40-94` covers overwrite, encrypted, corrupted, and image-only PDFs.

The weak point is the DoD phrase “block JSON이 사람이 봐도 합리적.” The human-review artifact itself shows questionable reading order: `docs/phases/phase-1/samples.md:12-20` orders a vertical arXiv margin header, then “1 Introduction,” then a side text fragment, then the document title/abstract. That directly contradicts `.claude/phases/phase-1/verify.md:89`, which calls `sample_en.pdf` page 1 natural.

The rotated-page claim is overstated. `tests/integration/test_rotated_page.py:23-36` checks `rotation=90` and PNG dimensions, but not whether any text bbox maps correctly onto the rotated render. The test name and verify wording say “bbox matches,” but the assertions do not inspect bbox coordinates.

## 3. Score audit

- 독창성 / 15: 13 is too generous. `_fitz.py` isolation and the fallback ordering are reasonable, but the custom ordering is not proven on real problematic pages, and `save_images` is an advertised no-op. Suggested: 12/15.
- 완결성 / 35: 34 is not justified. CI is not green, `--save-images` is unimplemented despite being in the plan at `.claude/phases/phase-1/plan.md:126-140`, and the sample artifact shows non-natural order on a canonical fixture. Suggested: 30/35.
- 안정성 / 30: 29 is too high. Error-path coverage is decent, but coverage excludes meaningful CLI-module invocation assertions, no `--save-images` test exists, and rotated bbox semantics are not actually validated. Suggested: 27/30.
- 확장성 / 20: 20 is not justified. Per-page render metadata helps Phase 4, but the rotation contract still pushes hard work to the viewer, and `ExtractResult` only returns counts/lang/out_dir, not generated manifest paths. Suggested: 19/20.

Fair score: 88/100.

## 4. Issues missed

- `save_images` is dead API surface. `extract_pdf(..., save_images=False)` accepts the parameter in `src/ht_lens/extract/pipeline.py:115-122`, the CLI exposes it in `src/ht_lens/cli.py:45-46`, but `rg` shows no implementation beyond passing the flag. This should be removed or implemented.
- The human-review test writes into the repository during pytest: `tests/integration/test_human_review.py:35-42` creates/overwrites `docs/phases/phase-1/samples.md`. Even if deterministic, a test with tracked-file side effects is fragile and can mask stale docs.
- Reading-order tests are synthetic only. `tests/unit/test_reading_order.py:23-60` covers crafted blocks, but there is no assertion against expected ordering in the real fixtures. Snapshot tests can freeze bad ordering rather than prove it is reasonable.
- Header classification is loose. `src/ht_lens/extract/blocks.py:106-114` treats any short large-font paragraph as `header`; the sample shows several chart/table fragments and document metadata as headers in `docs/phases/phase-1/samples.md:12-21`.
- The language threshold changed from the plan’s 30% to 20% in `src/ht_lens/extract/language.py:18-19`, tuned to the fixture. That may be acceptable, but verify did not call out the deviation.

## 5. Verdict

**DOWNGRADE** — The implementation is broadly functional and has more test coverage than a minimal Phase 1 would require, but the self-score overstates the evidence. CI is not actually green, a documented CLI option is unimplemented, rotated bbox verification is weaker than claimed, and the generated human-review artifact shows at least one canonical fixture with visibly questionable reading order. I would score this around 88/100 and recommend targeted re-code before treating it as a ≥95 pass candidate.