# Phase 4 — Viewer Frontend Screenshots

DoD evidence for Phase 4. All captures use the live FastAPI server
(`ht-lens serve --skip-llm-check`) on a DB that has gone through
`extract → ingest → translate` against `tests/fixtures/sample_mixed.pdf`
(6 pages, en → ko, sglang qwen3.6-27b). Captured headless via Playwright
(chromium 147, viewport 1400×900).

| # | File | URL / action | Notes |
| - | ---- | ------------ | ----- |
| 1 | `01-doc-list.png` | `/static/index.html` | Document list — one ingested document card. After the Planner-directed cross-phase fix, the status pill now shows the localised label `번역 완료` (color: ok-green). |
| 2 | `02-page-translation.png` | `viewer.html?doc=1&page=1` | Page 1 in **translation mode**. Korean overlay over the PDF page; sidebar highlights page 1. After the R2 opacity fix (0.78 → 0.92), the underlying English text no longer bleeds through the translated panels. |
| 3 | `03-page-original.png` | Same page after pressing `T` | **Original mode** — blocks become transparent so the PDF's native English text is what the user reads. |
| 4 | `04-page3-translation.png` | Same session, `→ →` keys | Page 3 in translation mode. Shows multi-page navigation via `history.pushState` (no full reload); sidebar page 3 highlighted; header reads `sample_mixed.pdf · page 3/6`. |
| 5 | `05-invalid-doc-error.png` | `viewer.html?doc=999&page=1` | 404 path — sidebar, page-mount, and header are all cleared by `clearViewerDom()`, only the friendly error banner remains. |
| 6 | `06-zoom-150.png` | `Ctrl+↑` twice from page 3 | **Zoom 150%** — two zoom-up steps (1.0 → 1.25 → 1.50). The `.stage { transform: scale }` enlarges both PNG background and block overlay in lockstep without re-fetching. |
| 7 | `07-back-forward.png` | Browser **back** from page 3 | Browser back restores page 2 (sidebar highlight on `2`). Demonstrates `popstate` handler — pushState navigation participates in browser history. |

## Captures not included

| # | Why | Plan |
| - | --- | ---- |
| 08 — rotated page | The only sample fixture (`sample_mixed.pdf`) has no rotated pages. The rotation path is still locked by `test_page_view_handles_rotation` (grep) + the code branch in `page_view.js` that shows the PNG + a "회전 페이지 미지원" banner. | Phase 6 will add a rotated-page fixture along with precise bbox-to-pixel mapping. |
| 09 — partial translation | All blocks in the current DB translated successfully (`stats.failed == 0`). The `partial_translated` status path and the `data-fallback="original"` dotted-underline visual are still locked by `test_translate_sets_document_status_partial_on_failures` and CSS grep tests. | Phase 6 will introduce a deliberate partial-translation fixture (LLM permanent failure on selected blocks) for screenshot capture. |

## Capture environment

- OS: Linux (Ubuntu host of dev workstation)
- Browser: Chromium 147 via Playwright (headless, viewport 1400×900)
- Server: `uvicorn` via `ht-lens serve --port 8105 --skip-llm-check`
- DB: `/tmp/ht_lens_phase3.db` (carried over from Phase 3 verify; after the
  Phase 2/3 cross-phase fix, `Document.status` was migrated to `translated`
  via a one-off update before recapture)

## Reproducing the captures

```bash
ht-lens serve --port 8105 --db /tmp/ht_lens_phase3.db --skip-llm-check &
sleep 3
# Any Python env with playwright + a chromium build can drive the flow.
# In this repo we used a one-shot helper at /tmp/take_screens.py
# (intentionally not tracked — Playwright is not a project dep yet;
# Phase 6 will introduce the proper UI regression suite).
```

Manual reproduction:

1. open `/static/index.html`
2. open `viewer.html?doc=1&page=1` (translation default)
3. press `T` (original)
4. press `T` (back), then `→ →` (page 3)
5. `Ctrl+↑ Ctrl+↑` (zoom 150)
6. Browser **back** (popstate)
7. open `viewer.html?doc=999&page=1` (error)

## Spot-check observations (Phase 4 DoD, after Planner-directed fix)

- **"실제 문서 한 권을 자연스럽게 읽을 수 있음"** — 03, 04, 07: 페이지 1↔2↔3을 reload 없이 자유롭게 이동, sidebar 동기화, back/forward 모두 동작.
- **"한/영 폰트 fitting 80% 이상 만족"** — 본문 paragraph + Figure caption은 깔끔 fit. 짧은 제목/라벨에서 ~10% overflow는 잔존. canvas.measureText + binary search.
- **"줌·이동 부드러움"** — 06 zoom 150%. CSS scale로 즉시 enlarge, PNG는 30일 캐시, navToken으로 race condition 차단.
- **"이미지 위 텍스트 z-index"** — translation 모드는 opacity 0.92 panel로 source bleed-through 제거 (02 screenshot), original 모드는 transparent (03 screenshot).
- **에러 경로** — 05: sidebar/page/header 모두 클리어.

## Cross-phase fix evidence

R2 cross-verify가 발견한 `Document.status` stale 문제는 `translate/pipeline.py`의 `_finalize_document_status()`에서 fix. 회귀 테스트 `test_translate_sets_document_status_translated_on_full_success` + `test_translate_sets_document_status_partial_on_failures`가 잠금. UI 측면에서는 `index.js`의 `STATUS_LABELS`가 5가지 status 모두 친화적 라벨로 표시.
