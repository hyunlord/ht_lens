# Phase 8d-2a — Verify (self) — v3 (post R2 micro-fix)

마지막 code commit: `647076d test(phase-8d-2a): lock anchor_type CHECK + TOC select callback`. 작성 직전 `git status` = clean. 2026-05-31. v3 = cross-verify R2 DOWNGRADE(~83) evidence gap 2건(CHECK 미테스트, TOC 콜백 미잠금) 폐쇄 + wording 정정. Planner-directed micro-fix(**test-only → production 무변경 → R3 없음**).

## 5-A. Automated checks (실측)
| Check | Command | Result |
| ----- | ------- | ------ |
| Lint | `uv run ruff check .` | All checks passed |
| Format | `uv run ruff format --check .` | clean |
| Type | `uv run mypy src` | Success: no issues found in 82 source files |
| Test | `uv run pytest -m "not llm and not slow" -q` | **720 passed, 1 skipped, 7 deselected in 668.36s** |
| Coverage | v2 측정 불변(R2 micro-fix=test-only, src 무변경) | `chunk_chat_context.py` 95%, `chunk_chat.py` 53%(TestClient worker-thread, 5-D) |
| CI | prototype-reflow — GitHub CI 미발생(8e 전) | n/a (jsdom CI provisioning 부채, 8d-1 등록) |

테스트 회계: 714 → v2 718(+4 R1) → **v3 720(+2 R2)**: `test_anchor_type_check_rejects_invalid` + `test_toc_select_button_passes_heading_chunk_id`.

## 5-B. cross-verify R1 + R2 처리
### R1 DOWNGRADE(~79) 실 결함 2 → fix (v2, 확인됨 by R2)
| R1 항목 | 처리 | Evidence |
| --- | --- | --- |
| 중복-섹션 frontend(secNo-first) | selectSectionByHeading(headingChunkId) | test_select_section_by_heading_resolves_duplicates |
| stale transcript | setSelection이 #chat-messages clear | test_set_selection_clears_transcript |
| chat ask/pin flow 미테스트 | mocked fetch 잠금 | test_ask_creates_thread_posts_and_renders, test_pin_posts_and_reloads |

### R2 DOWNGRADE(~83) evidence gap → 폐쇄 (v3, **functional 결함 아님**)
| R2 항목 | 처리 | Evidence |
| --- | --- | --- |
| #1 DB CHECK 미테스트 | invalid anchor_type 직접 insert → IntegrityError | **test_anchor_type_check_rejects_invalid** |
| #2 TOC 버튼 콜백 미잠금(핵심 product path) | 렌더 후 `.toc-select` 클릭 → onSelect가 node.chunkId 수신 | **test_toc_select_button_passes_heading_chunk_id** |
| #3 computeSectionByHeading grep 과장 | **정정**: 직접 grep 아님 — `selectSectionByHeading` 경유 **간접** 테스트(test_select_section_by_heading_resolves_duplicates). 직접 export identifier는 테스트 파일에 미등장. | 5-C |
| #4 pinCurrent가 loadPins await 안 함 | minor async edge; test_pin_posts_and_reloads가 polling으로 eventual render 확인. 호출자 await 보장 아님(기재). | 5-E |

## 5-C. Regression check (R2 micro-fix — CLAUDE.md)
R2 = **test-only**(production 무변경). 변경별 잠금:
| 변경 | 대상 코드 경로 | 잠금 단위 테스트 |
| --- | --- | --- |
| anchor_type CHECK 검증 | `ck_chunk_threads_anchor_type`(0007+models) | test_anchor_type_check_rejects_invalid (IntegrityError) |
| TOC 버튼 product path | `buildUl` `.toc-select`→`onSelect(node.chunkId)` (sections.js) | test_toc_select_button_passes_heading_chunk_id (received==chunkId) |

**정직 정정(R2 #3)**: `computeSectionByHeading`는 신규 export지만 테스트에 **직접 identifier 미등장** — `selectSectionByHeading`(직접 테스트됨) 경유 간접 잠금. v2의 "grep 증거"는 이 점에서 과장이었고, v3에서 정정. 새 production 함수 0(R2는 test-only). 회귀: 718→720(+2 신규만), 기존 green.

## 5-D. Coverage 정직 분해
`chunk_chat_context.py` 95%(직접 단위). `chunk_chat.py` 53% — HTTP 핸들러 본문 TestClient worker-thread 미귀속(8c reflow.py 동일); 11 API 테스트(+CHECK)가 응답 assert로 실행 증명.

## 5-E. 잔존 한계 (정직, 범위 외)
1. RAG(cross-doc + within-section top-K), figure 채팅, neighbor 재번역 = **8d-2b**.
2. 큰 섹션 = budget 절단 degraded(top-K=8d-2b). char-budget=coarse.
3. 동시 post stale-history(1.x 상속); 진짜 동시 삭제는 SQLite 락 시뮬 불가 → FK+rollback re-check backstop.
4. pinCurrent→loadPins 비-await(eventual render 테스트됨; 호출자 await 미보장 — minor).
5. live qwen E2E = smoke. dev DB CHECK 미반영(0007 적용 후 추가; API enforce). jsdom CI provisioning(8e 전). 볼드/영어 fallback(8e). secNo-first helper 일부 잔존(jump/ref용).

## 5-F. Scoring (100, self)
| Item | Score / Max | 근거 |
| ---- | ----------- | -------- |
| 독창성 | 12 / 15 | heading_chunk_id anchor(frontend 일관)+degraded+typed context+1.x additive+pins 별도. |
| 완결성 | 31 / 35 | 핵심 섹션Q live E2E + 문단Q + 핀 + flow 테스트 + **TOC product path 잠금**. 차감: RAG/figure/neighbor 8d-2b. |
| 안정성 | 27 / 30 | 720 green + 중복 fix + transcript fix + **CHECK 잠금 + TOC 콜백 잠금**(R2 2건 폐쇄) + LLM-fail/FK/anchor 검증. 차감: 라우터 53% 라인(5-D), 동시 post 상속. |
| 확장성 | 17 / 20 | frontend heading chunk id 일관 + context 빌더 8d-2b 토대. 차감: within-section top-K 8d-2b. |
| **Total** | **87 / 100** | R1 실 결함 fix + R2 evidence gap 폐쇄. 잔여는 8d-2b·본질적(coverage/동시성). |

## 5-G. Self verdict
- [x] **PASS_CANDIDATE (Planner-directed micro-fix 완료 → push, R3 없음)**. self **87**. R1 실 결함 2개 fix+lock(R2 확인), R2 evidence gap 2건(CHECK·TOC 콜백) 테스트 폐쇄, wording 정정. **production 무변경(test-only)** → CLAUDE.md cap 준수, R3 cross-verify 미호출. 잔존(8d-2b RAG/figure/neighbor·top-K, coverage TestClient·동시성 상속)은 정직 기재.
- 87<95이나 cross-verify cap(R2) + Planner 결정(micro-fix→push). Codex R2 "not a reject-level phase, important R1 defects fixed".
- [ ] FAIL → RE-PLAN (해당 없음)
