## 1. Verification of automated checks

The v2 report is not stale relative to tracked source. Current `HEAD` is `333200c`, which only updates `.claude/phases/phase-8e-5/verify.md`; the source/test RE-CODE commits are `dfd1251` and `e91afc9`. The worktree has untracked files, but no tracked source drift.

R1 issues were materially addressed: `repair_seeds/doc1.json` is committed, `is_safe_basename()` exists, non-dict manifest roots/items are handled, and fixed PNG names now include `p<page>_`. Do not re-raise the original durability/traversal/non-dict/collision findings as-is.

The 5-A evidence is plausible but not independently reproducible from the report alone. `ruff check src tests`, `ruff format --check .`, `mypy src/`, and `pytest -q` are listed with concrete results. CI is honestly marked pending. Coverage is still not quantified even though `pyproject.toml:71` enables `--cov=ht_lens --cov-report=term-missing`; the table says tests passed but gives no coverage percentage or changed-file coverage.

One mismatch: CI runs `uv run ruff check .` and `uv run pytest -m "not llm and not slow"` in `.github/workflows/ci.yml:45-54`, while self-verify reports `ruff check src tests` and `pytest -q`. `pytest -q` is broader if markers are not excluded, but the lint command is narrower than CI.

## 2. Verification of functional checks

The functional checks cover the core DoD well: defect 1 image replacements for ch1/84/85, defect 2 captions for ch53/54/55, non-target image fallback, and 8e-4 dedup stability. The local generated manifest at `data/extracts_v2/1/overrides.json` contains exactly three image overrides and three caption overrides, and `repair_seeds/doc1.json` is now a durable seed.

The API integration coverage is credible for serving behavior. `tests/integration/test_reflow_api.py:322-354` verifies a matching image override serves PNG, `:357-387` verifies stale evidence falls back, `:485-518` verifies absolute `fixed_basename` is rejected, and `:425-483` verifies caption override plus dedup interaction.

The functional gap is the new CLI path. `src/ht_lens/cli.py:383-466` adds `repair-images`, but there is no automated `main([... "repair-images" ...])` or subprocess test. The self-report only cites live dry-run/apply. For a RE-CODE whose main durability fix is a CLI regeneration path, live evidence is useful but not enough to lock command wiring, exit behavior, seed parsing, `HT_LENS_EXTRACTS_V2_DIR`, and `--apply/--dry-run`.

## 3. Score audit

독창성 / 15: `14/15` is justified. The manifest keyed by page, original basename, and bbox in `src/ht_lens/image_repair.py:205-228`, plus PDF clip rendering in `:236-272`, is a solid non-destructive repair design.

완결성 / 35: `33/35` is slightly high. The two live defects are handled, and R1 durability is mostly fixed by `repair_seeds/doc1.json`. Deduct 2-3 because `repair-images` itself lacks automated coverage and seed validation is loose. Suggested: 31-32.

안정성 / 30: `29/30` is too high. CI is pending, coverage is unreported, the CI lint command is broader than the reported lint command, and malformed manifest field types can still crash matching. Suggested: 26-27.

확장성 / 20: `19/20` is mostly justified but optimistic. The manifest design is extensible, but the CLI treats missing/empty `image_allowlist` as `None` at `src/ht_lens/cli.py:417`, which means “repair all detected” rather than “repair reviewed seed only.” Suggested: 18.

Fair total: about 90-92, not 95.

## 4. Issues missed (new this round)

1. New CLI command is untested. `repair_images_command()` was introduced at `src/ht_lens/cli.py:383-466`, but `rg "repair-images" tests` finds no automated CLI test. This is a Round 2 finding under the stated rule: the RE-CODE introduced a new command surface and relied on live/manual execution rather than locking command registration, dry-run no-write behavior, apply output, and error mapping.

2. Malformed manifest field types can still break serving. `load_overrides()` only checks item is a dict and required keys exist at `src/ht_lens/image_repair.py:166-178`; it does not validate `bbox` is a numeric 4-list. `_bbox_close()` then calls `float()` without catching `ValueError` at `:141-144`. A manifest entry with `"bbox": "oops"` can crash `/v2/chunks/{id}/image` or `/reflow`, contradicting the docstring at `:151-153` that broken manifests must never break serving.

3. The new seed path can silently disable the allowlist. `repair_images_command()` converts missing or empty `image_allowlist` into `None` at `src/ht_lens/cli.py:417`, and `run_image_backfill()` interprets `None` as every detected candidate allowed at `src/ht_lens/image_repair.py:313`. That weakens the challenge decision to use a reviewed allowlist; a malformed captions-only seed can clip-render unreviewed dark images.

4. CLI seed parsing has no controlled failure path. `json.loads(seed.read_text())` and `CaptionOverride(c["page_idx"], ...)` at `src/ht_lens/cli.py:416-420` can raise raw `JSONDecodeError`, `TypeError`, or `KeyError`. Existing CLI tests elsewhere assert clean exit codes for user-facing commands, but this new command has no equivalent.

## 5. Verdict

**DOWNGRADE** — R1’s main defects were genuinely fixed, and the phase is much closer to pass than Round 1. I would not reject it. However, the self-score of 95 overstates stability: the new regeneration CLI is not under automated test, coverage is not reported, and malformed manifest field values can still violate the “broken manifest never breaks serving” contract. Fair score: **90-92**.
