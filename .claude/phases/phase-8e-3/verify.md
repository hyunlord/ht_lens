# Phase 8e-3 — Verify (self) — v2.0 cutover

cutover(runtime env) + jsdom CI + schema-head debt + cross-doc RAG live + reflow smoke. **main 머지 = cutover(Stage 5, cross-verify PASS 후)**. 모든 값 실측, 최종 code commit `1fa0123` 이후 작성. git status는 phase 산출물만.

## 5-A. Automated checks
| Check    | Command | Result |
| -------- | ------- | ------ |
| Lint     | `uv run ruff check .` | **All checks passed!** |
| Format   | `uv run ruff format --check .` | **199 files already formatted** |
| Type     | `uv run mypy src/` | **Success: no issues found in 85 source files** |
| Test     | `uv run pytest -m "not llm and not slow"` | **781 passed, 1 skipped, 8 deselected** (725.30s) |
| jsdom (CI) | `npm ci` + `_find_jsdom` repo-local | 로컬 11 jsdom 테스트 RUN(skip 0); CI는 `npm ci` 단계로 동일 |
| CI | GitHub Actions | **8e-3 머지에서 첫 main 실행**(Stage 5 cutover서 green 확인) |

- 781 = 8e-2 종료 771 + 신규 10(test_cutover_8e3 9 + CLI schema-before-health 1). 회귀 0.

## 5-B. Functional checks

### cross-doc RAG live (DoD 핵심, 5-doc) — 실측
```
corpus: 2840 chunk vectors, dim=1024
query = doc5(Aggarwal) chunk 505, exclude_doc_ids={5}
cross-doc hits: 5 → chunk473/doc4(0.556), 439/doc4(0.542), 77/doc1(0.535), 372/doc4(0.53), 81/doc1(0.525)
→ doc_ids={1,4} (none == query doc 5)
```
- 8d-2b cross-doc 머신이 5-doc 실 데이터서 작동: 한 doc 질의 → **다른 doc** chunk 반환, exclude_doc_ids 동작 확인(반환 doc_id ≠ 질의 doc, verify-cross R-G 단언 형태).

### reflow smoke (5-doc) + root redirect — 실측 (TestClient, v2 DB)
```
2.0 root redirect: 307 -> /static/index.html
doc 1..5 reflow: 200 (chunks 103/40/196/162/3338)
```
- 5-doc 전부 reflow API 200 + 본문. root `/`→문서목록(2.0 기본 진입). (8e-2서 doc5 text 2330 중 한국어 2321 + suppressed 9 확인.)

### 롤백 = git-revert (live finding으로 재설계)
- **live**: 2.0 코드가 실 1.x(0004) DB serve 시 `/documents` 500(`documents.extractor` 등 2.0-only 컬럼) → env-flip-only 롤백 기술적 불가.
- **재설계(사용자 확정)**: guard **strict 0007**(0004/0003 등 non-head 거부 — `test_api_rejects_non_head_db`). 롤백 = **main 머지 revert**(0004 호환 1.x 코드 복원) + `HT_LENS_DB_URL→ht_lens.db`. **1.x DB 파일 불변**. `.env.example` 문서화.
- 오해성 합성 테스트(create_all로 2.0 스키마에 '0004' 스탬프) 정정 → non-head 거부 단언.

### schema-head debt + 안전 (verify-cross 반영)
- `retranslate_short`에 공유 `schema_guard.require_schema_head` 가드(8d-2c debt). CLI `--short-only`는 schema 체크 **health_check 전** → stale DB+LLM down = **exit 3**(`test_short_only_schema_mismatch_precedes_llm_health`).
- malformed `HT_LENS_DB_URL`(app+cli) **raise**(silent 1.x fallback 제거; `test_db_path_from_env_rejects_malformed_url` 4-param).

### jsdom CI provisioning
- `package.json`(jsdom 25.0.1, host parity) + `package-lock.json` + node_modules gitignore + ci.yml `npm ci` + `_find_jsdom` repo-local 경로(11 파일). → clean runner서 jsdom 테스트 RUN(skip 0).

### 1.x 무손상 (prod `data/ht_lens.db`)
```
alembic=0004  blocks=49850  chunk_tables=0
```
- 롤백 live 검증은 **복사본**(/tmp)으로 수행(lifespan이 jobs write → prod 미접촉). 모든 작업 env/별 DB.

## 5-C. New code-path lock (RE-CODE 가드)
| 새 코드 경로 | 잠금 테스트 |
| ------------ | ----------- |
| strict head guard(app lifespan) | `test_api_rejects_non_head_db`, `test_api_starts_on_2x_head` |
| root `/`→index redirect(root_path-aware) | `test_root_redirects_to_document_list` |
| `_db_path_from_env` malformed raise(app+cli) | `test_db_path_from_env_rejects_malformed_url`, `_empty_uses_default` |
| `schema_guard.require_schema_head` + retranslate_short 가드 | `test_require_schema_head_raises_on_stale` |
| CLI --short-only schema-before-health | `test_short_only_schema_mismatch_precedes_llm_health`(exit 3) |
| jsdom repo-local `_find_jsdom`(11 파일) | 기존 11 jsdom 테스트 green(repo-local 해석) |
- index.js doc-card→reflow.html: 기존 index JS 경로(렌더 회귀 없음, 781 green).

## 5-D. Scoring (100, self)
| Item | Score / Max | Evidence |
| ---- | ----------- | -------- |
| 독창성 | 12 / 15 | runtime-env cutover(코드/운영 분리) + 공유 schema_guard + live-finding 기반 롤백 재설계(env-flip 불가 입증→git-revert). (−3: 주로 운영/통합) |
| 완결성 | 32 / 35 | cutover guards + jsdom CI + debt + cross-doc live + reflow smoke + 10 테스트. (−3: GitHub CI 첫 main green은 Stage 5(머지) 후 확정; browser-level smoke는 API-level) |
| 안정성 | 28 / 30 | 781 green(회귀 0), strict guard + malformed raise + schema-before-health, 1.x 0004/49850/0 불변, 롤백=git-revert(파일 불변). (−2: 롤백은 코드 revert 필요 — env-flip-only 불가, 문서화) |
| 확장성 | 18 / 20 | jsdom CI로 JS 회귀 main 보호, env switch + 1.x 보존(deprecation). (−2: 1.x/2.0 코드 공존 deprecation 정리는 후속) |
| **Total** | **90 / 100** | |

## 5-E. Self verdict
- [x] **PASS_CANDIDATE (90)** → cross-verify Round 1. cutover guards 구현+검증, cross-doc live, 롤백 정직 재설계(git-revert), 781 green, 1.x 무손상. **main 머지는 cross-verify PASS 후 Stage 5**.
- [ ] FAIL → RE-CODE
- [ ] FAIL → RE-PLAN

### 잔여 / cutover 후 follow-up
1. **main 머지 + GitHub CI 첫 실행** = Stage 5(cross-verify PASS 후). CI red → 진단·hold.
2. 롤백 = git-revert(env-flip-only 불가, 문서화). 1.x deprecation 정리 = 후속.
3. browser-level reflow smoke(Playwright) = 후속(현 API-level 200 + index.js 경로).
4. book2 full 1370p(--timeout 내부 fix로 one-shot 가능) + 볼드(GPU) = cutover 후.
5. in-DB src_pdf_sha256 = manifest 보완(8e-2 carry).
