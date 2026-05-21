# Phase 6c — Viewer Polish screenshots

DoD evidence for Phase 6c (v0.6 milestone). Captures via
`scripts/phase6c_scenario.py` (Playwright + chromium headless, viewport
1600×1000). The live server uses the operator's `.env` so the LLM is
real `qwen3.6-27b` (no mock fall-through).

| # | File | Notes |
| - | ---- | ----- |
| 1 | `01-fit-to-width-default.png` | 진입 즉시 `ResizeObserver` + `computeFitZoom`이 ZOOM_STEPS의 가장 큰 ≤ target step으로 자동 snap. 사용자가 Ctrl+ArrowUp을 누른 적 없으므로 `state.zoomIsAuto === true`. |
| 2 | `02-sidebar-collapsed.png` | `#sidebar-toggle` 클릭 → `.viewer-shell--sidebar-closed` 클래스 토글 → grid-template-columns `220px 1fr 0` → `0 1fr 0`. 페이지 영역이 즉시 넓어짐. localStorage `ht_lens.sidebarOpen=0`. |
| 3 | `03-sidebar-expanded.png` | 토글 한 번 더 → 다시 220px 사이드바 복귀. localStorage `ht_lens.sidebarOpen=1`. |
| 4 | `04-natural-scroll-mid.png` | 페이지 3까지 scrollToPage 후 추가 200px scrollBy. `mounted_pages = [1, 2, 3, 4, 5]` — 페이지 6이 mount 안 됐던 v0.5 버그는 rootMargin 200% + `pickActivePage` 미드포인트 선택으로 해결. |
| 5 | `05-logo-back-to-index.png` | `.app-logo` (좌상단 `ht_lens` 텍스트) 클릭 → `/static/index.html` 이동. 다른 SPA 라우팅 없이 단순 `<a href>` — v0.6 폴리시. |
| 6 | `06-real-llm-response.png` | block 클릭 후 채팅 패널이 열린 viewer 상태. 라이브 LLM 호출은 별도 curl 검증으로 evidence (verify §2). |

## Live LLM evidence

```
$ pgrep -P $(cat ~/.ht_lens/server.pid) | xargs -I{} \
    sh -c 'tr "\0" "\n" < /proc/{}/environ | grep ^LLM_'
LLM_BASE_URL=http://localhost:8081/v1
LLM_MODEL=qwen3.6-27b
LLM_PROVIDER=openai_compat
```

```
$ POST /threads/{id}/explain (qwen3.6-27b, LLM_TIMEOUT=300)
latency: 93.24s
model: 'qwen3.6-27b'
content: '제시해주신 텍스트는 **Open-Sora 2.0**이라는 인공지능(AI) 비디오
         생성 모델의 논문 또는 기술 보고서의 **표지(Header)** 부분에
         해당합니다…'
```

DB `messages.model` 컬럼이 `qwen3.6-27b`로 기록됨 (verify §3). Mock
fall-through 사라짐.

## Reproducing the captures

```bash
scripts/dev_serve.sh restart   # .env 자동 로드 (load_dotenv in create_app)
python scripts/phase6c_scenario.py 8080
```

## Notes

- `LLM_TIMEOUT` 기본값 60초는 sglang qwen3.6-27b 추론에 짧음. operator
  가 `.env`에 `LLM_TIMEOUT=300` 추가하면 안정적 — Phase 6c 코드 변경
  scope 외 (operator config).
- 6c는 viewer polish만 — 핀 디자인 / 사이드바 리사이즈 / streaming / 모델
  토글은 Phase 6e.
