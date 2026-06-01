# Phase 8e-3 — Challenge

Codex가 **rollback이 깨진다는 critical 결함**(lifespan이 0007만 허용 → 1.x 0004 env-flip 시 startup 크래시)을 잡음. 사용자 결정으로 해결. 그 외 malformed-env silent fallback, schema-guard 순서, root 빈-doc, jsdom 16-file churn 전부 accept. **PASS with revisions**(cutover 형태 유지, rollback 정합성 + 안전 하드닝 추가).

## Debate responses
### 1. Over-engineering
- **accept (jsdom 16-file churn)**: `_find_jsdom`는 11 파일 **동일**. per-file edit 대신 **repo-local `node_modules/jsdom` 경로 1줄을 동일 블록에 일괄 추가**(스크립트) + package.json/`npm ci`. (Codex의 bare-import 대안은 11 파일 prelude 재작성이라 오히려 churn↑; 최소 변경 채택.)
- **accept (cutover=verify/merge)**: main 머지·GitHub CI는 **Stage 4-5(verify/cutover)** 로, 코드 deliverable 아님. 코드 = redirect/CI/guard/debt만.
- **accept-disclosed (7-doc DoD)**: ROADMAP "7 docs"는 Planner가 5-doc(papers2+Aggarwal+sample+book2-ch28)로 supersede(8e-2 확정), book2 full = cutover 후 follow-up(`--timeout` 내부 fix로 one-shot 가능). v2.0 마일스톤 scope=5-doc, subphase로 기재.

### 2. Hidden assumptions
- **accept (CRITICAL, rollback 깨짐)**: 확인 — `app.py` lifespan(:102)이 `version != "0007"` → SchemaVersionMismatch. 1.x=0004 → env-flip 롤백 시 startup 크래시. **사용자 결정: startup guard를 cutover-window allow-list `{0004, 0007}`로 완화** → env-flip 1.x(0004) 정상 기동(1.x viewer.html; 2.0 route는 chunks 없어 미사용). 알 수 없는 버전은 여전히 거부. +test.
- **accept (malformed env silent fallback)**: `_db_path_from_env`(app.py+cli.py)가 `sqlite+aiosqlite:///` 아닌 값 → 조용히 `_DEFAULT_DB`(1.x) fallback. cutover서 deploy env 오타/`sqlite:///`/공백 → 의도와 다른 DB. **비어있지-않은 malformed → raise(fail loud)**, empty → default OK. +test 양쪽.
- **accept (schema-guard 순서)**: CLI `translate-chunks`가 `from_env_translate()`+`health_check()`를 session 전 호출 → stale DB + LLM down 시 exit 4(health)가 exit 3(schema) 선점. **schema-head 체크를 health_check 전으로** → 약속한 exit 3 계약. +test.
- **accept (root 빈-doc)**: reflow.html `?doc=` 필요 → **사용자 결정: `/` → `/static/index.html`(문서 목록)**. index.js per-doc 링크를 reflow.html?doc=로(2.0). 빈-doc 에러 회피.

### 3. Edge cases
- **accept (0004 rollback startup)**: allow-list로 기동 가능(§2). 테스트 = 0004 DB 기동 OK + 1.x route 작동 + unknown 버전 거부.
- **accept (malformed env → 1.x 변경 위험)**: reflow는 read-only라 파일 변경은 없으나 "의도와 다른 DB serve"는 위험 → raise로 차단(§2).
- **accept (root_path/proxy)**: redirect를 **root_path-aware**(상대 또는 `request.scope['root_path']` 반영)로. `/ht-lens` prefix 하 동작.
- **accept (jsdom 일부 누락 silent skip)**: 11 파일 **전부** 동일 패치 + verify서 "no jsdom located" skip 0 확인.
- **accept (cross-doc trivial pass)**: live 검증은 **반환 `doc_id`가 질의 doc과 다름**을 단언(exclude_doc_ids 동작), "ref 등장"만 아님.

