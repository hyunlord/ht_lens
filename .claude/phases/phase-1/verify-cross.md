## 1. Verification of automated checks

Lint/format/type/test evidence in `.claude/phases/phase-1/verify.md:18-22` is plausible but only summarized, not backed by saved logs. The commands match the workflow requirements in `WORKFLOW.md:130-137` and CI job in `.github/workflows/ci.yml:27-37`.

Coverage evidence is credible as reported, but weakly gated. `pyproject.toml:51-62` enables pytest-cov and branch coverage, but there is no fail-under threshold; “92% line / 91% branch” is informational unless the phase target is defined elsewhere.

CI is not verified. `.claude/phases/phase-1/verify.md:23` says “green expected,” which is explicitly not evidence for the required GitHub Actions green check in `WORKFLOW.md:137`.

Dependency and fitz-isolation checks are mostly credible for source: extract deps are `pymupdf`, `pillow`, `langdetect` in `pyproject.toml:12-14`, and the only source `fitz` import is `src/ht_lens/extract/_fitz.py:16`. Test-only `fitz` imports are acceptable.

The console-script evidence is environment-sensitive. `tests/integration/test_module_cli.py:51-68` does invoke `.venv/bin/ht-lens`, but skips if that exact path is absent at `tests/integration/test_module_cli.py:53-58`; the self-report should note that this check depends on the local uv venv layout.

## 2. Verification of functional checks

The core `python -m ht_lens.extract` path is exercised, but only on `sample_en.pdf` in subprocess form (`tests/integration/test_module_cli.py:20-33`). The three-sample coverage is through in-process pipeline and snapshots (`tests/integration/test_extract_pipeline.py:33-150`, `tests/integration/test_extract_snapshot.py:25-33`), which is useful but not the same as running the documented CLI on all realistic inputs.

The DoD item “3종 sample PDF 모두 block JSON이 사람이 봐도 합리적” is not convincingly satisfied. `docs/phases/phase-1/samples.md` exists, but `tests/integration/test_human_review.py:18-39` only checks that the dump format contains every block; it does not validate that the order is reasonable.

The committed dump actually exposes reading-order problems. In `sample_ko.pdf` page 5, blocks at y=205/548/674 appear before top-of-page content at y=37/45/113 (`docs/phases/phase-1/samples.md:300-306`). Similar reversals appear on pages 6-8 (`docs/phases/phase-1/samples.md:318-329`, `docs/phases/phase-1/samples.md:335-344`, `docs/phases/phase-1/samples.md:350-360`).

Reading-order tests are too narrow for the ROADMAP risk at `ROADMAP.md:89-92`. The only real-fixture assertions inspect `sample_en.pdf` page 1 (`tests/integration/test_real_reading_order.py:20-56`), not Korean pages or pages with image/sidebar layouts where the current output is visibly non-monotonic.

Rotation checks are honestly caveated in the self-report: `tests/integration/test_rotated_page.py:23-36` verifies metadata and PNG orientation, not bbox-to-rendered-pixel alignment.

## 3. Score audit

독창성 / 15: 12/15 is defensible. `_fitz.py` isolation, line direction propagation, render metadata, and simple fallback are reasonable Phase 1 choices. No further deduction beyond the self-assessed limits.

완결성 / 35: 30/35 is too high. One of the three explicit DoD items is only partially met because the human-review artifact contains obvious Korean reading-order regressions. CI is also unverified, and CLI testing across all three samples is in-process rather than via the promised command. Suggested: 22/35.

안정성 / 30: 27/30 is optimistic. Error paths are much improved (`tests/integration/test_cli_errors.py:40-99`, `tests/integration/test_fitz_lifecycle.py:20-28`), but the test suite snapshots flawed output and lacks assertions for real fixture ordering beyond one English page. Suggested: 23/30.

확장성 / 20: 17/20 is too generous. Phase 2/4 depend on reliable block order and overlay metadata; `src/ht_lens/extract/reading_order.py:42-53` treats any block wider than 70% of page width as “spanning,” not just headers, which is already misordering Korean pages. The language threshold is also fixture-tuned at `src/ht_lens/extract/language.py:18-19`. Suggested: 13/20.

Fair score: 70/100.

## 4. Issues missed

The reading-order fallback is the main missed defect. `order_blocks()` splits blocks solely by width (`src/ht_lens/extract/reading_order.py:42-53`), so wide body paragraphs are lifted ahead of narrower top-of-page content, images, captions, and sidebars. This directly explains the bad `sample_ko.pdf` ordering in `docs/phases/phase-1/samples.md:300-312`.

The unit test named `test_two_columns_with_y_regression_resorted_left_then_right` does not prove column-aware ordering. Its fixture y-values make a plain `(y0, x0)` sort produce the expected left-column-first result (`tests/unit/test_reading_order.py:23-35`), so it does not protect the intended semantic behavior.

The plan remains stale despite the self-report claiming plan staleness was addressed. It still lists 1-3 column detection and image saving as in-scope (`.claude/phases/phase-1/plan.md:13-14`), and still documents `save_images` in the pipeline/CLI sections (`.claude/phases/phase-1/plan.md:121-135`, `.claude/phases/phase-1/plan.md:174-178`) even though the implementation removed it.

The self-report frames remaining deductions as outside Phase 1 (`.claude/phases/phase-1/verify.md:129-137`), but the Korean ordering defect is inside the Phase 1 sample fixture DoD, not a Phase 6 stretch issue.

## 5. Verdict

**REJECT** — The implementation has solid infrastructure and many prior Codex findings were addressed, but the current self-verification misses a real defect in the committed sample output for `sample_ko.pdf`. Since Phase 1’s first DoD is that all three sample block JSON outputs are human-reasonable, visible page-order reversals in the human-review artifact should trigger RE-CODE: fix or narrow the reading-order fallback, add real Korean/page-with-image ordering assertions, then regenerate snapshots and `samples.md`.