# Phase 8e-3 — Plan (cutover + CI + debt) — 8e 시리즈 3/3, **v2.0 마일스톤**

## 8e 컨텍스트
8e-1(math 강건화) ✅, 8e-2(5-doc 마이그레이션, 99.77%) ✅ push(`3dfc964`). 이 phase = prod cutover + 마무리. 완료 시 **ht_lens 2.0**.

## Goal
2.0를 prod 기본으로 cutover(runtime env), CI에서 jsdom 테스트 작동, schema-head debt 통일, cross-doc RAG live + reflow smoke 검증, prototype-reflow → main 머지로 GitHub CI 첫 main 실행. **1.x DB 파일 절대 불변(즉시 롤백)**.

## Stage 0 실측 (확정)
- DB 기본: `_DEFAULT_DB=data/ht_lens.db`(1.x) in app.py:46 + cli.py:27. `.env`(gitignore)에 HT_LENS_DB_URL 없음. `_db_path_from_env()`가 env→경로, 없으면 1.x. `load_repo_dotenv()`로 `.env` 로드. `_DEFAULT_DB` 참조 테스트 0(flip 안전하나 — **사용자 결정: 코드 불변**).
- 라우터: 1.x(documents/pages/blocks/...) + 2.0(reflow/chunk_chat) 전부 co-mount. **served DB가 어느 viewer 데이터 작동하는지 결정**. **root `/` 라우트 없음**(현 404; reflow.js는 `?doc=<id>` 필요).
- CI: `.github/workflows/ci.yml` Node 22 셋업 있음, **package.json 없음** → 16 jsdom 테스트가 `_find_jsdom()`(host 경로만) → CI에서 skip.
- schema-head: `chunk_pipeline.translate_chunks`는 `_require_schema_head`(83) 경유. **`short_retranslate.retranslate_short`(8d-2c `--short-only`)는 미경유**(debt).
- cross-doc: `embedding/chunk_search.search_chunks(exclude_doc_ids=...)` + `chunk_chat_context.build_cross_doc_chunk_refs`(8d-2b). 5-doc 임베딩(2840) 적재됨.
- 5-doc 2.0 DB(0007, 3839/3830/2840), 1.x prod(0004/49850/0) 무손상. 771 tests green.

## 사용자 결정 (확정)
- **cutover = runtime env만**: 코드 `_DEFAULT_DB` 1.x 유지(중립), 배포 `.env`/systemd에 `HT_LENS_DB_URL=...ht_lens_v2.db`. 롤백 = env flip. (코드/운영 분리; 테스트는 1.x 기본 유지 → prod 2.0 미접촉).
- **root `/` → reflow.html 리다이렉트**(기본 진입 2.0; 직접 경로 유지).
- 1.x 코드 = 보존(deprecation, 삭제는 후속). CI 실패 = 진단·머지 hold.

## Scope
**In (8e-3)**
- **A. root redirect**(code): `@app.get("/")` → `/static/reflow.html`(RedirectResponse). 직접 viewer.html/reflow.html 경로 불변(1.x 롤백 접근).
- **B. jsdom CI provisioning**(code): repo-root `package.json`(jsdom devDep) + `package-lock.json` + ci.yml `npm ci` 단계. `_find_jsdom()`에 **repo-local `node_modules/jsdom`** 경로 추가(16 파일 — 동일 함수면 일괄, 아니면 공유 헬퍼). → 16 jsdom 테스트 CI서 skip 안 함.
- **C. schema-head 가드 통일**(code, 8d-2c debt): `retranslate_short`(또는 CLI `--short-only` 분기)에 `_require_schema_head` 추가 → 구버전 DB서 clean `SchemaVersionMismatch`(exit 3). +test.
- **D. cutover 운영 문서**(committed): `.env.example`에 `HT_LENS_DB_URL` 항목 + cutover/rollback 런북(summary). 실제 `.env` 전환은 ops(gitignore, 미커밋).
- **E. 검증(머지 전)**: cross-doc RAG live(5-doc: doc A 질문 → doc B ref), reflow smoke(5-doc HTTP 200 + 본문), 1.x 롤백(env→1.x 작동), 1.x DB 불변(49850), 전체 suite + jsdom green.
- **F. main cutover**: prototype-reflow → main 머지, push, **GitHub CI 첫 main 실행** green 확인. CI red → 진단·hold.

**Out**
- `_DEFAULT_DB` 코드 변경(사용자: 운영 env). prod DB 파일 승격/교체. 1.x 코드 삭제(보존). book2 full 1370p·볼드 = cutover 후 follow-up. 웹/논문 = 8f.

