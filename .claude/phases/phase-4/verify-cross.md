## 1. Verification of automated checks

- `verify.md` is not stale by commit history. It explicitly evaluates code commit `25a0a41` at [verify.md](/home/hyunlord/github/ht_lens/.claude/phases/phase-4/verify.md:3), and current `HEAD` is `09d5f42`, a later verify-only commit. I do see a dirty worktree now (`tests/integration/test_static_serving.py` formatting-only diff), so the claims apply to the committed snapshot, not the exact live workspace.

- Round 1’s CI gap about Node provisioning is fixed: [ci.yml](/home/hyunlord/github/ht_lens/.github/workflows/ci.yml:25) now installs Node 22 before pytest. That makes the `font_fit_js` row more credible than last round.

- The remaining evidence gap is unchanged since Round 1: the “CI (remote)” row is still not evidence. [verify.md](/home/hyunlord/github/ht_lens/.claude/phases/phase-4/verify.md:16) says “pending push,” so there is still no audited GitHub Actions result for this phase snapshot.

- The frontend-specific automation is still narrower than the write-up suggests. [test_font_fit_js.py](/home/hyunlord/github/ht_lens/tests/integration/test_font_fit_js.py:1) explicitly tests the Node fallback estimator, not the browser `canvas.measureText` path used in production. Pinning Node fixes silent skip, but it does not make browser font fitting automated.

- Coverage remains only partially meaningful. [pyproject.toml](/home/hyunlord/github/ht_lens/pyproject.toml:54) wires Python coverage through pytest, but most Phase 4 risk sits under `src/ht_lens/api/static/js/`. They should have paired the coverage row with a browser-executed regression or at least clearer JS runtime evidence.

## 2. Verification of functional checks

- Round 1’s concrete browser defects do look fixed. The async race guard is present in [viewer.js](/home/hyunlord/github/ht_lens/src/ht_lens/api/static/js/viewer.js:54), stale DOM cleanup is present at [viewer.js](/home/hyunlord/github/ht_lens/src/ht_lens/api/static/js/viewer.js:39), original mode styling is corrected at [viewer.css](/home/hyunlord/github/ht_lens/src/ht_lens/api/static/css/viewer.css:116), and the new screenshots include multi-page and 404 cases in [README.md](/home/hyunlord/github/ht_lens/docs/phases/phase-4/README.md:11).

- The missing tracked-script complaint from Round 1 is addressed. [README.md](/home/hyunlord/github/ht_lens/docs/phases/phase-4/README.md:24) no longer points at a nonexistent repo script; it now describes the manual capture flow plainly.

- Two functional gaps are still unchanged since Round 1. [verify.md](/home/hyunlord/github/ht_lens/.claude/phases/phase-4/verify.md:51) claims “줌·이동 부드러움,” but the artifacts do not actually exercise zoom keys or browser back/forward; they only show page changes and static screenshots. `history.pushState` exists in code, but `popstate` behavior is not demonstrated.

- Rotated-page and partial-translation verification are still not actually exercised, despite being accepted in [challenge.md](/home/hyunlord/github/ht_lens/.claude/phases/phase-4/challenge.md:82). [verify.md](/home/hyunlord/github/ht_lens/.claude/phases/phase-4/verify.md:71) now acknowledges the limitation, but the evidence is still code-presence/grep, not functional execution.

- The visual evidence remains weaker than the prose. [README.md](/home/hyunlord/github/ht_lens/docs/phases/phase-4/README.md:12) says translation panels stop source bleed-through, but [02-page-translation.png](/home/hyunlord/github/ht_lens/docs/phases/phase-4/screenshots/02-page-translation.png) and [04-page3-translation.png](/home/hyunlord/github/ht_lens/docs/phases/phase-4/screenshots/04-page3-translation.png) still show English text visible behind several translated blocks. That does not invalidate the viewer, but it does weaken the “natural reading” claim.

