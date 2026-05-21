# Phase 5 — Plan

## Goal

Phase 4 viewer에 우측 채팅 패널 + block 클릭 → AI Q&A + 핀 표시 + 좌측 질문 사이드바 탭을 더해, 사용자가 실제로 문서 한 권을 읽으며 10개+ 질문을 자연스럽게 누적할 수 있도록 한다. v0.3 마일스톤.

## Scope

**In**
- `src/ht_lens/api/static/vendor/`: marked / highlight.js / DOMPurify (CDN 한 번 다운로드 → commit) + LICENSE
- `src/ht_lens/api/static/js/utils/render_markdown.js` (vendor 통합)
- `js/components/`:
  - `chat_panel.js` (우측 패널 본체, slide in/out)
  - `message.js` (단일 메시지 — assistant markdown / user plain)
  - `message_input.js` (입력창 + 전송 + 키보드)
  - `thread_list.js` (사이드바 질문 탭)
  - `pin.js` (block 핀 표시 utility)
  - 기존: `page_view.js` / `block.js` / `sidebar.js` 수정 (탭 전환, 핀 갱신, click hook)
- `js/api.js` 확장: threads/messages 호출 메서드
- `js/state.js` 확장: activeBlockId, activeThreadId, panelOpen, sidebarTab, threadsByDoc, messagesByThread, loadingMessage
- `js/viewer.js` 수정: 패널 통합 + 핀 갱신 + 키보드 확장
- `js/keyboard.js` 확장: Esc, Cmd/Ctrl+Enter, Cmd/Ctrl+B
- `css/chat_panel.css` (신규) + `css/viewer.css` 수정 (탭 + 핀 스타일)
- localStorage 확장: zoom + overlay + lastDocId + lastPageNum + panelOpen + sidebarTab
- Integration tests: 정적 자산 (vendor 포함), JS contract markers (panel, pin, thread_list)
- `docs/phases/phase-5/` 10 screenshots + README
- 10-question 시나리오 (자동/수동 hybrid)

**Out**
- Streaming (SSE/WebSocket) — Phase 6
- 새 backend API — Phase 3 endpoint로 충분
- markdown 외 라이브러리
- Phase 6 (검색/export/모바일/회전 페이지 정밀 매핑)
- JS framework / 빌드 도구
- block click 핸들러 시그니처 자체 변경 (placeholder console.log → panel trigger로 교체만)
- ROADMAP/WORKFLOW/CLAUDE/AGENTS/prompts/scripts (run_*) 수정

## Approach

### 1. Vendor 라이브러리 (사전 결정)

`src/ht_lens/api/static/vendor/`에 직접 commit:
- `marked@11.x.min.js` (~15KB)
- `highlight.min.js` (highlight.js@11 core) + 언어별: `javascript.min.js`, `python.min.js`, `bash.min.js`
- `highlight-theme.css` (atom-one-dark)
- `purify.min.js` (DOMPurify@3)
- `LICENSE` — 통합 (모두 MIT/BSD)

ES module로 다운로드 (`<script type="module">`에서 import). CDN URL은 README의 reproduction 노트에만 적고 빌드 단계는 없음.

### 2. `render_markdown.js`

```js
import { marked } from "../../vendor/marked.min.js";
import hljs from "../../vendor/highlight.min.js";
import DOMPurify from "../../vendor/purify.min.js";

marked.setOptions({
  highlight: (code, lang) => {
    if (lang && hljs.getLanguage(lang)) {
      return hljs.highlight(code, { language: lang }).value;
    }
    return hljs.highlightAuto(code).value;
  },
  breaks: true,
  gfm: true,
});

export function renderMarkdown(text) {
  const raw = marked.parse(text);
  return DOMPurify.sanitize(raw, {
    ADD_ATTR: ["target", "rel"],
    USE_PROFILES: { html: true },
  });
}

// 외부 링크 새 탭 open (DOMPurify hook)
DOMPurify.addHook("afterSanitizeAttributes", (node) => {
  if (node.tagName === "A" && node.getAttribute("href")) {
    node.setAttribute("target", "_blank");
    node.setAttribute("rel", "noopener noreferrer");
  }
});
```

