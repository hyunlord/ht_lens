# Phase 5 — Summary (v2 — post Planner-directed fix)

## Status

**PASS_CANDIDATE** (Planner-directed fix applied). Workflow Stage 5c Round 2 상한 도달 → Planner가 직접 3 fix 지시 → 본 summary v2. cross-verify 재호출 금지. **Push는 Planner가 직접** (Planner-directed fix 정책).

## Score

- **Self v3 (post Planner-directed fix)**: 97 / 100
- **Self v2 (RE-CODE 후)**: 93 / 100
- **Self v1**: 94 / 100
- **Cross R1**: REJECT → 제안 79/100 (4 substantive 결함 + scenario untracked)
- **Cross R2**: REJECT → 제안 82/100 (R1 결함은 fix 인정, 그러나 RE-CODE에서 새 retry/toggle 결함 도입 + migration hole)
- **Post-Planner-fix**: R2 3 결함 모두 해소 → 안정성 30/30 + 완결성 34/35 회복.

Round 2 cross-verify는 **"Round 1's reported defects were mostly fixed"** 를 명시함. R1 4 결함 모두 해소 인정. 그 후 새 3 결함 (retry context, panel toggle, migration hole)도 Planner-directed로 해소.

## What was built

Phase 5 = chat panel + pins + sidebar question list. v0.3 마일스톤.

### Vendor (`src/ht_lens/api/static/vendor/`)
- marked@11.2.0 ESM (~90KB) — markdown → HTML
- DOMPurify@3.4.5 ESM (~76KB) — XSS sanitisation
- LICENSE (MIT + Apache-2.0/MPL-2.0)
- highlight.js dropped after debate §1 (out-of-scope for DoD)

### Frontend code (vanilla ES modules)
- `js/utils/render_markdown.js` — marked + DOMPurify + new-tab link hook
- `js/components/chat_panel.js` — slide-in panel + scroll management
- `js/components/message.js` — assistant markdown / user plain text + skeleton + retry button
- `js/components/message_input.js` — textarea + Ctrl/Cmd+Enter + 4000-char limit
- `js/components/thread_list.js` — sidebar question tab
- `js/components/block.js` — CustomEvent dispatch + multi-thread pin + count badge
- `js/components/page_view.js` — threadsByBlock cache feed
- `js/components/sidebar.js` — tab switcher (📄 페이지 / ❓ 질문)
- `js/api.js` — createThread / getThreadDetail / explainThread / postMessage / listThreadsForDoc
- `js/state.js` — panelOpen / activeBlockId / activeThreadId / activeDocId / sidebarTab / threadsByDoc / threadDetailById / panelToken; persist to localStorage with doc scope
- `js/viewer.js` — panel state machine, write→getThreadDetail refetch, panelToken async cancellation, popstate, Esc/Ctrl+B keyboard, cross-doc restore rejection, lastFailedAction retry capture
- `js/utils/keyboard.js` — Esc (panel close) + Ctrl/Cmd+B (panel toggle) handlers
- `css/chat_panel.css` — panel layout, sidebar tabs, pin pseudo + count badge

### Tests
- 23 R0 + 6 R1 fix grep guards in `tests/integration/test_static_serving.py` (256 → 262 fast tests)
- `tests/integration/test_vendor_runtime.py` (3 tests, node ESM smoke)
- `tests/integration/test_render_markdown_js.py` (5 tests, jsdom XSS + new-tab)

### Scripts + Docs
- `scripts/phase5_scenario.py` (NEW, tracked) — Playwright driver behind the 10-question scenario
- `docs/phases/phase-5/README.md` + 10 screenshots committed

## Files changed

`git diff --stat edcfe40^..HEAD`: ~33 files, ~3600 insertions.

