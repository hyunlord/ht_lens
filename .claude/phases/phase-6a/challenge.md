# Phase 6a — Challenge

## Debate responses

### 1. Over-engineering

**SearchHit offset fields (`match_start`/`match_end`)** — **PARTIAL accept**
응답: offset 필드 제거. preview에 `<mark>` 인라인 마크업. client는 안전 파싱 (DOMPurify 이미 vendor).
**결정**: SearchHit = `{doc_id, doc_filename, page_num, block_id, block_local_id, type, matched_field, preview}`.

**Retranslate UI 분산** — **ACCEPT**
응답: contextmenu만 단일 trigger. chat_panel 버튼 제거. confirm modal 1개 유지.

**FTS5 → Phase 6b 미룸 정당성 부족** — **PARTIAL accept**
응답: DoD "200ms for 10K blocks"는 Phase 6a에 명시. 10K 합성 fixture 측정 → LIKE 통과면 유지, 미달이면 즉시 본 phase 안에서 FTS5 도입. Phase 6b로 미룬다는 표현 reject.

### 2. Hidden assumptions

**LIKE 10K latency 미검증** — **ACCEPT**
응답: pytest fixture로 10K row INSERT + LIKE 측정. verify에 실측치 인용.

**Export `<a download>` 트릭 에러 surface 불가** — **ACCEPT**
응답: `fetch` + `Blob` + `URL.createObjectURL` 패턴. ApiError catch + toast.

**Cmd+K from input/textarea 안 됨** — **ACCEPT**
응답: `attachKeyboard()` early return 분기에 Cmd+K 예외. Esc 우선순위: searchOpen → closeSearch (return), 아니면 panelOpen → closePanel.

**Export message content "그대로"** — **ACCEPT**
응답: assistant content는 markdown 포함 가능 → blockquote (`> ` line prefix). user content도 동일. outer 구조 보호.

### 3. Edge cases

**양쪽 필드 match 시 offset 모호** — **ACCEPT** (§1과 함께)
응답: backend가 original first → translated 우선순위로 결정. preview에 `<mark>` 첫 occurrence.

**`block` URL param + bootstrap 순서** — **ACCEPT**
응답: viewer.js `parseQuery`에 `block` 추가. `loadAndRender` 후 `block` 있으면 `openPanel({blockId, docId})` + scrollIntoView. panel restore 후처리.

**Retranslate desync with open chat panel** — **ACCEPT**
응답: retranslate 응답 직후 `currentPage.blocks[].translated_text` + `threadDetailById[]?.block.translated_text` 둘 다 갱신. `repaintPage()` + `repaintPanel()` 호출.

**Concurrent retranslate vs CLI translate** — **REJECT (문서화)**
응답: 단일 사용자 도구. Phase 6c row-level lock 검토. 알려진 한계.

### 4. Alternative approaches

**FTS5 immediate** — **PARTIAL accept** (§1, §2 통합)

**Shared retranslate service** — **REJECT**
응답: `_process_block`은 batch retry/semaphore/in-memory cache/skip 복잡. retranslate는 단일 block × 강제 새 호출이라 의도가 다름. 새 router에 `make_cache_key` + LLM + upsert 인라인 (~20줄 중복). 공유 추출은 over-engineering.

**fetch + Blob for export** — **ACCEPT** (§2와 함께)

### 5. Missing tests

**`test_search_10k_blocks_meets_latency_budget`** — **ACCEPT**
응답: 1만 row INSERT fixture + LIKE 측정 + assert < 200ms.

**`test_keyboard_cmd_k_works_from_chat_textarea_and_escape_closes_search_first`** — **ACCEPT (grep)**
응답: keyboard.js의 Cmd+K early-return 예외 + Esc 우선순위 코드 grep. viewer.js 실행 단위 테스트는 jsdom 필요 → grep으로 잠금.

**`test_search_result_block_param_restores_target_block_after_navigation`** — **ACCEPT (grep)**

**`test_search_translated_only_match_builds_correct_preview_span`** — **ACCEPT**
응답: blocks original 미매치 + translated 매치 → `matched_field == "translated"` + preview에 `<mark>`.

**`test_retranslate_transient_llm_error_returns_502_and_preserves_existing_translation`** — **ACCEPT**
**`test_retranslate_failed_llm_call_writes_no_partial_row`** — **ACCEPT**
응답: Phase 3 atomicity 패턴 동일. LLM 호출 먼저, 성공 시만 commit.

**`test_export_markdown_fences_assistant_markdown_content`** — **ACCEPT**
**`test_export_markdown_handles_multiline_original_and_translated_text`** — **ACCEPT**
응답: `# heading`, ``` 포함된 assistant content → 모든 라인이 `> `로 시작. 멀티라인 original/translated도 동일 prefix.

---

## Plan revisions (after debate)

1. **SearchHit 슬림화** — `match_start`/`match_end` 제거 + preview에 `<mark>` 인라인.
2. **Retranslate trigger 단일** — contextmenu만.
3. **10K latency 측정** — pytest fixture; 미달 시 본 phase 안 FTS5 도입.
4. **Export 다운로드** — fetch + Blob + toast error.
5. **Keyboard Cmd+K from input + Esc 우선순위** — keyboard.js 보강.
6. **Export message content** — line별 `> ` blockquote prefix.
7. **`block` URL param** — viewer.js parseQuery + 후처리.
8. **Retranslate after-effect 정합성** — page + panel 둘 다 repaint, threadDetailById 갱신.
9. **테스트 8건 추가** — 위 §5 항목.
10. **Concurrent retranslate race** — 문서화만.

---

## DoD checklist

| DoD item | Status | Evidence |
| -------- | ------ | -------- |
| Cmd+K로 임의 문구 찾고 점프 (< 200ms, 10K blocks) | planned | 10K fixture latency test + verify 측정 + screenshots 1-3 |
| 질문 export markdown 받기 + 사람이 읽기 좋음 | planned | fetch+Blob + blockquote safety tests + screenshots 4-5 |
| block 우클릭 → 재번역 → 갱신 | planned | contextmenu + upsert atomicity + UI sync + screenshots 6-7 |

---

## Risk register

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| 10K LIKE > 200ms | Medium | DoD 미달 | 합성 fixture 사전 측정, 미달 시 본 phase FTS5 즉시 도입 |
| Export nested fence 깨짐 | Low | UX | blockquote prefix + 2 safety tests |
| Retranslate UI desync | Medium | 데이터 정합성 | repaintPage + repaintPanel + threadDetailById 갱신 + test |
| Concurrent retranslate race | Low | 단일 사용자 가정 | 문서화, Phase 6c |
| Cmd+K conflict with browser default | Low | UX | preventDefault |
| Mobile contextmenu 없음 | Medium | UX | 알려진 한계, Phase 6c long-press |
| LLM permanent error in retranslate | Low | UI block | 502 + retry 버튼 (Phase 5 pattern) |

---

## Decision

- [x] PASS → proceed to code (plan revisions 10건 적용)
- [ ] RE-PLAN

Codex 14 비판 중 11 ACCEPT + 2 PARTIAL ACCEPT + 1 REJECT (shared service). Plan revision 10건 반영하여 코드 진입.
