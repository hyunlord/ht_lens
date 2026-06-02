## 1. Verification of automated checks

No real prior cross-verify exists for this phase; `.claude/phases/phase-8e-5/verify-cross.md` is only the template placeholder. This is Round 1.

`verify.md` is not stale relative to tracked source: `HEAD` is `e96e88a`, and the only diff from code commit `e16a61e` to `e96e88a` is `.claude/phases/phase-8e-5/verify.md`. Current worktree has untracked phase/log files, but no tracked source diff.

Lint/type/test evidence is mostly credible: `uv run ruff check src tests`, `uv run mypy src/`, and `uv run pytest -q` are plausible current-HEAD checks. However, the required workflow check is `uv run pytest -m "not llm and not slow"`; `pytest -q` may be broader, but the report should state marker behavior explicitly.

Format evidence is weak. The 5-A table says “pre-commit ruff-format (커밋마다)” instead of the required `uv run ruff format --check .`, so I would not count format as independently evidenced.

Coverage is not actually reported. `pyproject.toml` enables pytest-cov, but `verify.md` gives only “822 passed”; it does not provide a coverage percentage or phase target comparison.

CI is correctly marked pending push. That justifies their own −2 stability deduction and prevents a ≥95 pass claim.

## 2. Verification of functional checks

The functional checks exercise the two stated live defects: image override serving for chunks 1/84/85, caption reassignment for page 4 chunks 53/54/55, and 8e-4 dedup interaction. The integration tests in `tests/integration/test_reflow_api.py` also cover stale bbox fallback, scoped doc root via `HT_LENS_EXTRACTS_V2_DIR`, and caption override before dedup.

The biggest functional gap is reproducibility of the actual repair. The live manifest and fixed PNGs are under `data/extracts_v2/1/overrides.json` and `data/extracts_v2/1/images_fixed/*`, but `data/*` is gitignored at `.gitignore:46`. There is no CLI or script committed to regenerate the doc1 override set; `run_image_backfill()` exists only as a library helper in `src/ht_lens/image_repair.py`. A fresh checkout or PR merge gets the serving machinery but not the actual repaired assets or a documented command that recreates them.

The traversal integration test is also weaker than claimed. `test_image_override_traversal_basename_rejected` asserts fallback to the original JPEG because the malicious fixed path does not exist; it does not actually prove `_validate_v2_image()` rejects an existing traversal target.

The “5-doc 무회귀 / 정상 158” evidence is reported as live/manual but not represented by a committed test or reproducible audit artifact. That is acceptable as supporting evidence, but not enough to lock future regressions.

## 3. Score audit

독창성 / 15: `14/15` is justified. Moving from hard-coded chunk ids to stable-evidence manifests in `src/ht_lens/image_repair.py` is a good answer to `debate.md`, and direct PDF clipping via `clip_render_figure()` is cleaner than cropping cached page PNGs. I would confirm 14.

완결성 / 35: `33/35` is too high. The code delivers the router hooks and helper engine, but the actual doc1 repair depends on gitignored local files and no committed regeneration entry point. The plan expected a CLI or script-level backfill surface; only `run_image_backfill()` was added. Suggested score: 30–31.

안정성 / 30: `28/30` is too high. Tests cover many debate points, but absolute `fixed_basename` can escape the managed root, malformed manifest entries can raise during serving despite the docstring saying broken manifests never break serving, format evidence is indirect, and CI is pending. Suggested score: 24–25.

확장성 / 20: `19/20` is slightly high. The manifest design is extensible, but `run_image_backfill()` writes `f"{Path(base).stem}.png"` at `src/ht_lens/image_repair.py:300`, so duplicate original basenames within one doc can overwrite fixed images while both overrides point at the same file. Suggested score: 17–18.

Fair total: about 86–88, depending on whether the untracked live assets are accepted as phase evidence.

## 4. Issues missed (new this round)

1. The actual repair is not durable from git. `verify.md` explicitly says the manifest is gitignored, and `git ls-files data/extracts_v2/1/overrides.json data/extracts_v2/1/images_fixed/*` returns nothing. Since `.gitignore:46` ignores `data/*`, the phase currently commits infrastructure but not the repaired doc1 state or a runnable backfill command. That undercuts defect 1/2 completion outside this one workstation.

2. `fixed_basename` is not constrained to a basename. `chunk_image()` joins `_cache_root()/doc/images_fixed` with `img_ov.fixed_basename` at `src/ht_lens/api/routers/reflow.py:229`, and `_validate_v2_image()` only rejects `".."` segments plus suffix/nonexistence at lines 192–207. An absolute manifest value like `/tmp/owned.png` would discard the intended root during path joining and can be served if it exists and has an allowed suffix.

3. Malformed manifest entries can still break serving. `load_overrides()` catches invalid JSON, but then assumes every item in `raw.get("images", [])` has `.keys()` and indexable fields at `src/ht_lens/image_repair.py:161–170`. A syntactically valid manifest with `{"images": ["bad"]}` raises `AttributeError`, contradicting the docstring promise that a broken manifest “must never break serving.”

4. Backfill output filenames can collide. `run_image_backfill()` derives `fixed_basename` only from `Path(base).stem` at `src/ht_lens/image_repair.py:300`. If two image chunks in the same document share an original basename, the second write overwrites the first, while manifest matching by page/bbox still points both chunks to one fixed PNG. No unit test covers duplicate basenames.

## 5. Verdict

**DOWNGRADE** — The self-report is directionally honest and below the pass threshold, but its 94 is still too generous. The implementation addressed many debate objections, yet the repaired assets are gitignored with no committed regeneration path, and the new manifest serving path has concrete validation gaps. I would score this around **86–88** and require a small RE-CODE or Planner decision before treating Phase 8e-5 as complete.