assistant 메시지에만 적용. user 메시지는 `textContent` 사용 (escape 자동).

### 3. Chat Panel 컴포넌트

`chat_panel.js`:

```js
// API
renderChatPanel(container, { doc, block, thread, messages, loading }, callbacks)

// callbacks: { onExplain, onSubmit, onClose, onRetry }
```

DOM 구조:
```html
<aside class="chat-panel">
  <header>
    <div class="block-preview">
      <div class="original">{block.original_text 미리보기}</div>
      <div class="translated">{block.translated_text 미리보기}</div>
    </div>
    <button class="close">×</button>
  </header>
  <main class="messages">
    {messages.map(renderMessage)}
    {loading && <Skeleton />}
  </main>
  <footer>
    {messages 비어있고 explain 가능} → [✨ AI에게 설명 요청] button
    {그 외} → MessageInput
  </footer>
</aside>
```

패널 toggle은 viewer-shell의 grid-template-columns 변경 (`220px 1fr 400px` ↔ `220px 1fr 0`) + CSS transition.

### 4. Block click 동작 (Phase 4 placeholder 교체)

```js
// block.js
el.addEventListener("click", (e) => {
  e.stopPropagation();
  // Phase 4: console.log
  // Phase 5: dispatch custom event handled by viewer.js
  const event = new CustomEvent("ht-lens:block-click", {
    detail: { blockId: blockData.id, blockData },
    bubbles: true,
  });
  el.dispatchEvent(event);
});
```

`viewer.js`가 `document.addEventListener("ht-lens:block-click", ...)` 으로 처리.

이유: block.js는 viewer.js를 import하지 않고 (single-responsibility), viewer.js만 panel을 알면 됨.

### 5. Pin 표시 (block.js 수정)

```js
// block.js — renderBlock 끝부분
if (threadsByBlock.has(blockData.id)) {
  el.dataset.hasThread = "true";
  const thread = threadsByBlock.get(blockData.id);
  el.title = thread.title;
}
```

CSS:
```css
.block[data-has-thread='true']::after {
  content: "📌";
  position: absolute;
  top: -8px;
  right: -8px;
  font-size: 14px;
  background: white;
  color: #333;
  border-radius: 50%;
  width: 20px;
  height: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.4);
  z-index: 6;
}
```

핀 갱신:
- 페이지 진입 시: `GET /threads?doc_id=N`으로 thread 목록 받아 `state.threadsByDoc[docId]` 캐시
- 새 thread 생성 직후: 캐시에 추가 + 해당 block에 `data-has-thread` 설정
- 페이지 떠날 때 캐시 유지 (다음 진입 시 재사용)

### 6. Sidebar 탭 전환

```html
<aside class="sidebar">
  <nav class="sidebar-tabs">
    <button class="tab active" data-tab="pages">📄 페이지</button>
    <button class="tab" data-tab="questions">❓ 질문</button>
  </nav>
  <div class="tab-panel" data-panel="pages">{기존 page list}</div>
  <div class="tab-panel" data-panel="questions" hidden>{thread list}</div>
</aside>
```

탭 전환 시 `state.sidebarTab` 갱신 + localStorage 저장 + 스크롤 위치 보존.

### 7. Thread List 컴포넌트

`thread_list.js`:

```js
renderThreadList(container, threads, currentBlockId, onClick)
```

각 항목:
```html
<li class="thread-item" data-thread-id="N">
  <span class="pin">📌</span>
  <div class="title">{thread.title}</div>
  <div class="meta">p.{page_num} · {message_count}개 메시지</div>
</li>
```

클릭 → `onClick({thread})`:
- `navigateTo(docId, thread.page_num)` (history.pushState)
- `state.activeBlockId = thread.block_id`
- `state.activeThreadId = thread.id`
- 패널 열기 + thread 로드
- 페이지 렌더 후 해당 block scrollIntoView + 강조 outline

### 8. Thread title 자동 생성 (debate 결정사항 2)