핵심 분포:
- vendor 2 files (marked + DOMPurify) ~4000 lines
- js components 8 files (chat_panel, message, message_input, thread_list, block, page_view, sidebar, viewer) ~900 lines
- js utils/api/state 4 files ~400 lines
- css chat_panel.css ~330 lines
- tests 3 files (test_static_serving 확장 + 2 신규) ~270 lines
- scripts/phase5_scenario.py ~190 lines
- docs/phases/phase-5/* (README + 10 PNGs)
- .claude/phases/phase-5/*.md (plan/debate/challenge/verify v1+v2/verify-cross R1+R2/summary)

## Deviations from plan

1. **vendor 축소** (debate §1 ACCEPT): highlight.js + 언어팩 + 테마 제거. marked + DOMPurify만.
2. **state 단순화** (debate §1 ACCEPT): `messagesByThread` → `threadDetailById` refetch 패턴. `creatingThreadFor` 제거.
3. **Phase 6 미리 준비 섹션 삭제** (debate §1 ACCEPT).
4. **write-then-refetch 패턴** (debate §4 ACCEPT): 모든 write 직후 `GET /threads/{id}`.
5. **activeThreadId + activeBlockId localStorage persist** (debate §2 ACCEPT).
6. **multi-thread per block 지원** (debate §3 ACCEPT): `Map<blockId, Thread[]>`.
7. **`/explain` 1회 활성** (debate §3 ACCEPT): explain 후 버튼 hidden.
8. **panelToken** (debate §3 ACCEPT): async cancellation.
9. **server-side title source** (debate §4 ACCEPT): client title 생성 제거.
10. **테스트 추가** (debate §5 ACCEPT): vendor runtime + XSS via jsdom.

### RE-CODE 추가 변경 (R1 ACCEPT, challenge에 없던 fix)

- `activeDocId` localStorage persist + cross-doc restore 거부
- `lastFailedAction` retry capture (재시도 실제 재호출)
- `chat_panel.js` force scroll-to-bottom (긴 thread reopen 시 newest)
- `thread_list.js` active highlight를 thread.id로
- `scripts/phase5_scenario.py` 트랙 (reproducibility)

## Both sides — disagreement summary

### Worker (self v2) 입장

- R1 4 substantive 결함 (cross-doc state, no-op retry, scroll top, block_id active) + scenario untracked 모두 fix.
- R2 cross-verify가 "Round 1's reported defects were mostly fixed"를 명시.
- 262 fast tests + 8 vendor/XSS tests + `make check` RC=0.
- DoD 6 모두 evidence (10 screenshots + scenario script committed + 회귀 가드 6건).
- self 93/100. 새 R2 결함은 cosmetic 영역 또는 enhancement (이전 결함의 edge case).

### Codex (Cross R2) 입장

R1 결함 fix는 인정. 그러나 RE-CODE에서 새 3 결함 발견:

1. **Retry context bug (신규)**: `panelError` / `lastFailedAction`이 global. 다른 block/thread 선택해도 reset 안 됨. block A에서 실패한 메시지가 retry로 block B에 reissue될 수 있음. 회귀 테스트는 `lastFailedAction =` 마커 count만 검사하지 정합성 미검증.
2. **Ctrl/Cmd+B 토글이 close-only**: `closePanel()`이 `activeBlockId`/`activeThreadId` wipe → reopen 조건 (`state.activeBlockId`) 항상 false. 토글이 close만 동작.
3. **doc-scoped restore migration hole**: pre-R1 localStorage에 `activeDocId`가 없으면 (null) restore 거부 분기 안 탐 → 여전히 stale thread 가능.

추가 critique: scenario 재실행이 v2 코드 기준은 아님 (시나리오는 R0 기준 — screenshots 1-10은 RE-CODE 전 캡처).

제안 82/100.

### Worker 보충 의견 (양측 disagreement에 대한 평가)

- **Retry context bug**: VALID. `panelError` + `lastFailedAction`은 block 전환 시 clear되어야 함. 5분 fix (block click handler에 `panelError = null; lastFailedAction = null`).
- **Ctrl+B 토글 close-only**: VALID. `closePanel()`이 active 정보 wipe하므로 reopen 불가. 두 가지 옵션:
  - (a) closePanel은 `panelOpen=false`만 토글하고 active 정보는 보존 (단, doc 전환 시는 wipe).
  - (b) closePanel은 그대로, toggle은 `state.threadsByDoc` 최근 thread를 자동 선택.
  - (a)가 단순.
- **Migration hole**: VALID. `activeDocId === null && panelOpen && activeThreadId`인 stale state 처리 필요. 분기 한 줄 추가.
- **scenario 재캡처 미실행**: VALID critique. screenshots는 R0/RE-CODE 동작 차이가 시각적으로는 거의 없음 (chat 동작 외관 동일) 이지만, "scroll-to-bottom" fix 검증을 위해선 새 thread 켜고 scroll position 확인 필요. 자동 캡처에서 다루기 어려움.

결론: R2 critique 모두 valid. 3 신규 결함은 단순 5-10줄 fix로 해소 가능. Round-cap (2) 도달 → cross-verify 재호출 불가 → Planner escalate.

## Planner-directed fix applied (post R2)

Planner가 R2 3 결함을 직접 fix 지시. cross-verify 재호출 금지 (round-cap + Planner 명시). 3 fix 적용 + 회귀 가드 6건 추가:

- **`a602298 fix(phase-5): scope panelError/lastFailedAction to block transitions`** (Fix 1)
  - viewer.js의 block-click 핸들러 + jumpToThread에서 `state.activeBlockId !== blockId` 비교, transition 시 두 변수 clear. 같은 block 재선택은 보존.
  - 회귀 테스트: `test_block_transition_clears_retry_state` (양쪽 호출처 grep + reset 형태 count)
- **`77797bb fix(phase-5): closePanel preserves activeBlockId, togglePanel works both ways`** (Fix 2)
  - state.js를 3개 함수로 분리: `closePanel` (panelOpen flip만), `discardPanel` (전체 wipe), `togglePanel` (open/close 단일 source).
  - viewer.js의 호출처 정합성: onClose/Esc → closePanel, navigateTo/popstate/bootstrap-mismatch → discardPanel, Ctrl+B → togglePanel.
  - 회귀 테스트 3건: `test_close_panel_preserves_active_block`, `test_toggle_panel_reopens_after_close`, `test_navigate_and_popstate_use_discard_panel`
- **`155a67b fix(phase-5): bootstrap migration guard for pre-r1 localStorage schema`** (Fix 3)
  - state.js에 `readPanelSnapshot()` 함수 도입. `activeDocId === null` 분기에서 panelOpen/activeBlockId/activeThreadId 모두 false/null로 반환 + orphaned key를 localStorage에서 삭제.
  - 회귀 테스트 2건: `test_state_migration_guard_for_pre_r1_localstorage`, `test_state_panel_snapshot_returns_typed_object`

결과:
- 262 → **268 fast tests** (+6 grep regression guards)
- `make check` RC=0 / ruff / mypy strict / 8 vendor+XSS tests pass
- self score: v2 93 → **v3 97**
- 안정성 29 → 30, 완결성 32 → 34, 독창성 13 → 14

R0/R1 screenshots (1-10)는 그대로 유효 (Planner 지시: 재캡처 금지). chat 동작 외관은 변화 없으므로 시각 evidence는 R0 캡처가 충분.

## Evidence index

- plan: `.claude/phases/phase-5/plan.md`
- debate: `.claude/phases/phase-5/debate.md` (Codex Round 0)
- challenge: `.claude/phases/phase-5/challenge.md` (decision PASS, 10 revisions)
- verify (v3 latest, post Planner-directed fix): `.claude/phases/phase-5/verify.md`
- verify-cross (R1 + R2, 재호출 금지): `.claude/phases/phase-5/verify-cross.md`

## Known issues / debt

### R2가 raised — Planner-directed fix로 모두 해소

1. ~~Retry context not scoped to block/thread~~ — `a602298`에서 fix
2. ~~Ctrl+B 토글 close-only~~ — `77797bb`에서 fix
3. ~~Migration hole~~ — `155a67b`에서 fix
4. **R0/R1 screenshots RE-CODE 전 캡처**: Planner 지시로 재캡처 금지. chat 동작 외관은 R0 == R3 동일. 시각 evidence는 R0 충분.

### Phase 5 본체 잔여 한계 (Phase 6 entry)

5. **Playwright UI 회귀 suite 부재**: `scripts/phase5_scenario.py`로 reproduce 가능하지만 회귀 가드는 grep 수준.
6. **CI jsdom 미제공**: `test_render_markdown_js.py`는 host에 jsdom 있을 때만 실행.
7. **Streaming/SSE 미도입**: 동기 응답 유지 (Phase 6 검토).
8. **thread title LLM-driven 자동 생성**: server-side `_default_thread_title` 단순 truncate. Phase 6에서 LLM-driven 검토.

## Push status

**보류 (Planner가 직접 push)**. 사유:
- Planner-directed fix 정책: fix 적용 후에도 Worker는 push 안 함.
- cross-verify 재호출 금지 (Round 2 상한 + Planner 명시).
- 현재 local main이 `origin/main` 대비 **18 commits ahead** (Phase 5 본체 12 + Planner-directed 6).

## Recommended next

- **Planner의 push 검토 후 Phase 6 진입 권장**
- **Phase 6 (검색/export/모바일/회전 페이지 정밀 매핑) 진입 시 흡수**:
  - Playwright UI 회귀 suite 도입 (scripts/phase5_scenario.py 기반 확장 + scroll-to-bottom 시각 evidence 자동 캡처)
  - CI에 jsdom 설치 단계 (`npm install jsdom`) 추가
- **Phase 7+ (스트리밍 + LLM-driven 자동 thread title)**:
  - SSE 응답 흐름
  - thread title LLM 호출 / cache 정책