## Approach
- **A**: app.py에 root 라우트 1개. `RedirectResponse("/static/reflow.html")`. (reflow.html `?doc=` 필요 — doc-picker는 scope 밖; redirect만.)
- **B**: `package.json`에 jsdom 고정 버전(host venv = jsdom 사용 중인 버전 정합). ci.yml: setup-node 후 `npm ci`. `_find_jsdom` 후보에 `Path(__file__).parents[N]/"node_modules"/"jsdom"`(repo-local) 선두 추가. 동일 함수 여부 확인 후 일괄 edit 또는 conftest 공유 헬퍼.
- **C**: `retranslate_short` 시작에 `_require_schema_head(session)` 호출(chunk_pipeline 것 재사용/공유). CLI `--short-only`서 SchemaVersionMismatch→exit 3 통일. mock-DB 구버전 테스트.
- **D**: `.env.example`에 주석+키. 런북 = summary "Cutover 절차/롤백".
- **E/F**: verify 단계 + 머지.

## File-level changes (예상)
| Path | Action | Note |
| ---- | ------ | ---- |
| `src/ht_lens/api/app.py` | 수정 | root `/` → reflow redirect |
| `src/ht_lens/translate/short_retranslate.py` 또는 `cli.py` | 수정 | schema-head 가드(C) |
| `package.json` + `package-lock.json` | 신규 | jsdom devDep(B) |
| `.github/workflows/ci.yml` | 수정 | npm ci 단계(B) |
| `tests/integration/test_*_js.py` (16) | 수정 | `_find_jsdom` repo-local 경로(B) |
| `.env.example` | 수정 | HT_LENS_DB_URL 항목(D) |
| `tests/...` | 신규 | root-redirect / schema-head guard / (cross-doc는 8d-2b 기존) |

## Dependencies (new)
| Package | Why |
| ------- | --- |
| jsdom (npm devDep) | CI서 8c/8d JS 테스트 실행(이미 host서 사용 중, 버전 정합) |

## Test strategy
- root redirect: TestClient `GET /` → 307/308 → `/static/reflow.html`.
- schema-head 가드: 구버전(예: 0004) DB에 `--short-only`/`retranslate_short` → `SchemaVersionMismatch`(CLI exit 3). mock/temp DB.
- jsdom CI: `_find_jsdom`가 repo-local node_modules 인식(npm ci 후 16 테스트 non-skip). 로컬 `npm ci` + pytest jsdom 그룹 green.
- cross-doc RAG: 8d-2b 기존 단위(2-doc fixture) green + **live 5-doc 검증**(verify evidence).
- reflow smoke: 5-doc `/v2/.../reflow` HTTP 200 + translated 본문(verify evidence).
- 1.x 롤백: HT_LENS_DB_URL=1.x → 1.x viewer/blocks 작동, blocks 49850 불변.
- 회귀 771 + 신규 + jsdom(CI). ruff/format/mypy clean.

## DoD mapping
| DoD item | How | Evidence |
| --- | --- | --- |
| cutover(2.0 기본, 즉시 롤백) | runtime env + root redirect | .env.example + 런북 + 롤백 검증 |
| jsdom CI 작동 | package.json + ci.yml + _find_jsdom | npm ci + 16 테스트 non-skip + GitHub CI green |
| schema-head debt | retranslate_short 가드 | exit 3 테스트 |
| cross-doc RAG live | 5-doc search_chunks | doc A→doc B ref 실증 |
| reflow 전체 읽기 | 5-doc smoke | HTTP 200 + 본문 |
| 1.x 무손상/롤백 | env flip, 파일 불변 | blocks 49850, env→1.x 작동 |
| GitHub CI 첫 main | main 머지 | gh run green |

## 위험 / 완화
- **1.x DB 파일 변경(절대 금지)** → 모든 작업 env/별 DB, 머지 전후 blocks 49850 재확인. cutover는 env만.
- **GitHub CI 첫 main 실패**(jsdom/환경) → 로컬서 npm ci + jsdom 먼저 green, ci.yml 정합 확인 후 머지. 실패 시 진단·hold(머지 되돌림 아닌 hot-fix).
- env 전환 누락 경로(CLI/서버/테스트) → 서버=`_db_path_from_env`(env), CLI=`--db`/env, 테스트=api_db_path/tmp(중립). root redirect는 DB 무관.
- main 머지 충돌(1.x 보존) → prototype은 1.x 위 additive(2.0 신규 파일+additive migration), 충돌 최소. 보존 머지.
- cross-doc 5-doc scale → chunk<block, in-memory 행렬 충분(8d-2b 검증).
- reflow `?doc=` 없는 root → redirect는 reflow.html로(doc-picker는 follow-up; 직접 `?doc=` 동작).

## 결정 필요 (해결됨)
- cutover=runtime env(확정). root→reflow(확정). 1.x 보존(확정). CI red=진단·hold(확정).