LLM 추가 호출 없이 단순:
- 첫 user message가 있으면 첫 30자
- 없으면 block.original_text 첫 30자
- 빈 block이면 `"[block #{id}]"`
- 사용자가 명시적으로 `POST /threads` body에 `title`을 주면 그 값 (Phase 3 API 그대로)

생성 시점: thread 생성 시 client-side 결정 + 서버 호출. 변경되지 않음 (immutable). Phase 6에서 LLM-driven title 검토.

### 9. Loading + 에러 상태

- AI 호출 중: 메시지 영역 하단에 skeleton + spinner ("AI가 응답 중..." 텍스트)
- 전송 버튼 비활성화 (`loading` 동안)
- LLM 에러 (502): 빨강 banner + 재시도 버튼
- 네트워크 끊김: 메시지 영역 상단 "재연결 중..." banner

### 10. Message Input

```html
<form class="message-input">
  <textarea rows="3" maxlength="4000" placeholder="질문을 입력하세요..."></textarea>
  <button type="submit">전송</button>
</form>
```

- textarea 자동 grow (3 ~ 8 lines)
- `Cmd/Ctrl+Enter` 전송, `Enter` 단순 줄바꿈
- 빈 trim 거부
- 4000자 초과 시 경고

### 11. State 확장

```js
// state.js 추가
export const state = {
  zoom: ...,
  overlayMode: ...,
  // 신규
  activeBlockId: null,
  activeThreadId: null,
  panelOpen: false,
  sidebarTab: localStorage.getItem("ht_lens.sidebarTab") || "pages",
  threadsByDoc: {},          // {docId: [...threads]}
  messagesByThread: {},      // {threadId: [...messages]}
  loadingMessage: false,
};
```

### 12. localStorage persistence

debounced (500ms) write:
```js
{
  zoom, overlayMode,
  lastDocId, lastPageNum,
  panelOpen, sidebarTab,
}
```

리로드 시 복원. `activeThreadId`는 저장 안 함 (URL 기반은 Phase 6).

### 13. 키보드 확장

`keyboard.js`에 추가:
- `Esc`: 패널 닫기 (open일 때만, 아니면 무시)
- `Cmd/Ctrl+B`: 패널 토글
- `Cmd/Ctrl+Enter`: input 안에서 메시지 전송 (input 자체에서 처리)

### 14. URL 라우팅

`?doc=N&page=M` 유지. Phase 5에서 deep link (`?thread=N`) 추가 안 함 (Phase 6).

### 15. CSS layout 확장

```css
.viewer-shell {
  display: grid;
  grid-template-columns: 220px 1fr 0;       /* panel closed */
  ...
}

.viewer-shell.panel-open {
  grid-template-columns: 220px 1fr 400px;   /* panel open */
}

.chat-panel {
  background: var(--surface);
  border-left: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  transition: transform 0.2s ease;
}
```

### 16. Race condition 방어 (debate 결정사항 10)

`POST /threads` 빠른 두 번 클릭 방지:
- `state.creatingThreadFor`: 현재 thread 생성 중인 blockId
- 같은 blockId에 대해 진행 중이면 두 번째 호출은 첫 응답 대기로 합침

### 17. CustomEvent 전파 (block click)

`block.js`가 ES module이라 `viewer.js`의 함수를 직접 import할 수 없는 건 아니지만, viewer.js가 viewer 진입점이라서 다른 컴포넌트가 import하면 순환 의존. 대신 custom event로 디커플.

### 18. Phase 4 호환성

- Phase 4의 모든 기능 그대로 유지
- viewer.js의 `clearViewerDom`, `navToken`, `loadAndRender` 시그니처 유지
- `subscribe` pattern 확장으로 새 state 키 추가는 무회귀

### 19. 10-question 시나리오 (verify 5-B)

