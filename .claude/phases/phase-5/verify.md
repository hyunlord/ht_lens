# Phase 5 — Verify (self, v1)

작성 직전 `git status` clean. 본 verify는 head 시점에 대한 self-evaluation.

## 5-A. Automated checks

| Check    | Command | Result |
| -------- | ------- | ------ |
| Lint     | `uv run ruff check .` | All checks passed! |
| Format   | `uv run ruff format --check .` | already formatted |
| Type     | `uv run mypy src/` | Success: no issues found in 49 source files |
| Test (fast) | `make test-fast` → `pytest -m "not llm and not slow"` | **256 passed, 5 deselected** in 91.40s |
| Coverage | `make check` 내장 | TOTAL 74% (Phase 5 JS는 node 기반 알고리즘 테스트로 검증) |
| Test (vendor + xss) | `pytest tests/integration/test_vendor_runtime.py tests/integration/test_render_markdown_js.py` | **8 passed** (node + jsdom) |
| CI (local) | `make check` | **RC=0** |
| CI (remote) | `.github/workflows/ci.yml` push trigger | pending push |
| Shellcheck | pre-commit + CI step | clean |

Phase 5 신규 자동 테스트 **23건** (233 → 256, +23):
- `test_static_serving.py` 확장 (+15): 9 정적 자산 + render_markdown DOMPurify 마커 + block multi-thread + viewer refetch / panelToken / Esc + state localStorage keys + viewer.html chat_panel.css + keyboard Esc/Ctrl+B
- `test_vendor_runtime.py` (3): marked ESM importable + DOMPurify ESM factory + vendor 파일 존재
- `test_render_markdown_js.py` (5): XSS — script tag / javascript: href / iframe / onerror / external link 새 탭

## 5-B. Functional checks (live LLM)

### 1) 10-question scenario (Playwright + chromium + sglang qwen3.6-27b)

helper `/tmp/phase5_scenario.py` (untracked — Playwright는 project dep 아님). 약 25분 소요. 결과:

```
threads: 10
total messages: 22
```

10 thread 분포:
| Thread | Block | Page | Title (truncated) | Messages |
| ------ | ----- | ---- | ----------------- | -------- |
| 1 | 2  | 1 | Open-Sora Team                       | 2 |
| 2 | 3  | 1 | HPC-AI Tech                          | 4 |
| 3 | 4  | 1 | Abstract                             | 2 |
| 4 | 38 | 2 | The past year has witnessed an...    | 2 |
| 5 | 39 | 2 | In this report, however, we show...  | 2 |
| 6 | 51 | 3 | 768px                                | 2 |
| 7 | 40 | 2 | We show the human preference...      | 2 |
| 8 | 41 | 2 | This report is structured as...      | 2 |
| 9 | 42 | 2 | 2                                    | 2 |
| 10 | 76 | 4 | (long English title)                 | 2 |

Thread 2 (HPC-AI Tech)에 explain + follow-up + 추가 질문/응답 4건. 나머지는 explain pair 2건. 총 22 messages = 11 user + 11 assistant.

### 2) Screenshots (10장)

- 01-block-click-empty.png — empty thread + AI 설명 CTA
- 02-explain-response.png — 한국어 markdown (heading + bullets + inline code)
- 03-direct-question.png — 직접 질문 후
- 04-followup-question.png — 같은 thread 꼬리질문
- 05-pins-on-blocks.png — 페이지 1 핀 3개
- 06-sidebar-questions-tab.png — ❓ 질문 탭 + 10 threads
- 07-thread-jump-from-list.png — thread 클릭 → 페이지 점프 + 패널
- 08-markdown-render.png — markdown 렌더 클로즈업
- 09-ten-questions-accumulated.png — 10 thread DoD evidence
- 10-localstorage-restore.png — 새로고침 후 복원

### 3) DoD 항목별 evidence

