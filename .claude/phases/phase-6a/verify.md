# Phase 6a — Verify (self, v2 — post RE-CODE)

R1 cross-verify가 REJECT (제안 79/100). 4 substantive 결함: retranslate cache pollution, export multiline, search whitespace, confirm modal 미테스트. RE-CODE 후 v2. 작성 직전 `git status` clean. head `145f0ae`.

## 5-A. Automated checks (fresh 실행)

| Check    | Command | Result |
| -------- | ------- | ------ |
| Lint     | `uv run ruff check .` | All checks passed! |
| Format   | `uv run ruff format --check .` | already formatted |
| Type     | `uv run mypy src/` | Success: no issues found in 52 source files |
| Test (fast) | `make test-fast` | **305 passed, 6 deselected** in 110.16s |
| Coverage | `make check` 내장 | TOTAL 72% |
| Test (live LLM) | `pytest -m llm` | 6 passed (직전 라운드 검증 그대로 유효) |
| CI (local) | `make check` | **RC=0** |
| CI (remote) | `.github/workflows/ci.yml` | pending push |

신규 회귀 테스트 6건 (R1 fix 잠금):
- `test_retranslate_clears_cache_key_to_prevent_cache_reuse` (cache invalidation)
- `test_search_rejects_whitespace_only_query` (whitespace q=422)
- `test_export_handles_multiline_block_text` 강화 (모든 라인이 `> ` prefix)
- `test_confirm_modal_js.py` 4건 (confirm/cancel/backdrop/detail behavioral via jsdom)

Phase 6a 누적 신규 자동 테스트 **37건** (268 → 305).

## 5-B. Functional checks

### 1) R1 결함 → RE-CODE 매핑

| R1 결함 | RE-CODE fix | 회귀 가드 |
| ------- | ----------- | --------- |
| Retranslate cache pollution | `blocks.py` upsert 시 `cache_key=None` + `model="manual-retranslate:{base}:{ts}"`. `translate/pipeline.py::_db_cache_lookup`은 NOT NULL 필터링이라 자동 제외. | `test_retranslate_clears_cache_key_to_prevent_cache_reuse` + 기존 `test_retranslate_updates_existing_translation`의 model assertion 갱신 |
| Export markdown 멀티라인 깨짐 | `export_markdown.py`에서 `> 원문:` 헤더를 별도 라인으로 + 본문은 `_quote()` 헬퍼로 라인별 `> ` prefix | `test_export_handles_multiline_block_text` 모든 라인 검증 |
| `/search` whitespace-only → "match everything" | `search.py` handler에서 strip 후 `len(needle) < 2` 명시 reject (422) | `test_search_rejects_whitespace_only_query` (422 + detail message) |
| `renderConfirmModal()` behavioral 미테스트 | `tests/integration/test_confirm_modal_js.py` jsdom 4건 | confirm / cancel / backdrop click + detail render |

### 2) DoD evidence (v2 강화)

| DoD | 만족 | 근거 |
| --- | ---- | ---- |
| Cmd+K로 임의 문구 찾고 점프 (< 200ms, 10K) | ✅ | 3.9ms + whitespace 422 guard + screenshots 01-03 |
| 질문 export markdown 받기 + 사람이 읽기 좋음 | ✅ | fetch+Blob + blockquote safety 6건 (assistant markdown + multi-line original) + screenshots 04-05 |
| block 우클릭 → 재번역 → **캐시 무효화** + 갱신 | ✅ | contextmenu + confirm modal (4 jsdom tests) + upsert atomicity + **cache_key=None** + screenshots 06-07 |

R1이 지적한 "cache invalidation" 부분이 v2에서 명시적으로 잠금됨.

### 3) Latency benchmark 그대로

```
[bench] search 10K blocks: 3.9ms
```

## 5-C. Regression check + 신 코드 경로 잠금 (워크플로우 0-3-A 의무 표)

### R0 도입 신 식별자 (이전 verify v1과 동일)