- sample_mixed.pdf, 6 pages
- 8개 block에서 explain (다양한 페이지)
- 2개 block에서 직접 질문 + 1개 thread에 꼬리질문
- 결과: 10 thread, ~12-15 메시지
- 스크린샷 10장 캡처:
  1. block click → 빈 thread (explain 버튼)
  2. explain 응답 받음
  3. 직접 질문 + 응답
  4. 같은 thread에 꼬리질문
  5. 페이지에 핀 여러 개
  6. 사이드바 질문 탭 열림
  7. 질문 클릭 → 페이지 점프 + 패널 자동 열림
  8. markdown 코드블록 렌더
  9. 10개 thread 누적 (질문 탭에서)
  10. 새로고침 후 localStorage 복원 (페이지/패널/탭 그대로)

### 20. Phase 6 미리 준비

- `state.threadsByDoc` 캐시 패턴 → Phase 6의 search/export에서 재사용
- chat_panel의 messages rendering → Phase 6 streaming SSE 추가 시 동일 컴포넌트 재사용
- pin click 핸들러는 block click과 동일 흐름 (single source)

## File-level changes

| Path | Action | Note |
| ---- | ------ | ---- |
| `src/ht_lens/api/static/vendor/marked.min.js` | NEW | marked@11 |
| `src/ht_lens/api/static/vendor/highlight.min.js` | NEW | hljs core |
| `src/ht_lens/api/static/vendor/highlight-languages/{javascript,python,bash}.min.js` | NEW (3) | 자주 쓰는 언어 |
| `src/ht_lens/api/static/vendor/highlight-theme.css` | NEW | atom-one-dark |
| `src/ht_lens/api/static/vendor/purify.min.js` | NEW | DOMPurify@3 |
| `src/ht_lens/api/static/vendor/LICENSE` | NEW | MIT/BSD 통합 |
| `src/ht_lens/api/static/js/utils/render_markdown.js` | NEW | vendor 통합 |
| `src/ht_lens/api/static/js/components/chat_panel.js` | NEW | 패널 본체 |
| `src/ht_lens/api/static/js/components/message.js` | NEW | 단일 메시지 |
| `src/ht_lens/api/static/js/components/message_input.js` | NEW | 입력창 |
| `src/ht_lens/api/static/js/components/thread_list.js` | NEW | 사이드바 질문 탭 |
| `src/ht_lens/api/static/js/components/pin.js` | NEW | 핀 utility (사실은 block.js inline가 더 단순; 결정: block.js에 inline 적용 + pin.js 생략 검토) |
| `src/ht_lens/api/static/js/components/block.js` | MODIFY | click → custom event + has-thread attr |
| `src/ht_lens/api/static/js/components/page_view.js` | MODIFY | threads cache 전달 |
| `src/ht_lens/api/static/js/components/sidebar.js` | MODIFY | 탭 전환 + 질문 탭 |
| `src/ht_lens/api/static/js/api.js` | MODIFY | threads/messages 메서드 |
| `src/ht_lens/api/static/js/state.js` | MODIFY | 신규 state 필드 + persist |
| `src/ht_lens/api/static/js/viewer.js` | MODIFY | 패널 통합 + 핀 갱신 + Esc/Ctrl+B |
| `src/ht_lens/api/static/js/utils/keyboard.js` | MODIFY | Esc, Ctrl+B |
| `src/ht_lens/api/static/css/chat_panel.css` | NEW | 패널 스타일 |
| `src/ht_lens/api/static/css/viewer.css` | MODIFY | 사이드바 탭 + 핀 |
| `src/ht_lens/api/static/viewer.html` | MODIFY | 우측 슬롯 활성화 + 사이드바 탭 DOM |
| `tests/integration/test_static_serving.py` | MODIFY | vendor + 신규 JS 자산 200 |
| `docs/phases/phase-5/README.md` | NEW | 10-시나리오 설명 |
| `docs/phases/phase-5/screenshots/*.png` | NEW (10) | 시나리오 캡처 |

## Dependencies (new)

Python: **none**.

JS vendor (commit, not npm):

| Library | Version | Purpose | Size | License |
| ------- | ------- | ------- | ---- | ------- |
| marked | 11.x | Markdown → HTML | ~15 KB | MIT |
| highlight.js | 11.x | Syntax highlighting | ~50 KB (core+3 langs) | BSD-3 |
| DOMPurify | 3.x | XSS sanitization | ~22 KB | Apache 2.0 / MPL |

