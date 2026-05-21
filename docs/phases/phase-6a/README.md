# Phase 6a — Critical UX gaps screenshots

DoD evidence for Phase 6a (v0.4 milestone). All captures use the live
FastAPI server + sglang qwen3.6-27b. Driver: Playwright (chromium 147,
viewport 1600×1000). The tracked driver is `scripts/phase6a_scenario.py`
(if you want to re-run it after a code change).

| # | File | Notes |
| - | ---- | ----- |
| 1 | `01-search-modal-open.png` | Cmd/Ctrl+K opens the search modal. The card is centered on a blurred backdrop, input focused, "두 글자 이상 입력하세요" status row visible. |
| 2 | `02-search-results.png` | Query `비디오` returns matches with `<mark>` highlighting on the matched substring. Result rows show `doc · p.N · block_local_id (matched_field)` headers. |
| 3 | `03-search-jump.png` | Pressing Enter on the first result navigated to its page, opened the chat panel on that block, and flash-outlined the block (yellow keyframe in 1.5s). |
| 4 | `04-export-button.png` | Sidebar "❓ 질문" tab with the new "📥 마크다운으로 내보내기" button at the top. Below it the existing 10 threads from Phase 5 are listed. |
| 5 | `05-export-toast.png` | Click triggers a `fetch + Blob + URL.createObjectURL` download. A success toast confirms `ht_lens-1-questions.md 다운로드 완료`. |
| 6 | `06-retranslate-confirm.png` | Right-click on a text block opens the confirm modal "이 단락을 LLM에 다시 번역 요청하시겠습니까?" with a preview of the original text. |
| 7 | `07-retranslate-result.png` | After confirming, the LLM call completes (qwen3.6-27b live), the block translation is replaced in place, and a success toast appears. |

## DoD spot-check

- **Cmd+K로 임의 문구 찾고 점프 (latency < 200ms, 10K blocks)** — covered by
  `test_api_search.py::test_search_10k_blocks_latency_under_budget`.
  Measured ~4ms on a 10K synthetic-row fixture (TestClient roundtrip
  included). Production margin is comfortable.
- **질문 export markdown 받기 + 사람이 읽기 좋음** — screenshots 04/05 +
  `test_api_export.py::test_export_blockquotes_assistant_markdown` lock
  the blockquote-prefix safety so nested headings/code fences cannot
  break the outer structure.
- **block 우클릭 → 재번역 → 갱신** — screenshots 06/07 + 6 retranslate
  tests including transient/permanent atomicity (no partial rows).

## Reproducing the captures

```bash
cp /tmp/ht_lens_phase5.db /tmp/ht_lens_phase6a.db
export LLM_PROVIDER=openai_compat \
       LLM_BASE_URL=http://localhost:8081/v1 \
       LLM_MODEL=qwen3.6-27b \
       LLM_TIMEOUT=300
ht-lens serve --port 8211 --db /tmp/ht_lens_phase6a.db &
sleep 4
# Any env with playwright + chromium works.
python /tmp/phase6a_scenario.py 8211
```

The retranslate step in screenshot 7 takes 30-90s on this LLM endpoint.
