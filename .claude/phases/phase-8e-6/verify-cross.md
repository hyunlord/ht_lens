## 1. Verification of automated checks

The v2 verify is not stale relative to code: `8ca80a7` is the verify commit after the RE-CODE commit `84732b3`, and no later committed source/test changes appear in the provided log. The code evidence is therefore current HEAD evidence, not the stale v1 report.

Lint/format/type/test evidence is plausible: the self-report lists `uv run ruff check src tests`, `uv run ruff format --check .`, `uv run mypy src/`, and `uv run pytest -q` with `847 passed, 8 skipped`. Coverage is also credible because `pyproject.toml:69-80` configures pytest with `--cov=ht_lens --cov-report=term-missing`; it is not a separate command, but it is included in the test command.

The “tracked tree clean” wording still falls short of `WORKFLOW.md`’s literal `git status` clean requirement. Current `git status --short` has untracked `.claude/phases/phase-8e-6/summary.md`, `.claude/scheduled_tasks.lock`, `.ipynb_checkpoints/`, and `logs/`. This does not make verify stale, but it is weaker process evidence than claimed.

CI is correctly marked pending push, so no issue there beyond the self-score needing to account for absent remote confirmation.

## 2. Verification of functional checks

Round 1 issue §4#1 is mostly fixed for detection/previews: `DegradedCandidate.order_idx` exists in `src/ht_lens/image_repair.py:117-124`, `detect_degraded_images()` now receives `(page_idx, order_idx, img_path, bbox)` at `src/ht_lens/image_repair.py:155-179`, and preview filenames include page+order at `src/ht_lens/cli.py:557-560`. The new tests at `tests/unit/test_image_repair.py:397-407` and `tests/integration/test_repair_cli.py:297-337` lock that preview path.

Round 1 issue §4#2 is fixed: default output now goes to `<extracts>/<doc_id>/repair_draft.detected.json` at `src/ht_lens/cli.py:611-619`, and only `doc1.json`/`doc5.json` remain under `repair_seeds/`. `tests/integration/test_repair_cli.py:340-361` locks the default location.

Round 1 issue §4#3 is fixed in code but not in tests. `_skipped` now includes `page_idx`, `order_idx`, `bbox`, and `reason` at `src/ht_lens/cli.py:563-572`, but no test asserts those fields; `rg` only finds `_skipped` in source and verify artifacts.

The doc5 live re-detection claim is stronger than v1 but still not reproducible from committed artifacts. `verify.md` reports doc5 pages `[109, 223, 257, 339]` and degraded FP 0 across docs 2-5, but this is a self-reported live run, not a test or saved report. That is acceptable as functional evidence, but not as strong as a committed fixture or script output.

## 3. Score audit

독창성 / 15: 14/15 is justified. The final approach avoided the original overbuilt manifest/ingest path and kept a seed-centered audit CLI. I would confirm 14/15.

완결성 / 35: 33/35 is high. The accepted challenge included tests for text-chunk caption handling, parenthetical-prose caption FP, and rotated-page skip reporting (`.claude/phases/phase-8e-6/challenge.md:31-37`), but only missing-origin, draft-not-served, same-basename preview, and synthetic caption cases landed. Suggested score: 31/35.

안정성 / 30: 29/30 is too high. The RE-CODE fixed the direct preview collision, but the downstream `repair-images` apply path is still basename-only and can collide on same-page duplicate basenames. Also `_skipped` field coverage is code-review only. Suggested score: 26-27/30.

확장성 / 20: 19/20 is slightly optimistic. The detector now preserves `order_idx`, but the durable draft seed still emits `image_allowlist` as basenames only (`src/ht_lens/cli.py:582`), while `repair-images` consumes a `set` of basenames at `src/ht_lens/cli.py:421`. That limits safe scaling to book2-style duplicate image names. Suggested score: 17-18/20.

## 4. Issues missed (new this round)

Unchanged since Round 1: the allowlist/apply half of duplicate-basename identity is still not fixed. `detect-repairs` can produce distinct previews, but its draft seed only stores `image_allowlist` basenames at `src/ht_lens/cli.py:582`. `repair-images` then converts that to `set(seed_data["image_allowlist"])` at `src/ht_lens/cli.py:421`, and `run_image_backfill()` writes fixed files as `p{page_idx}_{stem}.png` at `src/ht_lens/image_repair.py:457-471`. Two degraded chunks on the same page with the same basename but different bbox can still overwrite/share the same fixed PNG. The new tests cover same-basename distinct pages (`tests/unit/test_image_repair.py:321-337`) and detect preview files, not same-page apply.

The RE-CODE introduced `_skipped` stable fields but did not add explicit test coverage. `verify.md` admits the lock is “CLI 코드 + 리뷰” for `_skipped` at `.claude/phases/phase-8e-6/verify.md:58-59`. Per the Round 2 rule, a new report field/path without grep-visible test coverage is a finding even if the code looks correct.

The CLI help/docstring is stale after the gitignored default-output fix. `src/ht_lens/cli.py:487` still says default is `repair_seeds/<doc_filename_stem>.detected.json`, and `src/ht_lens/cli.py:493-495` still describes a draft `repair_seeds` output. That is minor, but it directly conflicts with the R1 fix and can cause a human reviewer to look in the wrong place.

The caption detector is broader than the challenge wording. `detect_caption_mispairs()` flags any multi-image page with one captioned and one uncaptioned considered image (`src/ht_lens/image_repair.py:197-221`), not specifically “병합캡션” or parenthetical panel-label signatures. Because it is report-only this is not a correctness failure, but the missing parenthetical-prose/text-caption tests from `.claude/phases/phase-8e-6/challenge.md:34-35` mean review-overload FP risk remains under-tested.

## 5. Verdict

**DOWNGRADE** — The R1 implementation fixes are mostly real, and this should not be rejected: no ingest/schema/serving writes were added, the default draft no longer dirties `repair_seeds/`, and same-basename preview identity is now locked. But the self-score of 95 is too high because the downstream `repair-images` writer remains basename-only for same-page duplicate basenames, `_skipped` has no explicit test, and several accepted challenge tests did not land. A fair score is **91-92**.