## 3. Score audit

- 독창성 `14/15`: mostly justified. The pixel-space stage in [page_view.js](/home/hyunlord/github/ht_lens/src/ht_lens/api/static/js/components/page_view.js:9), pushState navigation in [viewer.js](/home/hyunlord/github/ht_lens/src/ht_lens/api/static/js/viewer.js:74), and binary-search font fitting in [font_fit.js](/home/hyunlord/github/ht_lens/src/ht_lens/api/static/js/utils/font_fit.js:1) are phase-appropriate. I would keep this at `13-14/15`.

- 완결성 `32/35`: too high. I would deduct to `27/35`. Multi-page and error-path evidence improved, but zoom/back-forward are still unverified, and rotated/partial-translation remain acknowledged-but-unexercised at [verify.md](/home/hyunlord/github/ht_lens/.claude/phases/phase-4/verify.md:71).

- 안정성 `28/30`: too high. I would deduct to `22/30`. The Round 1 bugs are fixed, but the new regression guards in [test_static_serving.py](/home/hyunlord/github/ht_lens/tests/integration/test_static_serving.py:173) are mostly grep/marker tests, and the browser font-fit path is still manual despite the new CI Node step.

- 확장성 `19/20`: slightly high but close. I would deduct to `18/20`. The split into `viewer.js`, `page_view.js`, `block.js`, and `state.js` is fine for Phase 5, but the history/navigation behavior is still under-tested for a UI that is about to gain more state.

- Fair total: about `80-82/100`, not `93/100`.

## 4. Issues missed (new this round)

- I do not see a concrete RE-CODE regression in the four Round 1 fix areas. `navToken`, `clearViewerDom()`, original-mode CSS scoping, and zoom snapping are all present in current code at [viewer.js](/home/hyunlord/github/ht_lens/src/ht_lens/api/static/js/viewer.js:54), [viewer.js](/home/hyunlord/github/ht_lens/src/ht_lens/api/static/js/viewer.js:85), [viewer.css](/home/hyunlord/github/ht_lens/src/ht_lens/api/static/css/viewer.css:116), and [state.js](/home/hyunlord/github/ht_lens/src/ht_lens/api/static/js/state.js:43).

- The new document index exposes a stale lifecycle state and the verify never mentions it. [index.js](/home/hyunlord/github/ht_lens/src/ht_lens/api/static/js/index.js:34) renders `doc.status` verbatim; [README.md](/home/hyunlord/github/ht_lens/docs/phases/phase-4/README.md:11) shows `ready_for_translation`; but the same README claims the DB already went through `translate` at [README.md](/home/hyunlord/github/ht_lens/docs/phases/phase-4/README.md:3). That mismatch comes from [ingest/pipeline.py](/home/hyunlord/github/ht_lens/src/ht_lens/ingest/pipeline.py:91) setting `Document.status="ready_for_translation"` and [translate/pipeline.py](/home/hyunlord/github/ht_lens/src/ht_lens/translate/pipeline.py:29) only updating `Translation` rows. Phase 4 newly surfaces that inconsistency to the user.

- The screenshot dataset itself looks stale/inconsistent for verification purposes. [README.md](/home/hyunlord/github/ht_lens/docs/phases/phase-4/README.md:22) says the captures reused `/tmp/ht_lens_phase3.db`, not a phase-local setup. Combined with the stale status above, the artifacts do not prove the viewer was exercised against a clean, self-consistent translated document state.

## 5. Verdict

**DOWNGRADE** — Round 1’s concrete viewer bugs appear fixed, so I would not REJECT on code regressions. But the self-verify still overstates the strength of its evidence: remote CI is still unproven, zoom/back-forward/rotated/partial-translation remain unexercised, translation-mode screenshots still show source bleed-through, and the new index page exposes a stale document status that the report never surfaces. A fair score is around `81/100`, not `93/100`.
