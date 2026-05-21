## 1. Verification of automated checks

- No stale-verify signal. `HEAD` is commit `d915117`, the same commit that added [verify.md](</home/hyunlord/github/ht_lens/.claude/phases/phase-6d/verify.md:1>), and the provided log shows no later code commits. On the specific stale-report question, their evidence is current-head.

- `lint` / `format` / `type` are plausible as reported in [verify.md](</home/hyunlord/github/ht_lens/.claude/phases/phase-6d/verify.md:7>) because the tree structure matches the claimed Phase 6d files and there is no obvious broken syntax. I do not see a contradiction in source that would make those outputs impossible.

- `CI (local)` is weaker than the table implies. [Makefile](</home/hyunlord/github/ht_lens/Makefile:1>) defines `check` as `fmt lint test-fast`, and `fmt` runs `ruff format .`, not `ruff format --check`. That means `make check` is not a faithful local mirror of remote CI; it can repair formatting instead of detecting failure.

- `CI (remote)` is not verified. [verify.md](</home/hyunlord/github/ht_lens/.claude/phases/phase-6d/verify.md:16>) explicitly says “pending push”, so this row should not be counted as passed evidence.

- Migration/test coverage is overstated in the regression table. [verify.md](</home/hyunlord/github/ht_lens/.claude/phases/phase-6d/verify.md:109>) says `test_alembic` locks `0003` + UNIQUE, but [tests/integration/test_alembic.py](</home/hyunlord/github/ht_lens/tests/integration/test_alembic.py:60>) still only asserts the pre-6d table set and does not check `jobs`, `documents.summary`, `documents.summarized_at`, or `uq_documents_src_pdf_sha256`.

## 2. Verification of functional checks

- The claimed “PDF drop → automatic processing → viewer entry” flow is not actually exercised as one UI flow. In [scripts/phase6d_scenario.py](</home/hyunlord/github/ht_lens/scripts/phase6d_scenario.py:91>) the scenario fetches `/documents` and then does a direct `page.goto("viewer.html?doc=...")`, bypassing the new-card click and any automatic handoff. That does not fully prove the DoD phrasing in [ROADMAP.md](</home/hyunlord/github/ht_lens/ROADMAP.md:298>).

- The 200-page SLA evidence is still only an extrapolation from a 2-page sample. [verify.md](</home/hyunlord/github/ht_lens/.claude/phases/phase-6d/verify.md:44>) measures one 56-second run and infers ~93 minutes for 200 pages. That is directionally useful, but it is not a realistic high-page-count or high-block-count verification.

- Dedup functional coverage is incomplete. The manual curl in [verify.md](</home/hyunlord/github/ht_lens/.claude/phases/phase-6d/verify.md:63>) proves re-upload after the document already exists, but it does not prove the concurrent same-SHA case. The only dedicated race test in [tests/integration/test_api_uploads.py](</home/hyunlord/github/ht_lens/tests/integration/test_api_uploads.py:133>) does not assert the claimed single-document outcome.

- Summary display as a “separate area” is acceptable: the viewer banner mount exists in [viewer.html](</home/hyunlord/github/ht_lens/src/ht_lens/api/static/viewer.html:37>) and is rendered in [viewer.js](</home/hyunlord/github/ht_lens/src/ht_lens/api/static/js/viewer.js:273>). That part of the DoD is substantively met.

## 3. Score audit

- 독창성 `14/15`: mostly justified. The `asyncio.to_thread` extraction and per-stage session boundaries in [jobs/pipeline.py](</home/hyunlord/github/ht_lens/src/ht_lens/jobs/pipeline.py:133>) are sensible, phase-appropriate choices. I would keep this at `13–14/15`.

- 완결성 `34/35`: too high. Deduct about 5. The verified user flow does not actually go through the new viewer-entry path, and the 200-page requirement is inferred rather than exercised. More importantly, same-name different-file uploads are not handled correctly, which is core Phase 6d scope.

- 안정성 `30/30`: not justified. Deduct about 8. Concurrent same-SHA uploads can still create a second job in [uploads.py](</home/hyunlord/github/ht_lens/src/ht_lens/api/routers/uploads.py:127>), and the upload pipeline always calls `ingest_extract_dir(... overwrite=True ...)` in [jobs/pipeline.py](</home/hyunlord/github/ht_lens/src/ht_lens/jobs/pipeline.py:159>), which interacts dangerously with filename-based overwrite in [ingest/pipeline.py](</home/hyunlord/github/ht_lens/src/ht_lens/ingest/pipeline.py:71>).

- 확장성 `19/20`: too high. Deduct about 4. Filename-collision overwrite means the document library does not scale to normal user behavior, and restart recovery only flips job rows without reconciling partial document state in [mark_in_flight_jobs_failed](</home/hyunlord/github/ht_lens/src/ht_lens/jobs/pipeline.py:245>).

- Suggested fair total: about `81/100`, not `97/100`.

## 4. Issues missed (new this round)

- Different PDFs with the same original filename overwrite each other. `process_upload_job()` always passes `overwrite=True` plus the user-visible filename in [jobs/pipeline.py](</home/hyunlord/github/ht_lens/src/ht_lens/jobs/pipeline.py:159>), and `ingest_extract_dir()` resolves existing documents by `Document.filename == display_filename` then deletes the old document in [ingest/pipeline.py](</home/hyunlord/github/ht_lens/src/ht_lens/ingest/pipeline.py:71>). Two unrelated `report.pdf` uploads should coexist; here the second replaces the first.

- The concurrent same-SHA race is still not resolved; it is merely converted into “second job may fail later.” In [uploads.py](</home/hyunlord/github/ht_lens/src/ht_lens/api/routers/uploads.py:129>) if the upload file already exists but the `Document` row is not committed yet, the code falls through and creates another `Job` anyway. The supposed race test in [test_api_uploads.py](</home/hyunlord/github/ht_lens/tests/integration/test_api_uploads.py:161>) ends without asserting dedup success and explicitly tolerates the second-job behavior.

- Restart recovery leaves partial document state unaddressed. Startup recovery in [jobs/pipeline.py](</home/hyunlord/github/ht_lens/src/ht_lens/jobs/pipeline.py:245>) only marks active jobs `failed`; it does not clean or resume partially ingested/translated documents. Because `/uploads` dedups by `documents.src_pdf_sha256` in [uploads.py](</home/hyunlord/github/ht_lens/src/ht_lens/api/routers/uploads.py:122>), re-uploading the same PDF after a restart can route the user back to an incomplete document instead of restarting processing. [test_api_jobs.py](</home/hyunlord/github/ht_lens/tests/integration/test_api_jobs.py:122>) only checks the job-row status flip, not the document-state consequence.

## 5. Verdict

**REJECT**. The report is not stale, but its scoring materially overstates completeness and stability. There is at least one core functional bug in current code: two distinct uploads with the same filename can delete/replace the earlier document, and the claimed concurrent dedup fix is not actually fixed or properly tested. Verification also bypasses the real viewer-entry flow and treats a 2-page timing extrapolation as DoD proof for 200 pages. This looks like a RE-CODE, not a RE-PLAN: the phase architecture is mostly fine, but the filename-overwrite semantics, concurrent dedup behavior, and recovery tests need concrete fixes before a 95+ pass is credible.
