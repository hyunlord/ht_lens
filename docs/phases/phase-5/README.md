# Phase 5 — Chat Panel + Pins + Question List

DoD evidence for Phase 5 (v0.3 milestone). All captures use the live FastAPI
server + sglang qwen3.6-27b. Driver: Playwright (chromium 147, viewport
1600×1000); the script lives at `/tmp/phase5_scenario.py` and is intentionally
not committed (Playwright is not a project dep).

## 10-question scenario result

- **Threads created**: 10
- **Total messages** (user + assistant): 22
- **Pins on page 1 blocks**: 3 (Open-Sora Team, HPC-AI Tech, Abstract — all
  visible in screenshot 05)
- **localStorage restore**: panel + sidebar tab + active thread + page all
  restored after `page.reload()` (screenshot 10)
- **Markdown render**: assistant responses use marked + DOMPurify; bold, lists,
  fenced code blocks all render. XSS payloads (script / iframe / javascript:
  href / on*) are stripped at render time — locked by
  `tests/integration/test_render_markdown_js.py`.

| # | File | Notes |
| - | ---- | ----- |
| 1 | `01-block-click-empty.png` | First block click — empty thread, [✨ AI에게 설명 요청] CTA visible. |
| 2 | `02-explain-response.png` | After clicking explain — assistant message renders Korean markdown with headings/lists/inline code. |
| 3 | `03-direct-question.png` | After typing a direct question and Ctrl+Enter — user + assistant pair stack in the panel. |
| 4 | `04-followup-question.png` | Follow-up question in the same thread — Phase 3's `chat(..., system=block_ctx)` keeps context. |
| 5 | `05-pins-on-blocks.png` | Page 1 with multiple pinned blocks — 📌 visible at the top-right of `Open-Sora Team`, `HPC-AI Tech`, `Abstract`. |
| 6 | `06-sidebar-questions-tab.png` | "❓ 질문" sidebar tab — all 10 threads listed with title + page + message count. |
| 7 | `07-thread-jump-from-list.png` | Click a sidebar thread → viewer navigates to that block's page and re-opens the chat panel. |
| 8 | `08-markdown-render.png` | Same panel state as 07 — close-up evidence of marked + DOMPurify rendering ("핵심 개념 요약" headings, bullet lists, inline code). |
| 9 | `09-ten-questions-accumulated.png` | DoD evidence — 10 threads visible in the sidebar. |
| 10 | `10-localstorage-restore.png` | After `page.reload()` — panel + tab + active thread all restored from localStorage. |

## Reproducing the captures

```bash
# Fresh DB with the Phase 3 sample doc.
cp /tmp/ht_lens_phase3.db /tmp/ht_lens_phase5.db
sqlite3 /tmp/ht_lens_phase5.db "DELETE FROM messages; DELETE FROM threads;"

# Server (live LLM required).
export LLM_PROVIDER=openai_compat \
       LLM_BASE_URL=http://localhost:8081/v1 \
       LLM_MODEL=qwen3.6-27b \
       LLM_TIMEOUT=300
ht-lens serve --port 8201 --db /tmp/ht_lens_phase5.db &
sleep 4

# Drive the scenario via Playwright (any env with playwright + chromium).
python /tmp/phase5_scenario.py 8201
```

The first scenario pass typically takes 15-25 minutes (one LLM round-trip
per explain/message, qwen3.6-27b at 200-500 tokens/sec on sglang). Re-running
on the same DB is idempotent — already-existing threads are reused; only
the new clicks generate fresh LLM calls.

## DoD spot-check

| DoD item | Evidence |
| -------- | -------- |
| 문서 한 권 읽으며 10개 이상 질문 자연스럽게 누적 | screenshots 06/09 — 10 threads in sidebar. |
| 닫았다 다시 열어도 핀/스레드 그대로 | screenshot 10 — page reload preserves panel, tab, active thread. localStorage keys: `ht_lens.panelOpen`, `ht_lens.activeThreadId`, `ht_lens.activeBlockId`, `ht_lens.sidebarTab`. |
| 마크다운/코드블럭 렌더링 | screenshots 02/04/08 — headings, lists, fenced code. Sanitisation locked by `test_render_markdown_js.py` (5 XSS payloads). |
| 우측 채팅 패널 (AI 설명 / 직접 질문 / 꼬리질문) | screenshots 01-04. |
| 핀 표시 (thread 있는 block 우상단) | screenshot 05 — 📌 visible on multiple blocks. |
| 좌측 사이드바 "질문" 탭 + 페이지 점프 | screenshots 06/07. |
