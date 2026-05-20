## 1. Verification of automated checks

Lint, format, type, and test evidence in `.claude/phases/phase-1/verify.md:9-12` is plausible but thin: it reports only summarized terminal output, with no saved log. The commands match project config in `pyproject.toml:38-62`, so I do not see a contradiction.

Coverage is partly credible because pytest always runs with `--cov=ht_lens --cov-report=term-missing` via `pyproject.toml:51-53`. However, verify lists the command as only “(pytest --cov)” at `.claude/phases/phase-1/verify.md:13`, and there is no threshold or persisted artifact. The 0% coverage for `src/ht_lens/extract/__main__.py` in `.claude/phases/phase-1/verify.md:28` matters because the DoD deliverable is specifically `python -m ht_lens.extract`.

CI is not verified. `.claude/phases/phase-1/verify.md:14` says “green expected,” while `WORKFLOW.md` requires GitHub Actions green. `.github/workflows/ci.yml:27-37` runs the right local commands, but expected green is not evidence.

Dependency and fitz-isolation checks are directionally useful but not complete. The dependency grep in `.claude/phases/phase-1/verify.md:15` proves the three expected deps exist, not that extraction stayed limited to them. The fitz isolation check is credible for `src/`; `src/ht_lens/extract/_fitz.py:16` is the only source import. The dead-API check at `.claude/phases/phase-1/verify.md:17` uses a malformed path (`src/ ht_lens/`), but the conclusion is independently true: `save_images` is gone from current source.

## 2. Verification of functional checks

The functional tests cover a lot of Phase 1 behavior, but the self-report overstates the CLI evidence. The three-fixture integration tests call `extract_pdf()` directly in `tests/integration/test_extract_pipeline.py:33-51`, not `python -m ht_lens.extract` or the installed `ht-lens extract` command. CLI error tests call `main(["extract", ...])` through `tests/integration/test_cli_errors.py:15-16`, still not a real module/subprocess invocation. There is no success-path test for `src/ht_lens/extract/__main__.py:13-14`.

The 3 sample PDFs are actually exercised for metadata, JSON/PNG pairing, schema, render scale, and snapshot output in `tests/integration/test_extract_pipeline.py:26-150` and `tests/integration/test_extract_snapshot.py:25-33`. That supports the DoD better than the previous verify.

The “block JSON is human-reasonable” claim is only partially exercised. `docs/phases/phase-1/samples.md` exists and is useful, but automated real-fixture reading-order checks only assert two facts on `sample_en.pdf` page 1 in `tests/integration/test_real_reading_order.py:28-56`. They do not test Korean ordering, mixed-document ordering, figure/caption order, or any real multi-column page. The arXiv margin stamp is still classified as a `header` in `docs/phases/phase-1/samples.md:16`, so header over-classification is reduced, not eliminated.

The rotated-page check is weaker than named. `tests/integration/test_rotated_page.py:29-36` verifies `rotation=90` and PNG dimensions, but does not verify that text bboxes map onto the rotated render. The limitation is disclosed in `.claude/phases/phase-1/verify.md:60`, so this is not a blocker, but the test name/report wording overclaims.

## 3. Score audit

독창성 / 15: 13/15 is slightly high. `_fitz.py` isolation and the simplified reading-order fallback are pragmatic, but the fallback is still a narrow heuristic and the real-layout proof is thin. Suggested score: 12/15.

완결성 / 35: 33/35 is not justified. CI is not green, real module CLI invocation is untested despite being the stated deliverable, and “human-reasonable” block ordering is backed mostly by snapshots plus one English-page assertion. Suggested score: 30/35.

안정성 / 30: 29/30 is too high. Error scenarios are solid in `tests/integration/test_cli_errors.py:40-94`, but the promised close-on-exception coverage from `.claude/phases/phase-1/challenge.md` is absent, `src/ht_lens/extract/__main__.py` is uncovered, and CJK ToUnicode remains untested. Suggested score: 27/30.

확장성 / 20: 19/20 is a little generous. Render metadata helps Phase 4, but rotation bbox normalization is deferred to the viewer, and `src/ht_lens/extract/language.py:18-19` is explicitly tuned to the current mixed fixture. Suggested score: 18/20.

Fair score: 87/100.

## 4. Issues missed

`test_open_pdf_close_on_exception` was promised in `.claude/phases/phase-1/challenge.md`, but no such test exists; `rg` only finds `open_pdf` usage in source. `_fitz.is_closed()` exists at `src/ht_lens/extract/_fitz.py:83-84` but is unused by tests, so resource cleanup on caller exceptions is assumed rather than locked.

The reading-order fallback only triggers on vertical regressions: `src/ht_lens/extract/reading_order.py:23-40`. A two-column page emitted in monotonic row-major order would pass through unchanged, even if column-major reading order is desired. Current real-fixture tests do not cover that case.

Language detection deviates from the plan without much justification. The plan described 30% page disagreement for mixed detection, but the implementation uses `_MIXED_RATIO = 0.20` and comments that it is tuned on `sample_mixed` in `src/ht_lens/extract/language.py:18-19`. That is hidden fixture coupling.

The CLI deliverable is under-tested. `src/ht_lens/extract/__main__.py:13-14` is the user-facing `python -m ht_lens.extract` path, but the tests never invoke it. This is exactly the command named in ROADMAP Phase 1.

Header typing is semantically loose. `src/ht_lens/extract/blocks.py:108-113` relies on size, line count, and length, which still tags vertical arXiv metadata as `header` in `docs/phases/phase-1/samples.md:16`. That may be acceptable for Phase 1, but verify should not present header over-classification as solved.

## 5. Verdict

**DOWNGRADE** — The implementation is broadly functional and the RE-CODE addressed several prior defects, especially removing `save_images`, avoiding repo-writing tests, and adding real fixture checks. But the self-verification still overclaims: CI is not verified, the exact module CLI deliverable is untested, rotated bbox behavior is not actually validated, and real reading-order coverage is narrow. I would score this at about 87/100 and recommend targeted re-code before treating Phase 1 as pass-candidate quality.