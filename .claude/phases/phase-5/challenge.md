# Phase 5 — Challenge

## Debate responses

### 1. Over-engineering

**Markdown 스택 (marked + DOMPurify + highlight.js + 3 langs + theme + LICENSE)** — **PARTIAL accept**
Codex 주장: DoD는 "마크다운/코드블럭 렌더링"이고 highlight.js는 부가.
응답: marked + DOMPurify로 마크다운/코드블럭 렌더 충족. highlight.js + 언어팩 + 테마는 cosmetic → 제거. 코드블록은 marked 기본 `<pre><code>` + 자체 CSS (monospace + 배경). Phase 6에서 필요 시 도입.
**결정**: vendor = marked + DOMPurify + LICENSE 만. ~37KB.

**Client state 모델 비대** — **PARTIAL accept**
응답: `creatingThreadFor` 제거 → `loadingMessage` flag + 버튼 disable로 충분. Tab scroll 복원 제거. `messagesByThread` 대신 `threadDetailById` (GET /threads/{id} 캐시, debate §4 alt 채택). `threadsByDoc` (페이지 진입 시 핀 갱신용)만 유지.
**결정**: state 단순화.

**Phase 6 미리 준비** — **ACCEPT**
응답: plan §20 제거. Phase 5는 Phase 5 DoD에만 집중.

### 2. Hidden assumptions

**Vendor lib ESM 호환성 미검증** — **ACCEPT (중요)**
응답: ESM 빌드 명시 다운로드:
- marked: `cdn.jsdelivr.net/npm/marked@11/lib/marked.esm.js`
- DOMPurify: `cdn.jsdelivr.net/npm/dompurify@3/dist/purify.es.mjs`

다운로드 직후 node로 dynamic import 가능 여부 smoke test. 실패 시 IIFE 버전 + `window.marked` 패턴 fallback.
**결정**: ESM 빌드 + smoke test.

**`/messages` 응답이 assistant만** — **ACCEPT (큰 변경)**
응답: debate §4 alt 채택 — `GET /threads/{id}`를 cache 단위로. 모든 write 직후 refetch. `threadDetailById` 캐시.
**결정**: write 후 refetch 패턴.

**`panelOpen` persist + `activeThreadId` non-persist mismatch** — **ACCEPT**
응답: `activeThreadId` + `activeBlockId`도 localStorage persist. 리로드 시 자동 패널 열기 + thread 로드.
**결정**: persist + restore.

### 3. Edge cases

**Multiple threads per block** — **ACCEPT**
응답: `threadsByBlock`를 `Map<blockId, Thread[]>`로. 핀은 array.length > 0이면 표시. tooltip은 first thread title (+ "+N more"). 사이드바는 모든 thread 표시. 클릭 시 가장 최근 thread 자동 열기.
**결정**: 배열 모델 + 핀 count badge.

**`/explain` double-click → duplicate** — **ACCEPT**
응답: explain 버튼 1회 활성 후 영구 비활성 (per thread). 추가 설명은 직접 질문으로 유도. `loadingMessage` 동안 모든 액션 disable.
**결정**: explain 버튼 1회만 클릭 가능.

**navToken이 chat panel async ops 미포함** — **ACCEPT**
응답: `panelToken` 별도 추가. thread 로드 / explain / message post 모두 token 검증. 페이지 navigation 시 panel 강제 close (`panelToken++`).
**결정**: panelToken + close on navigation.

### 4. Alternative approaches

**`GET /threads/{id}` cache 단위** — **ACCEPT** (§2와 함께)

**Server-side title source of truth** — **ACCEPT**
응답: client-side title 생성 로직 제거. `POST /threads` body의 `title`는 사용자 명시 시만. 서버의 `_default_thread_title()`이 단일 source.

**marked + DOMPurify only** — **ACCEPT** (§1과 함께)

### 5. Missing tests

**`test_viewer_runtime_imports_vendor_modules`** — **ACCEPT**
응답: node-only ESM import smoke (font_fit_js 패턴). subprocess + `import("vendor/marked.esm.js")` + export 확인.
**결정**: `tests/integration/test_vendor_runtime.py` (node 있을 때 skip-not).

