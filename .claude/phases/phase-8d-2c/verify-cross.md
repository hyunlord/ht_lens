## 1. Verification of automated checks

Lint/format/type/test evidence in `.claude/phases/phase-8d-2c/verify.md` is broadly credible: current `HEAD` is `87b2c13 chore(phase-8d-2c): verify`, after the code commits `96eb729`, `ceae9fa`, and test commit `faf8d13`. No code commits appear after verify, so this is not a stale-verify case.

`git status` is not clean now, but only because `.claude/phases/phase-8d-2c/summary.md` and `verify-cross.md` are untracked/template artifacts. I do not see source/test drift after `verify.md`.

The local test count claim is plausible: `pyproject.toml:71` enables coverage automatically, and the new test files match the claimed surfaces. The weak item is CI: `verify.md` marks GitHub Actions as N/A, while `WORKFLOW.md` lists CI green as the standard check. That is acceptable as a disclosed gap only if this branch truly has no PR/main workflow trigger; it is not equivalent to actual CI.

## 2. Verification of functional checks

The short retranslation path is materially exercised. Tests cover selector inclusion/exclusion, duplicate `where`, all-type neighbor context, cache-key nulling, dry-run no-write, explicit `--chunk-id`, and CLI subprocess paths in `tests/integration/test_short_retranslate.py` and `tests/integration/test_short_retranslate_cli.py`.

The live check demonstrates the key `where -> 여기서` behavior, but it is weaker than stated because it is against dev DB `data/ht_lens_v2.db` doc 1, not a reproducible fixture or the doc7 evidence described in `plan.md`. It proves one local state, not broad selector safety before 8e.

Resize is only tested at `resize.js` unit level. `tests/integration/test_resize_js.py` covers clamp/session/margin/compare/close/drag well, but `verify.md` correctly admits `reflow.js` radio-to-`syncPaneMargin` wiring lacks end-to-end jsdom coverage. No browser-level functional check validates the real drawer on `reflow.html`.

## 3. Score audit

독창성 13/15: Mostly justified. `src/ht_lens/translate/short_retranslate.py:127` correctly isolates context-specific retranslation and avoids content-cache poisoning with `cache_key = None` at lines 177-180. Deduction remains warranted because translation repair plus drawer resize is still a broad scope bundle for one phase.

완결성 33/35: Slightly high. The challenge explicitly accepted testing malformed/delimiter-free output in `.claude/phases/phase-8d-2c/challenge.md`, but the actual malformed test only covers empty output and dropped math placeholders at `tests/integration/test_short_retranslate.py:230-271`. Suggested score: 31/35.

안정성 28/30: Too high. `src/ht_lens/cli.py:395-399` exposes `--dry-run`, but if passed without `--short-only` or `--chunk-id`, the command falls through to normal `translate_chunks` and can write. Also, explicit `--chunk-id` values not found in the document silently produce `candidates=0` and exit 0 via `short_retranslate.py:152-156`. Suggested score: 25/30.

확장성 18/20: Reasonable but slightly optimistic. The `cache_key=NULL` approach is a good 8e-safe choice, but silent no-op explicit chunk targeting will be painful during 7-doc migration. Suggested score: 17/20.

## 4. Issues missed (new this round)

`--dry-run` is unsafe when used without `--short-only` or `--chunk-id`. The option is globally available in `src/ht_lens/cli.py:395-399`, but the branch at lines 431-462 only honors it for short/explicit retranslation. A realistic operator command like `translate-chunks --doc-id X --dry-run` will run the normal translation path at lines 464-479 and can write. No test covers this misuse.

Explicit `--chunk-id` silently accepts nonexistent or wrong-document IDs. `retranslate_short` filters `targets = [c for c in chunks if c.id in chunk_ids]` at `src/ht_lens/translate/short_retranslate.py:152-153`, but never checks that requested IDs were found. The CLI then exits 0 with `candidates=0` at `src/ht_lens/cli.py:452-462`. This undermines the “safe manual repair” path added after debate.

Malformed LLM output is overclaimed. `challenge.md` promised delimiter-free/prose preservation, but `_translate_with_context` accepts any non-empty string if placeholders are intact (`src/ht_lens/translate/short_retranslate.py:120-124`, 170-172). A response that includes explanation text or repeats neighbor context would overwrite the existing translation. The current test name says “malformed,” but only locks whitespace and placeholder loss.

The live functional evidence mutates ignored dev DB state and is not reproducible from committed fixtures. That is fine as supplemental evidence, but the durable evidence should be the tests; `where -> 여기서` itself is not locked in a realistic integration fixture because mocks do not verify Korean connective behavior.

## 5. Verdict

**DOWNGRADE** — The implementation addresses the major debate risks, especially cache poisoning and compare-mode margin behavior, and the reported 92 is directionally honest. However, the CLI has two concrete untested safety gaps around `--dry-run` misuse and silent invalid `--chunk-id`, and the claimed malformed-output guard is narrower than the challenge required. Fair score: **86/100**. No RE-PLAN is needed, but these are legitimate RE-CODE candidates before treating 8d-2c as migration-safe.
