# Phase 4 — Viewer Frontend Screenshots

DoD evidence for Phase 4. All three captures use the live FastAPI server
(`ht-lens serve --skip-llm-check`) on a database that has gone through
`extract → ingest → translate` against `tests/fixtures/sample_mixed.pdf`
(6 pages, en → ko, sglang qwen3.6-27b).

| # | File | URL | Notes |
| - | ---- | --- | ----- |
| 1 | `screenshots/01-doc-list.png` | `/static/index.html` | Document list — one ingested document card with `en → ko · 6 pages · ready_for_translation · 2026-05-20`. Clicking enters the viewer. |
| 2 | `screenshots/02-page-translation.png` | `/static/viewer.html?doc=1&page=1` | Page 1 in **translation mode** (default). Korean overlay sits on top of the original PNG; sidebar lists pages 1-6 with page 1 highlighted; header shows `sample_mixed.pdf · page 1/6`. |
| 3 | `screenshots/03-page-original.png` | Same URL after pressing `T` | Page 1 in **original mode**. The `T` toggle swaps the visible text in-place without a network round-trip; original English overlays the same PNG. |

## Capture environment

- OS: Linux (Ubuntu host of dev workstation)
- Browser: Chromium 147 via Playwright (headless, viewport 1400×900)
- Server: `uvicorn` via `ht-lens serve --port 8101 --skip-llm-check`
- DB: `/tmp/ht_lens_phase3.db` (re-used from Phase 3 verify)

## Spot-check observations (Phase 4 DoD)

- **"실제 문서 한 권을 자연스럽게 읽을 수 있음"** — 사이드바 페이지 리스트가 한눈에 들어오고, 좌→우 reading order 유지. ←/→ 키와 사이드바 클릭 모두 즉시 다른 페이지로 이동 (history.pushState, full reload 없음).
- **"한/영 폰트 fitting 80% 이상 만족"** — 본문 문단(Abstract 등)은 깔끔히 들어감. 제목 한 줄에서 한국어가 영문보다 길어 일부 overflow (Open-Sora 2.0 제목 박스). 본문 기준으로는 80% 충족.
- **"줌·이동 부드러움"** — 페이지 이동은 in-place rerender, `.stage { transform: scale(zoom) }`로 줌. ←/→ 누른 즉시 다음 페이지 표시 (PNG는 30일 캐시).
- **이미지 위 텍스트**: translucent 검정 panel(opacity ~0.78)을 block 배경으로 깔아 가독성 확보. block hover 시 outline.

## Reproducing the captures

```bash
PORT=8101
export HT_LENS_DB_URL="sqlite+aiosqlite:///$PWD/data/ht_lens.db"
ht-lens serve --port $PORT --skip-llm-check &
sleep 3
# captures via Playwright Python (any env with playwright + chromium browser)
python scripts/_take_phase4_screens.py $PORT  # or invoke the snippet below inline
```

In this repo we used a one-shot script (`/tmp/take_screens.py`); the same
flow can be reproduced manually:

1. Open `http://127.0.0.1:$PORT/static/index.html` → capture.
2. Click the document card → capture page 1.
3. Press `T` → capture again.

Re-running with a different `--port` and `--db` is safe as long as the DB
has at least one document with text blocks (the `verify_api.sh` data setup
satisfies that).