**`test_chat_post_roundtrip_shows_user_and_assistant_messages`** — **ACCEPT (간접)**
응답: server-side roundtrip은 Phase 3 `test_api_threads.py::test_get_thread_returns_messages_in_order`에서 이미 검증. Phase 5는 client refetch 패턴 grep test로 잠금: viewer.js / chat_panel.js에서 write 후 `apiGet("/threads/{id}")` 호출.

**`test_multiple_threads_same_block_show_single_pin_and_distinct_sidebar_entries`** — **PARTIAL accept**
응답: server-side는 Phase 3 통과. Phase 5 client는 grep test로 잠금: block.js의 multi-thread 처리 + thread_list.js의 모든 thread 렌더.

**`test_reload_restores_active_thread_or_intentionally_closes_panel`** — **ACCEPT**
응답: state.js의 localStorage key에 `activeThreadId`, `activeBlockId` 추가 + 복원 분기. grep + 수동 verify.

**`test_markdown_sanitization_strips_script_and_javascript_href`** — **ACCEPT**
응답: `tests/integration/test_render_markdown_js.py` (node + render_markdown.js dynamic import). XSS payload 5종 (script, on*, javascript:, data:, iframe) 검증.

---

## Plan revisions (after debate)

1. **vendor 라이브러리 축소**: highlight.js + 언어팩 + theme 제거. marked + DOMPurify만 (ESM 빌드).
2. **client state 단순화**: `messagesByThread` → `threadDetailById` (refetch 패턴). `creatingThreadFor`, tab scroll 제거.
3. **Phase 6 미리 준비 섹션 삭제**.
4. **write 후 `GET /threads/{id}` refetch 패턴**.
5. **`activeThreadId` + `activeBlockId` persist** + 리로드 시 panel 자동 복원.
6. **Multiple threads per block 지원**: 배열 + 핀 count.
7. **`/explain` 1회 활성 (per thread)** + `loadingMessage` 동안 모든 액션 disable.
8. **`panelToken`** chat panel async cancellation + 페이지 nav 시 패널 close.
9. **Client title 생성 제거** (서버가 단일 source).
10. **테스트 추가**:
    - `test_vendor_runtime.py` (node ESM import smoke)
    - `test_render_markdown_js.py` (node + XSS payload 5종)
    - JS contract grep (refetch 패턴, multi-thread per block, activeThreadId persist, panelToken)

---

## DoD checklist

| DoD item | Status | Evidence |
| -------- | ------ | -------- |
| 문서 한 권 읽으며 10개 이상 질문 자연스럽게 누적 | planned | 10-question scenario + 질문 탭 + 10 screenshots |
| 닫았다 다시 열어도 핀/스레드 그대로 | planned | localStorage activeThreadId/activeBlockId + GET /threads on page enter |
| 마크다운/코드블럭 렌더링 | planned | marked + DOMPurify + CSS code block + node XSS test |
| 우측 패널 | planned | chat_panel + message_input + panelToken |
| 핀 표시 | planned | block.js `data-has-thread` + count badge if >1 |
| 좌측 사이드바 질문 탭 | planned | sidebar tab + thread_list |

---

## Risk register

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| vendor ESM 빌드 import 실패 | Low (다운로드 시 검증) | viewer 부팅 실패 | node smoke test + manual import 검증 |
| LLM 응답 >60s | Medium | UX 정지 | `LLM_TIMEOUT` env (Phase 3 기존) + spinner + 재시도 |
| 동시 thread 생성 race | Low | duplicate | 버튼 disable + panelToken |
| Markdown XSS | Low | reputation | DOMPurify + node test 5 payload |
| localStorage 비활성 | Low | persist 안 됨 | try/catch + in-memory fallback |
| Multi-thread block UI 혼란 | Low | UX | 사이드바에 모두 표시 + 핀 count |
| 페이지 nav 후 stale panel paint | Low | UX | panelToken + close on nav |

---

## Decision

- [x] PASS → proceed to code (plan revisions 10건 적용)
- [ ] RE-PLAN

Codex 13 비판 중 10 ACCEPT, 3 PARTIAL ACCEPT, 0 REJECT. Plan revision 10건 반영해 코드 단계 진입.