### 4. Alternative approaches
- **partial (jsdom bare-import)**: 11 파일 재작성 비용 > repo-local 경로 1줄 추가. 최소 변경(경로 추가) 채택, package.json은 추가(CI `npm ci`).
- **accept (공유 schema_guard)**: private `_require_schema_head`(chunk_pipeline) 재사용 대신 **공개 `ht_lens.db.schema_guard.require_schema_head()`** 헬퍼로 추출, retranslate_short/ingest/translate 공유.
- **accept (rollback 정의)**: allow-list로 env-flip-only 롤백 성립(사용자 1). git-revert는 백업 경로로만 기재.
- **accept (root)**: index.html 문서목록(사용자) — doc picker 신규 불요(기존 페이지 재사용).

### 5. Missing tests — 채택
1. `test_rollback_db_at_0004_starts`(allow-list) + unknown 버전 거부.
2. `test_db_path_from_env_rejects_malformed_url`(app+cli, raise).
3. `test_short_only_schema_mismatch_before_llm_health`(exit 3 선점).
4. `test_root_redirects_to_index`(+root_path-aware).
5. jsdom: `npm ci` 후 repo-local 인식 + skip 0(verify 확인).
6. cross-doc: 반환 doc_id != 질의 doc(8d-2b 단위 + 5-doc live).
7. (7-doc) = 5-doc subphase 명시(scope, recode 아님).

## Plan revisions
- **R-A** lifespan schema **allow-list {0004,0007}**(cutover-window) — env-flip 롤백 성립(CRITICAL).
- **R-B** root `/` → `index.html`(문서목록) + index.js per-doc → reflow.html?doc=, root_path-aware.
- **R-C** `_db_path_from_env`(app+cli) malformed URL **raise**(silent fallback 제거).
- **R-D** 공개 `schema_guard.require_schema_head()` → retranslate_short; CLI `--short-only` schema 체크 **health_check 전**.
- **R-E** jsdom: package.json+`npm ci`+repo-local 경로(11 파일 동일 일괄).
- **R-F** main 머지/CI = verify/cutover stage(코드 아님).
- **R-G** cross-doc live = 반환 doc_id≠질의 doc 단언.
- **R-H** 5-doc = v2.0 subphase(7-doc/book2 full = follow-up, disclosed).

## DoD checklist
| DoD | Status | Evidence |
| --- | ------ | -------- |
| cutover(2.0 기본) + 즉시 롤백 | 계획 | runtime env + **allow-list로 0004 기동** + .env.example + 롤백 검증 |
| jsdom CI | 계획 | package.json+ci.yml+repo-local, skip 0 |
| schema-head debt | 계획 | retranslate_short guard + exit 3 선점 test |
| cross-doc RAG live | 계획 | 5-doc doc_id≠ 단언 |
| reflow 읽기 | 계획 | 5-doc smoke + root→index |
| 1.x 무손상/롤백 | 계획 | blocks 49850, 0004 기동 OK |
| malformed env 안전 | 계획 | raise test |
| GitHub CI 첫 main | cutover | gh run green |

## Risk register
| Risk | L | I | Mitigation |
| ---- | - | - | ---------- |
| **rollback 크래시(0004)** | (was 고) | 고 | allow-list {0004,0007}(R-A) + test |
| malformed env → 오DB serve | 중 | 고 | raise(R-C) + test |
| 1.x DB 파일 변경 | 저 | 고 | env만, reflow read-only, 49850 재확인 |
| GitHub CI 첫 main red | 중 | 중 | 로컬 npm ci+jsdom green 후 머지, red→진단·hold |
| schema allow-list 과완화 | 저 | 중 | {0004,0007}만(unknown 거부), 1.x deprecation 후 0004 제거 |

## Decision
- [x] **PASS → proceed to code** (R-A~R-H). Codex critical(rollback) 사용자 결정으로 해결 + 안전 하드닝(malformed env, guard 순서, root). cutover 형태 유지 → RE-PLAN 불요.
- [ ] RE-PLAN