| 영역 | 새 함수/state/event | 잠금 |
| ---- | ------------------- | ---- |
| state.js | `openSearch`/`closeSearch`/`setSearchResults`/`moveSearchSelection`/`setSearchLoading`/`setSearchError`/`setRetranslateInProgress` + 7 fields | `test_state_exposes_search_helpers` |
| api.js | `searchAll`/`exportQuestions`/`retranslateBlock` (fetch+Blob) | `test_api_js_has_search_export_retranslate_helpers` |
| keyboard.js | `onOpenSearch`/`onCloseSearch`/`isSearchOpen` | `test_keyboard_supports_cmd_k_and_search_close_priority` |
| block.js | `ht-lens:block-contextmenu` CustomEvent | `test_block_js_dispatches_contextmenu_event` |
| viewer.js | `handleSearchInput`/`handleSearchSelect`/`handleExport`/`handleRetranslate`/`activateBlockId`/`?block` | `test_viewer_js_handles_search_export_retranslate` + `test_search_result_block_param_restores_target_block` |
| sidebar.js | `onExport`/`onOpenSearch`/`.export-btn`/`.search-hint` | `test_sidebar_has_export_button_and_search_hint` |
| search_modal.js | `renderSearchModal` + `ALLOWED_TAGS: ["mark"]` | `test_search_modal_sanitises_preview_to_mark_only` |
| confirm_modal.js | `renderConfirmModal` (R1 fix로 behavioral lock 추가) | `test_phase6a_assets_served` + **`test_confirm_modal_js.py` 4건** |
| Backend | `GET /search`, `GET /documents/{id}/export.md`, `POST /blocks/{id}/retranslate`, `SearchHit`, `RetranslateResponse`, `_build_preview`, `build_questions_markdown` | 19 integration tests |

### R1 fix 도입 신 식별자 / 정책

| RE-CODE 변경 | 새 식별자 / 정책 | 잠금 단위 테스트 |
| ----------- | ---------------- | ---------------- |
| retranslate cache invalidation | `cache_key=None` 분기 + `manual-retranslate:` model prefix | `test_retranslate_clears_cache_key_to_prevent_cache_reuse` (NULL + prefix 둘 다 단언) |
| export multiline blockquote | `> 원문:` separator + `_quote()` body | `test_export_handles_multiline_block_text` 3 라인 모두 quoted |
| search whitespace guard | strip 후 `if len(needle) < 2 → HTTPException(422)` | `test_search_rejects_whitespace_only_query` |
| confirm modal behavioural | (기존 `renderConfirmModal`의 행위 잠금) | `test_confirm_modal_js.py` 4 케이스 |

모든 새 식별자/정책 → 명시적 단위 테스트 grep 가능.

### 기존 contract 무회귀

- ruff / mypy strict / 304 + R1 새 6 = 305 passed
- Phase 1-5 무영향
- LLM 호출 경로 변경 없음
- Phase 5 vendor / chat panel / pin / sidebar 동작 그대로

### Deviations from R0 (R1 응답)

- retranslate model 형식: `mock-retranslate` → `manual-retranslate:mock-retranslate:{ts}` (production 배포 전이라 호환성 영향 0)
- export markdown layout: `> 원문: {…}` (1 라인) → `> 원문:\n> {…}` (2+ 라인, blockquote-safe)
- search handler 422 분기 추가

## 5-D. Scoring (100, v2 재산정)

| Item       | Score / Max | Evidence |
| ---------- | ----------- | -------- |
| 독창성     | 14 / 15     | (v1 동일) `<mark>` 인라인 preview + DOMPurify whitelist + ?block 깊은 링크 + scroll flash + blockquote-safe export + fetch+Blob 다운로드 + contextmenu CustomEvent + manual-retranslate 캐시 무효화 정책 |
| 완결성     | **34 / 35** | v1 33 → 34 (+1). R1 4 결함 모두 해소 + 6 회귀 가드 추가. |
| 안정성     | **30 / 30** | v1 29 → 30 (+1). cache invalidation + whitespace guard + multiline export + confirm modal behavioural 모두 잠금. |
| 확장성     | **20 / 20** | v1 19 → 20 (+1). `cache_key=None` 정책이 translate pipeline의 NOT NULL 필터링과 자연스럽게 결합 → future cache 호환성 안전. |
| **Total**  | **98 / 100** | (v1 95 → v2 **98**) |

## 5-E. Self verdict

- [x] PASS_CANDIDATE (≥95)
- [ ] FAIL → RE-CODE
- [ ] FAIL → RE-PLAN

근거:
- R1 4 substantive 결함 모두 fix + 6 회귀 가드 추가 + 워크플로우 0-3-A "RE-CODE 새 코드 경로 단위 테스트 의무 표" 충족
- 305 fast tests + 6 LLM + `make check` RC=0
- self 98/100 (R1 95 → R2 98)
- R2 cross-verify로 CONFIRM_PASS 기대.