| DoD | 만족 | 근거 |
| --- | ---- | ---- |
| 문서 한 권 읽으며 10개 이상 질문 자연스럽게 누적 | ✅ | 10 threads, 22 messages. screenshots 06/09. |
| 닫았다 다시 열어도 핀/스레드 그대로 | ✅ | localStorage (`panelOpen`, `activeThreadId`, `activeBlockId`, `sidebarTab`) + 페이지 진입 시 `listThreadsForDoc` → 핀 갱신. screenshot 10. |
| 마크다운/코드블럭 렌더링 | ✅ | marked + DOMPurify. screenshot 08. XSS 5종 stripped (node + jsdom test). |
| 우측 채팅 패널 | ✅ | screenshots 01-04. |
| 핀 표시 | ✅ | screenshot 05. block `data-has-thread` + `data-thread-count`. |
| 좌측 사이드바 질문 탭 + 점프 | ✅ | screenshots 06/07. |

### 4) LLM 호출 통계

- 총 호출: ~12 (10 explains + 2 직접질문/꼬리질문)
- 평균 latency: explain 60-180초, follow-up 30-60초 (qwen3.6-27b @ sglang)
- 실패: 1 (thread 8 explain timeout) → retry 100% 복구
- Cache: chat API 자체는 cache 없음 (Phase 2b translate cache만)

### 5) 정적 자산 spot-check

```
$ curl -sI http://localhost:8200/static/vendor/marked.esm.js → 200
$ curl -sI http://localhost:8200/static/vendor/purify.es.mjs → 200
$ curl -sI http://localhost:8200/static/js/components/chat_panel.js → 200
$ curl -sI http://localhost:8200/static/css/chat_panel.css → 200
$ curl -s http://localhost:8200/threads?doc_id=1 → 10 threads
```

## 5-C. Regression check

Phase 4 본체 무회귀:
- Phase 4 grep tests (clearViewerDom, navToken, overlay data-mode, snapToStep) 통과
- `test_font_fit_js.py` 4 tests 통과
- Phase 4 키보드 (T / ←→ / Ctrl+↑↓ / Home/End) 그대로
- Phase 5 추가: Esc, Ctrl+B (debate ACCEPT)

Phase 3 API 무회귀:
- API 변경 없음 (read endpoint 사용만)
- chat/messages 동작 그대로

Phase 1/2 unit/integration: 모두 통과 (256 fast tests).

### Deviations from challenge (의도적 design call)

- challenge §5 "test_chat_post_roundtrip": Phase 3 `test_get_thread_returns_messages_in_order`에서 server roundtrip 검증 + Phase 5 viewer.js grep으로 client refetch 검증 (`getThreadDetail` + `ensureThreadDetail` 마커).
- client thread title 생성 제거 — server `_default_thread_title()` 단일 source.

## 5-D. Scoring (100, v1)

| Item       | Score / Max | Evidence |
| ---------- | ----------- | -------- |
| 독창성     | 14 / 15     | vendor ESM (build 0) + CustomEvent로 component 디커플 + multi-thread per block + write-then-refetch 패턴 + panelToken async cancellation. |
| 완결성     | 33 / 35     | DoD 6 + 10 screenshots + 10 threads/22 messages + XSS 5종. 감점: 자연스러운 사용자 흐름 시연은 1 thread만 깊은 대화 (#2). 나머지는 explain pair. |
| 안정성     | 28 / 30     | panelToken + refetch + persist + DOMPurify + vendor smoke. 감점: Playwright UI 회귀 suite 부재 (수동 시나리오 + grep). |
| 확장성     | 19 / 20     | components 분리 + ESM 패턴 → Phase 6 streaming/SSE 도입 시 컴포넌트 재사용. 감점: pin은 별도 컴포넌트 없이 block.js inline (plan §17 의도). |
| **Total**  | **94 / 100** | |

## 5-E. Self verdict

- [ ] PASS_CANDIDATE (≥95)
- [x] PASS_CANDIDATE_94 → R1 cross-verify 결과 따라 RE-CODE 가능성
- [ ] FAIL → RE-PLAN

근거:
- DoD 6 모두 evidence (자동 + 시각). 10 threads / 22 messages / localStorage 복원 / XSS guard.
- 256 fast tests + 8 vendor/XSS tests + `make check` RC=0
- self 94 — 95 threshold에 1점 부족. R1 결과로 confirm or RE-CODE.
