# Phase 8e-3 — Summary (cutover + CI + debt) — **v2.0 마일스톤**

## Status
**PASS_CANDIDATE → CUTOVER (Planner 승인)**. cross-verify R2 **DOWNGRADE 84-85**이나 Codex 명시 "I would not reject this phase" — 실 결함 전부 fix, 잔여 downgrade는 **구조적 pre-merge 불가**(CI green은 main 머지가 첫 실행) + disclosed scope(browser smoke, 7-doc). 2-round cap. **Planner가 main 머지 cutover 승인** → Stage 5 머지 + GitHub CI 첫 실행.

## Score
- Self verify v1 `e6ea9ed`(90) → v2 `2b17a1e`(87, post R1 RE-CODE)
- Cross R1 `e720867`: **DOWNGRADE ~82**(§4#1 doc-list "0 pages" 회귀, §4#3 docstring 과장) → RE-CODE
- Cross R2 `114cd43`(최종/cap): **DOWNGRADE 84-85, "would not reject"**(§4 sparse-page edge → post-R2 micro-fix; 잔여는 post-merge/disclosed)

## What was built
- **cutover = runtime env**(사용자): 코드 `_DEFAULT_DB` 1.x 중립, 배포 `HT_LENS_DB_URL=v2`. `.env.example` 문서화.
- **root `/` → `/static/index.html`**(2.0 문서목록 기본 진입, root_path-aware). index.js doc-card → reflow.html?doc=.
- **strict schema head(0007)**: 2.0 코드가 실 1.x(0004) serve 시 `/documents` 500(2.0-only 컬럼) live 입증 → env-flip-only 롤백 불가. **롤백 = git revert main(0004 호환 1.x 코드) + env**, 1.x 파일 불변.
- **malformed `HT_LENS_DB_URL` raise**(app+cli; silent 1.x fallback 제거).
- **schema-head debt**: 공유 `db/schema_guard.require_schema_head` → `retranslate_short`; CLI `--short-only` schema **before** health(exit 3).
- **jsdom CI provisioning**: `package.json`(jsdom 25.0.1)+lock+gitignore+ci.yml `npm ci`+`_find_jsdom` repo-local(11). → 11 jsdom 테스트 CI RUN.
- **doc-list page count(2.0)**: Page rows 0이면 `max(chunk.page_idx)+1`(blank-middle-page 포함). cutover "0 pages" 회귀 해소.

## live 검증 (5-doc v2 DB)
- **cross-doc RAG live**: doc5 질의/exclude{5} → doc4×3+doc1×2 hits(none==5). 8d-2b 머신 multi-doc 작동.
- **reflow smoke**: root /→307 index.html; doc1-5 reflow 200(chunks 103/40/196/162/3338).
- **doc-list page count**: 11/6/21/27/515(소스 PDF 일치, "0 pages" 없음).
- **1.x 무손상**: prod 0004/blocks 49850/chunk_tables 0(롤백 live는 복사본으로 prod 미접촉).

## Code changes (challenge `45e6a45` → HEAD; +377/-15)
```
 api/app.py            root redirect + strict head guard + malformed raise
 api/routers/documents.py  2.0 page count = max(page_idx)+1
 db/schema_guard.py    신규 공유 가드
 cli.py                malformed raise + schema-before-health
 translate/short_retranslate.py  schema 가드(8d-2c debt)
 api/static/js/index.js  doc-card → reflow
 package.json/lock + ci.yml + .gitignore + .env.example  jsdom CI + cutover env
 tests: test_cutover_8e3(10) + short_retranslate_cli(schema-before-health) + 11 jsdom(_find_jsdom)
```
테스트: 8e-2 종료 771 → **782**(+11) fast green. ruff/format/mypy(85) clean.

## R1/R2 resolution
| 지적 | 판정 | 처리 |
| ---- | ---- | ---- |
| R1 §4#1 doc-list "0 pages" | real 회귀 | `4b9b00f` chunk.page_idx fallback (+R2 `6c3dc02` max+1 sparse) + test |
| R1 §4#3 schema_guard 과장 | real(minor) | docstring 완화 |
| R2 §4 sparse page(blank middle) | real(edge) | distinct→max+1, sparse test(0,0,2→3) |
| CI green / rollback drill | **post-merge 불가** | CI는 main 머지가 첫 실행; rollback drill은 머지 후 |
| browser smoke / 7-doc DoD | disclosed | Playwright=후속; 5-doc=Planner subphase, book2 full=cutover 후 |
| upload→viewer.html | 의도(1.x) | 웹 업로드는 1.x block 흐름 |

## Evidence index
- plan `babd1f8` / debate `37b6242`(Codex) / challenge `45e6a45`(PASS: rollback allow-list→정정, hardening)
- feat `516fcf2` + jsdom `df3cf14` + test `8ef4222` → **롤백 재설계 `1fa0123`**(live finding) → verify v1 `e6ea9ed`(90) → **cross R1 `e720867`(82)** → RE-CODE `4b9b00f` → verify v2 `2b17a1e`(87) → **cross R2 `114cd43`(84-85, "would not reject")** → R2 micro-fix `6c3dc02`
- 실측: ruff/format/mypy clean, **782 passed**, cross-doc live(doc5→1,4), reflow 5/5 200, page count 11/6/21/27/515, prod 0004/49850/0.

## Cutover 절차 (Stage 5)
1. `git checkout main && git merge prototype-reflow` (Phase 8 전체 = 135 commits)
2. `git push origin main`
3. **GitHub CI 첫 main 실행** watch — jsdom+pytest+ruff+mypy green 확인
4. green = **ht_lens 2.0** ✅ / red = 진단 + hot-fix 또는 `git revert`(롤백 자산)

## Rollback (cutover 후)
- env: `HT_LENS_DB_URL=sqlite+aiosqlite:///data/ht_lens.db` (또는 unset) — **단, 2.0 코드는 0004 route 500** → 코드 롤백 필요.
- code: `git revert <merge>` → 0004 호환 1.x 코드 복원 + 위 env. **1.x DB 파일 불변.**

## Known issues / debt (cutover 후 follow-up)
1. browser-level reflow smoke(Playwright).
2. private `_require_schema_head` copies(ingest/translate) → 공유 helper 통일.
3. 1.x 코드 deprecation 정리.
4. book2 full 1370p(`--timeout` 내부 fix로 one-shot 가능) + 볼드(GPU 결정).
5. in-DB src_pdf_sha256(8e-2 manifest 보완) / WORKFLOW Regression-check 표 형식.

## 🎉 v2.0
8a~8e-3 완료: MinerU 추출 + chunk 번역(math 강건화) + reflow viewer + chat/RAG/figure/섹션Q + neighbor 재번역 + 5-doc 마이그레이션 + cutover. **ht_lens 2.0 = 학술 PDF 한국어 reflow 번역·열람·RAG 도구.**
