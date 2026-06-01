## 1. Over-engineering

The plan spends too much machinery on per-test `_find_jsdom()` edits: `File-level changes` proposes touching 16 `tests/integration/test_*_js.py` files. That is churn for a test harness problem. A shared helper in `tests/conftest.py` or a tiny Node runner should replace the duplicated path search instead of editing every jsdom test.

`F. main cutover` mixes workflow operations into implementation scope. Merging `prototype-reflow → main`, pushing, and checking “GitHub CI 첫 main 실행” belong in verify/summary, not as code deliverables. This makes Stage 4 harder to review and blurs what code change actually satisfies Phase 8e.

The plan declares this phase the “v2.0 milestone” while explicitly deferring `book2 full 1370p·볼드` and relying on “5-doc” verification. `ROADMAP.md` Phase 8e DoD says “7 docs 2.0 DB 완료” and “reflow viewer에서 전체 읽기”; the plan’s DoD mapping omits the 7-doc completion requirement.

## 2. Hidden assumptions

The rollback story is internally inconsistent. The plan says 1.x prod is `0004/49850/0`, but `src/ht_lens/api/app.py::_lifespan` rejects any DB whose `alembic_version` is not `ALEMBIC_HEAD`, and `src/ht_lens/db/session.py` sets `ALEMBIC_HEAD = "0007"`. An env flip back to `data/ht_lens.db` will likely fail startup, not provide “즉시 롤백”.

The plan assumes `HT_LENS_DB_URL` is always exactly `sqlite+aiosqlite:///...`. Both `src/ht_lens/api/app.py::_db_path_from_env()` and `src/ht_lens/cli.py::_db_path_from_env()` silently fall back to `_DEFAULT_DB` for any other value. A typo, `sqlite:///...`, relative URL, or quoted systemd value can redirect production to the 1.x DB without warning.

The schema-head guard plan assumes adding `_require_schema_head(session)` inside `retranslate_short()` is enough. But `src/ht_lens/cli.py` calls `from_env_translate()` and `llm.health_check()` before creating the DB session in the `translate-chunks` command. If the LLM is down and the DB is stale, the user may not get the promised clean `SchemaVersionMismatch` exit 3.

The root redirect assumes `/static/reflow.html` is a valid default 2.0 entry point, but the plan itself states `reflow.js` requires `?doc=<id>`. Redirecting `/` to a page with no document selected is not a real cutover unless the empty-doc state is intentionally acceptable and tested.

## 3. Edge cases

Rollback to a 1.x DB at migration `0004` is the biggest break case. The plan’s “1.x viewer/blocks 작동” verification must account for app startup schema rejection before any `/documents`, `/pages`, or `/blocks` route can be exercised.

Malformed deployment env values can mutate the wrong DB. A systemd `HT_LENS_DB_URL=sqlite:///data/ht_lens_v2.db`, a missing slash, or a path with spaces will currently fall through to `_DEFAULT_DB=data/ht_lens.db`; that directly violates the “1.x DB 파일 절대 불변” requirement.

`RedirectResponse("/static/reflow.html")` may fail behind a reverse proxy or mounted app that uses `root_path`; a hard absolute path ignores deployment prefix. If this app ever runs under `/ht-lens`, `/` will redirect outside the prefix.

The jsdom provisioning assumes Node 22 plus `npm ci` is enough. Existing tests import jsdom by file URI from `_find_jsdom()`, not package resolution. If one of the 16 duplicated helpers is missed, CI will still silently skip part of the JS coverage.

Live cross-doc RAG verification can pass trivially if the query only finds same-doc context or if embeddings are stale. The plan should specify the exact endpoint/path and assert `exclude_doc_ids` behavior via returned `doc_id`, not just “doc A 질문 → doc B ref”.

## 4. Alternative approaches

For jsdom, stop resolving `lib/api.js` manually. Add `jsdom` to `package.json`, then make tests run Node scripts that use normal ESM package resolution: `import { JSDOM } from "jsdom"`. That removes host-specific paths and avoids changing 16 test files.

For schema guards, create a shared public helper such as `ht_lens.db.schema_guard.require_schema_head()`. Reusing private `_require_schema_head` from `chunk_pipeline.py` couples short retranslation to translation-pipeline internals and duplicates the same logic already present in ingest and legacy translation paths.

For rollback, either migrate a copy of the 1.x DB through additive migrations to `0007`, or define rollback as switching both DB and code version. The current “env flip only” approach is not credible with strict head checking in API startup.

For `/`, a minimal document picker or redirect to a configured `HT_LENS_DEFAULT_DOC_ID` would be more honest than sending users to `reflow.html` with no `doc` query. If doc picker is out of scope, keep `/` unchanged and document the direct 2.0 URL.

## 5. Missing tests

Add `test_rollback_db_at_0004_contract`: point `HT_LENS_DB_URL` at a migrated-through-0004 1.x-style DB and assert the intended rollback behavior. If startup must fail, the plan’s rollback claim is false.

Add `test_db_path_from_env_rejects_malformed_sqlite_url` for both `src/ht_lens/api/app.py::_db_path_from_env()` and `src/ht_lens/cli.py::_db_path_from_env()`. Silent fallback to `_DEFAULT_DB` must be locked out before cutover.

Add `test_translate_chunks_short_only_schema_mismatch_precedes_llm_health_check`: stale DB plus failing LLM should still return `SchemaVersionMismatch` exit 3 if that is the claimed contract.

Add `test_root_redirect_location_and_empty_doc_state`: assert `/` redirects exactly as intended and that `/static/reflow.html` without `?doc=` renders a controlled empty/error state, not a broken page.

Add `test_all_jsdom_tests_use_repo_local_jsdom`: after `npm ci`, verify every `_find_jsdom()` path or shared helper resolves `node_modules/jsdom`, and CI output has zero “no jsdom install located” skips.

Add a 7-doc Phase 8e acceptance check, not just 5-doc smoke: `test_phase_8e_all_expected_docs_have_reflow_chunks_translations_embeddings` should assert the ROADMAP DoD directly.
