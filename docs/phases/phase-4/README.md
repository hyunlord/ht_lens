# Phase 4 — Viewer Frontend Screenshots

DoD evidence for Phase 4. All captures use the live FastAPI server
(`ht-lens serve --skip-llm-check`) on a DB that has gone through
`extract → ingest → translate` against `tests/fixtures/sample_mixed.pdf`
(6 pages, en → ko, sglang qwen3.6-27b). Captured headless via Playwright
(chromium 147, viewport 1400×900).

| # | File | URL / action | Notes |
| - | ---- | ------------ | ----- |
| 1 | `screenshots/01-doc-list.png` | `/static/index.html` | Document list — one ingested document card with `en → ko · 6 pages · ready_for_translation · 2026-05-20`. |
| 2 | `screenshots/02-page-translation.png` | `viewer.html?doc=1&page=1` | Page 1 in **translation mode**. Korean overlay over the PDF page; sidebar lists pages 1-6 with page 1 highlighted. Translucent dark panels cover blocks so the source text never bleeds through (RE-CODE r1 fix). |
| 3 | `screenshots/03-page-original.png` | Same page after pressing `T` | **Original mode** — blocks become transparent so the PDF's native English text is what the user reads. No double-rendered text (RE-CODE r1 fix vs initial round). |
| 4 | `screenshots/04-page3-translation.png` | Same session, two `→` key presses | Page 3 in translation mode. Shows multi-page navigation works without full reload (`history.pushState`), sidebar page 3 highlighted, header `sample_mixed.pdf · page 3/6`. |
| 5 | `screenshots/05-invalid-doc-error.png` | `viewer.html?doc=999&page=1` | 404 path — sidebar, page-mount, and header are all cleared (`clearViewerDom()`), only the friendly error banner remains (RE-CODE r1 fix vs initial round where stale content was retained). |

## Capture environment

- OS: Linux (Ubuntu host of dev workstation)
- Browser: Chromium 147 via Playwright (headless, viewport 1400×900)
- Server: `uvicorn` via `ht-lens serve --port 8103 --skip-llm-check`
- DB: `/tmp/ht_lens_phase3.db` (carried over from Phase 3 verify)

## Reproducing the captures

```bash
ht-lens serve --port 8103 --db /tmp/ht_lens_phase3.db --skip-llm-check &
sleep 3
# Any Python env with `playwright` + `chromium` browser installed works.
# In this repo we used a one-shot helper at /tmp/take_screens.py (not
# tracked); the steps reduce to:
#   1. open /static/index.html
#   2. open viewer.html?doc=1&page=1  (translation mode is default)
#   3. press T
#   4. press T (back to translation), then → → (page 3)
#   5. open viewer.html?doc=999&page=1 (error path)
```

A tracked reproduction script is intentionally not added — Playwright is
not a project dep (Phase 4 forbids new deps) and Phase 6's UI regression
suite will introduce the proper recorded flow.

## Spot-check observations (Phase 4 DoD)

- **"실제 문서 한 권을 자연스럽게 읽을 수 있음"** — sidebar로 6 페이지 모두 접근 + ←/→ + history.pushState (full reload 없음). 04 screenshot이 multi-page 흐름 evidence.
- **"한/영 폰트 fitting 80% 이상 만족"** — 본문 문단 (Abstract, Figure caption) 깔끔 fit. 짧은 제목/라벨에서 한국어가 영문보다 길어 ~10% block에서 overflow (Open-Sora 2.0 메인 제목). 본문 기준 ~92% 만족. canvas.measureText + binary search가 핵심 로직.
- **"줌·이동 부드러움"** — pushState in-place rerender + `.stage { transform: scale }` + PNG는 30일 캐시. multi-page 키보드 nav는 무딜리 없음.
- **"이미지 위 텍스트 z-index"** — translation 모드는 translucent 검정 panel로 가독성 확보, original 모드는 transparent block + hover 시만 약한 outline.
- **"회전 페이지"** — sample_mixed.pdf에는 회전 페이지가 없어 viewer가 rotation banner 경로를 자동 캡처할 수 없음. 대신 `test_page_view_handles_rotation` grep test로 코드 경로 잠금, 그리고 rotation != 0일 때 PNG는 표시하고 overlay만 생략하는 fallback이 명시됨.
- **에러 경로** — `viewer.html?doc=999`처럼 잘못된 query에 대해 sidebar/page-mount 모두 클리어 (05 screenshot), `currentDoc`/`currentPage` 초기화로 stale state 누락.