총 ~90 KB. 라이선스 통합 `vendor/LICENSE`로 commit.

## Test strategy

### Integration (TestClient, fast)
- 정적 자산 200 (HTML/CSS/JS + vendor 6+ 파일)
- JS contract markers (panel CustomEvent, pin data-has-thread, sidebar tab data-tab, thread_list rendering, message markdown)
- Phase 3/4 회귀 가드 (기존 233 tests)

### 수동 + 자동 hybrid (verify 5-B)
- 10-question 시나리오 (live LLM)
- Playwright 자동 캡처 (Phase 4와 동일 패턴, 외부 venv 활용 — Python dep 추가 없음)
- 캡처 결과 통계 (thread 수, 메시지 수, 핀 수)
- localStorage 복원 검증 (브라우저 새로고침 후 화면 그대로)

### Live LLM tests (`@pytest.mark.llm`)
- Phase 3의 `test_api_live_llm.py` 유지 (회귀 가드)
- Phase 5 신규 endpoint 없으므로 추가 LLM test 불필요

## DoD mapping

| DoD item | How to satisfy | Evidence plan |
| -------- | -------------- | ------------- |
| 문서 한 권 읽으며 10개 이상 질문 자연스럽게 누적 | 10-question scenario + 사이드바 질문 탭 | verify 5-B + 스크린샷 9 (10 threads list) |
| 닫았다 다시 열어도 핀/스레드 그대로 | localStorage persist + GET /threads on page enter | verify 5-B + 스크린샷 10 (리로드 후 상태) |
| 마크다운/코드블럭 렌더링 | marked + highlight.js + DOMPurify | 스크린샷 8 (코드블록) |
| 우측 패널 (explain/직접질문/꼬리질문) | chat_panel + message_input | 스크린샷 2/3/4 |
| 핀 표시 (thread 있는 block 우상단) | block.js `data-has-thread` + CSS pseudo | 스크린샷 5 |
| 좌측 사이드바 질문 탭 (전체 thread 목록 + 페이지 점프) | sidebar tab + thread_list | 스크린샷 6/7 |

## 미결정 사항 (debate 검토 대상)

1. **`/explain` 멱등성 UI**: Phase 3 API는 호출마다 새 메시지 append. UI에서 "이미 explain 있음" 표시? plan: 첫 explain 후 버튼 비활성 (재호출은 직접 질문으로 유도).
2. **Thread title 자동 생성**: LLM 호출 0 (user msg/block 첫 30자). LLM-driven은 Phase 6.
3. **메시지 영역 스크롤**: 새 메시지 도착 시 자동 하단 스크롤. 사용자가 위로 스크롤 중이면 (scrollTop < scrollHeight - clientHeight - 50) 자동 스크롤 안 함.
4. **`@pytest.mark.llm`**: Phase 5는 신규 endpoint 없으므로 Phase 3 LLM 테스트가 회귀 가드. 추가 안 함.
5. **마크다운 link**: 외부 링크 새 탭 (`target="_blank" rel="noopener noreferrer"`). DOMPurify hook으로 추가.
6. **핀 위치**: 우상단 (외부 spec 결정 그대로).
7. **사이드바 탭 전환 후 스크롤 복원**: tab별 scrollTop을 state에 저장 + 복원.
8. **메시지 입력 multi-line**: textarea auto-grow 3~8 lines.
9. **DOMPurify whitelist**: `USE_PROFILES.html: true` + `ADD_ATTR: ["target", "rel"]`. 코드블록은 marked가 `<pre><code>`로 변환하므로 그대로 통과.
10. **Thread 생성 race**: `state.creatingThreadFor` flag + Promise dedup. 같은 blockId 동시 클릭은 첫 호출 결과 공유.

debate에서 Codex가 위 영역을 찌를 가능성: 특히 (3) 스크롤 동작, (10) race condition, vendor lib supply chain 신뢰성.
