## 1. Verification of automated checks

`verify.md` is not stale relative to code: current HEAD is `612a1af chore(phase-8e-1): verify`, after code/test commits `d08904b` and `bd3f166`. No later code commit exists. Current untracked files include `.claude/phases/phase-8e-1/verify-cross.md`, `summary.md`, and `.claude/scheduled_tasks.lock`; that means the “git status clean” wording in `verify.md:3` is imprecise, but it does not indicate stale verification.

- Lint / format / type: credible as reported in `verify.md:8-10`; source diff is small and mypy-sensitive paths remain typed.
- Test: credible enough; `verify.md:11` reports the full non-LLM/non-slow suite, `768 passed, 1 skipped, 8 deselected`.
- New tests: grep confirms the seven named tests exist across `tests/unit/test_math_protect.py`, `tests/unit/test_translate_prompt.py`, and `tests/integration/test_chunk_translate.py`.
- Coverage: weaker evidence. `pyproject.toml` does enable `--cov=ht_lens`, but `verify.md:13` gives no numeric coverage result or missing-line output. It only asserts the new paths are covered.
- CI: `N/A` is acceptable if this branch truly has no Actions trigger, but “local 768 is CI-equivalent” is an overstatement. It does not cover environment differences or packaging.

## 2. Verification of functional checks

The core math fallback check is mostly credible: `verify.md:23-29` claims live retry of the six failed doc7 chunks and `failed=6` to `failed=0`. This directly exercises the phase’s practical target.

The main gap is byte-identity evidence. The report says byte-identical for chunk16, chunk67, and chunk90 only (`verify.md:29`), but the live recovery set is six chunks: 16/67/71/72/76/90. Since the DoD-critical invariant is “math byte-identical 보존,” the live check should state all math runs across all six recovered chunks were compared, or explain why the other three have no math runs. The plan said chunk72 has one inline span, so omission matters.

The bold method spike is plausible but thinly evidenced. `verify.md:31-33` reports CPU MinerU metadata inspection and raw markdown `**` count, but no saved command/output artifact exists under `.claude/phases/phase-8e-1/`. Given challenge reduced bold to a finding, this is not a blocker, but the evidence is not independently auditable from the repo.

## 3. Score audit

- 독창성 / 15: `13/15` is justified. The final approach reflects the debate: segment fallback was removed, ASCII sentinel plus prompt hardening targets the diagnosed failure, and `_MATH_LOSS_RETRIES` is bounded in `src/ht_lens/translate/chunk_pipeline.py:272-286`. Confirm 13.

- 완결성 / 35: `33/35` is slightly high. Math recovery is shown for 6/6 chunks, but live byte-identical evidence is only listed for 3/6 chunks in `verify.md:29`. Bold is a documented defer, not a usable method. Suggest 31/35.

- 안정성 / 30: `29/30` is high. The retry/dedup/caption tests are real (`tests/integration/test_chunk_translate.py:423`, `456`, `487`, `521`), but one collision path remains semantically under-tested: collision forces hashed sentinels in `chunk_pipeline.py:272-277`, while the new prompt only names `[[MATH0]]` / `[[MATHn]]` in `openai_compat.py:202` and `214`. Suggest 27/30.

- 확장성 / 20: `18/20` is fair. The change is small and compatible with 8e-2 batch migration, but bold remains an unresolved backend decision. Confirm 18.

Fair adjusted total: **89/100**.

## 4. Issues missed (new this round)

- Live byte-identity is under-proven for the full recovered set. `verify.md:28-29` lists six recovered chunks but only byte-checks chunks 16, 67, and 90. The report should not claim full byte-identical preservation unless chunks 71/72/76 were also compared. This is especially concrete because `plan.md` identifies chunk72 as a single inline math failure.

- The hashed collision sentinel path is not locked against the real prompt change. When source text already contains `[[MATH0]]`, `_translate_protected` switches to `[[MATH<sha>0]]` via `chunk_pipeline.py:272-277` and `math_protect.py:68`. The prompt hardening in `openai_compat.py:202` and `214` only describes `[[MATH0]]`, `[[MATH1]]`, or `[[MATHn]]`. The existing collision test at `tests/integration/test_chunk_translate.py:289-317` uses a mock that preserves the hashed token by default; it does not test that the new prompt causes real qwen or a stricter mock to preserve non-default placeholder prefixes.

- Coverage evidence is too hand-wavy for a phase that changed shared translation primitives. `verify.md:13` says coverage is included and new paths are covered, but no percentage or missing-line excerpt is recorded. This is not a functional defect, but it weakens the automated evidence table.

- Bold finding lacks a durable artifact. `verify.md:31-33` is the only place recording the MinerU CPU metadata result. Since 8e-2 is expected to make a GPU/defer decision, a saved minimal excerpt of `middle.json` keys or the exact inspection command would reduce re-litigation.

## 5. Verdict

**DOWNGRADE** — The implementation is directionally sound and the key tests promised by debate were mostly added, so this does not warrant REJECT. The self-score overstates completeness and stability because live byte-identical evidence covers only half of the recovered chunks, and the new ASCII sentinel plus prompt rule leaves the hashed collision sentinel path untested against the actual preservation wording. Fair score: **89/100**.
