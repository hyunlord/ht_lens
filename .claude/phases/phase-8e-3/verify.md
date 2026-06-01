# Phase 8e-3 — Verify v2 (self, post verify-cross R1 RE-CODE) — v2.0 cutover

cutover(runtime env) + jsdom CI + schema-head debt + cross-doc RAG live + reflow smoke + doc-list page-count fix. **main 머지 = cutover(Stage 5, cross-verify PASS 후)**. 최종 code commit `4b9b00f` 이후 작성.

**v2 사유**: cross-verify R1(DOWNGRADE ~82, "guarded 2.0 cutover candidate, code mostly solid")이 §4#1 doc-list "0 pages" 회귀(실) + §4#3 docstring 과장 + 증거 갭 지적. §4#1/§4#3 fix, 나머지 disclosed.

## 5-A. Automated checks
| Check    | Command | Result |
| -------- | ------- | ------ |
| Lint     | `uv run ruff check .` | **All checks passed!** |
| Format   | `uv run ruff format --check .` | **199 files already formatted** |
| Type     | `uv run mypy src/` | **Success: no issues found in 85 source files** |
| Test     | `uv run pytest -m "not llm and not slow"` | **782 passed, 1 skipped, 8 deselected** (568.54s) |
| Coverage | routers/documents.py 신규 분기 | `test_2x_doc_page_count_from_chunks_not_zero` + live(아래) 로 잠금 |
| jsdom (CI) | `npm ci` + repo-local `_find_jsdom`(11) | 로컬 11 jsdom 테스트 RUN(skip 0); CI `npm ci` 단계 |
| CI | GitHub Actions | **8e-3 머지서 첫 main 실행**(Stage 5) |

- 782 = 8e-2 종료 771 + 신규 11(test_cutover_8e3 10 + CLI schema-before-health 1). 회귀 0.

## 5-B. verify-cross R1 resolution (DOWNGRADE ~82 → 처리)
| R1 | 판정 | 처리 (`4b9b00f`) | 증거 |
| -- | ---- | --------------- | ---- |
| §4#1 doc-list "0 pages"(2.0 doc는 Page rows 0) | **real(cutover UX 회귀)** | list+single 라우트에서 Page 0이면 distinct `chunk.page_idx`로 page 수 산출 | **live 5-doc: 11/6/21/27/503** (아래) + `test_2x_doc_page_count` |
| §4#3 schema_guard "every path" 과장(private copy 4개 잔존) | real(minor) | docstring을 "canonical reusable guard, 기존 private copy는 후속 정리"로 완화 | docstring |
| §4#2 upload→viewer.html(혼합) | 의도(1.x) | 웹 업로드는 1.x block 흐름 → viewer.html 정당(2.0은 CLI ingest). doc-card만 reflow | 코드 분리(index.js:64 vs 120-128) |
| §1 coverage/jsdom skip-0 | wording | documents.py 신규 분기 test+live; jsdom repo-local 해석(11 RUN) | — |
| §2 5-doc vs 7-doc / browser smoke / rollback drill / CI | disclosed | subphase(8e-2 Planner) / API-level+index.js / git-revert runbook / Stage 5 머지 | 5-E |

## 5-C. Functional checks

### doc-list page count — live, 실 5-doc v2 DB (§4#1 fix)
```
GET /documents (HT_LENS_DB_URL=v2):
  doc1 book2_ch28: num_pages=11   doc2 sample_mixed: 6   doc3 2503: 21
  doc4 2603: 27                   doc5 aggarwal: 503
```
- 2.0 doc 전부 실제 page 수(소스 PDF와 일치; Aggarwal 503=내용 있는 distinct page_idx). "0 pages" 회귀 해소.

### cross-doc RAG live (DoD 핵심, 5-doc)
```
corpus 2840 vec dim1024; query=doc5 chunk505, exclude {5}
→ 5 hits: doc4×3, doc1×2 (scores 0.52–0.56), none==doc5
```
- 8d-2b cross-doc 머신 live: 한 doc 질의 → 다른 doc chunk, exclude_doc_ids 동작.

### reflow smoke + root redirect (TestClient, v2)
```
root / → 307 /static/index.html;  doc1..5 reflow 200 (chunks 103/40/196/162/3338)
```

### 롤백 = git-revert (live finding 재설계) + runbook
- 2.0 코드가 실 1.x(0004) serve 시 `/documents` 500(2.0-only 컬럼) → env-flip-only 불가 입증. guard **strict 0007**(`test_api_rejects_non_head_db`).
- **Rollback runbook**: ① `git revert <merge-commit>` (0004 호환 1.x 코드 복원) → 재배포 ② `HT_LENS_DB_URL=sqlite+aiosqlite:///data/ht_lens.db` (또는 unset). **1.x DB 파일 불변**. `.env.example` 기재.
- (1.x 코드+0004 DB는 8e 이전 prod 상태 = 기검증; 새 drill 불요.)

### schema-head debt + 안전
- `retranslate_short` 공유 `require_schema_head` 가드; CLI `--short-only` schema **before** health → stale+LLM down = exit 3 (`test_short_only_schema_mismatch_precedes_llm_health`). malformed `HT_LENS_DB_URL` raise(app+cli, 4-param test).

### 1.x 무손상 (prod `data/ht_lens.db`)
```
alembic=0004  blocks=49850  chunk_tables=0
```
- 롤백 live는 **복사본**(/tmp)으로(lifespan jobs write → prod 미접촉).

## 5-D. Scoring (100, self v2)
| Item | Score / Max | Evidence |
| ---- | ----------- | -------- |
| 독창성 | 12 / 15 | runtime-env cutover + 공유 schema_guard + live-finding 롤백 재설계 + page-count fallback. (−3: 운영/통합 중심) |
| 완결성 | 30 / 35 | cutover guards + jsdom CI + debt + cross-doc live + reflow smoke + page-count fix + 11 테스트. (−5: GitHub CI green=머지 후, browser smoke=API-level+index.js, 5-doc subphase) |
| 안정성 | 28 / 30 | 782 green(회귀 0), strict guard + malformed raise + schema-before-health + page-count fix, 1.x 0004/49850/0 불변, 롤백 runbook. (−2: 롤백 drill은 머지 후/기검증, CI green 머지 후) |
| 확장성 | 17 / 20 | jsdom CI(JS 회귀 main 보호) + env switch + 1.x 보존. (−3: private schema-guard copies 후속 정리; 1.x deprecation) |
| **Total** | **87 / 100** | R1 82 → §4#1/§4#3 fix + live 증거 보강 |

## 5-E. Self verdict
- [x] **PASS_CANDIDATE (87)** → cross-verify Round 2(마지막). §4#1 실 회귀 fix(live 11/6/21/27/503) + §4#3 정정, cross-doc live, 롤백 runbook, 782 green, 1.x 무손상. **main 머지 = R2 PASS 후 Stage 5**.
- [ ] FAIL → RE-CODE
- [ ] FAIL → RE-PLAN

### 잔여 / cutover 후
1. **main 머지 + GitHub CI 첫 green** = Stage 5(R2 PASS 후). red→진단·hold.
2. browser-level reflow smoke(Playwright), private schema-guard copies 정리, 1.x deprecation = 후속.
3. book2 full 1370p(one-shot 가능) + 볼드(GPU) = cutover 후. 5-doc=v2.0 subphase(7-doc은 Planner supersede).
