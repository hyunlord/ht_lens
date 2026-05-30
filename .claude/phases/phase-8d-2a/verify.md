# Phase 8d-2a — Verify (self) — v2 (post RE-CODE, verify-cross R1)

마지막 code commit: `87fde93` (fix + test, verify-cross R1 대응). 작성 직전 `git status` = clean. 2026-05-31. v2 = R1 DOWNGRADE(~79) 실 결함 2개(중복섹션 frontend, stale transcript) fix + CHECK + chat flow 테스트.

## 5-A. Automated checks (실측, CI-equivalent)
| Check | Command | Result |
| ----- | ------- | ------ |
| Lint | `uv run ruff check .` | All checks passed |
| Format | `uv run ruff format --check .` | clean |
| Type | `uv run mypy src` | Success: no issues found in 82 source files |
| Test | `uv run pytest -m "not llm and not slow" -q` (coverage 포함) | **718 passed, 1 skipped, 7 deselected in 552.79s** |
| Coverage | 타깃 측정 | `chunk_chat_context.py` 95%; `chunk_chat.py` 53%(핸들러 본문=TestClient worker-thread 미귀속, 5-D 동일) |
| CI | prototype-reflow — GitHub CI 미발생(8e 전) | n/a (jsdom CI provisioning 부채, 8d-1 등록) |

테스트 회계: 714 → **718** (+4 RE-CODE): `test_select_section_by_heading_resolves_duplicates` + `test_set_selection_clears_transcript` + `test_ask_creates_thread_posts_and_renders` + `test_pin_posts_and_reloads`.

## 5-B. verify-cross R1 DOWNGRADE → 처리 (실 결함 2 + gap 2)
| R1 항목 | 종류 | 처리 | Evidence |
| --- | --- | --- | --- |
| §4 중복-섹션 fix가 frontend 경로에 미적용(secNo-first) | **실 결함** | `selectSectionByHeading(headingChunkId)`+`computeSectionByHeading`; renderToc→node.chunkId; reflow.js 사용 | test_select_section_by_heading_resolves_duplicates (2번째 28.4→자기 범위) |
| §3 setSelection이 transcript 미정리 → 다른 anchor 대화 잔존 | **실 UX 결함** | setSelection이 `#chat-messages` clear | test_set_selection_clears_transcript |
| §4 chat ask/pin fetch flow 미테스트 | gap | mocked fetch로 ask/pin 잠금 | test_ask_creates_thread_posts_and_renders(payload+assistant render), test_pin_posts_and_reloads |
| §4 anchor_type DB CHECK 부재 | 강화 | 0007 + ORM `__table_args__`에 CHECK | test_migration_0007_additive_only(여전히 additive) + api 유효 insert green |
| §1 "CI-equivalent" 라벨 / §2 live E2E 약한 증거 | 정직 | live qwen E2E = smoke(재현 transcript 없음); 검증은 단위/통합 테스트. CI는 jsdom 부채(8e). | 5-E |

## 5-C. Regression check (RE-CODE — CLAUDE.md 필수)
RE-CODE = frontend 로직 수정 + DB CHECK + 테스트. 변경별 잠금:
| 변경 | 새 코드 경로 / 새 함수 | 잠금 단위 테스트 |
| --- | --- | --- |
| sections.js 중복-안전 섹션 anchor | `computeSectionByHeading`/`selectSectionByHeading` (신규 export) | test_select_section_by_heading_resolves_duplicates |
| renderToc onSelect → node.chunkId; reflow.js → selectSectionByHeading | 콜백 chunkId 전달 | 위 + 기존 test_render_toc_nested_with_callbacks(green) |
| chat.js setSelection clear transcript | `#chat-messages` 정리 분기 | test_set_selection_clears_transcript |
| chat.js export pinCurrent + ask/pin flow | (기존 fn, 이제 fetch 잠금) | test_ask_creates_thread_posts_and_renders, test_pin_posts_and_reloads |
| 0007 + models anchor_type CHECK | `ck_chunk_threads_anchor_type` | test_migration_0007_additive_only |

**grep 증거**: `selectSectionByHeading`/`computeSectionByHeading`(sections.js + test), `setSelection`+`replaceChildren`(chat.js) + test_set_selection_clears_transcript, `pinCurrent` export + test_pin_posts_and_reloads, `ck_chunk_threads_anchor_type`(0007 + models.py). **회귀 0**: 714→718(+4 신규만), 기존 jsdom/backend green. 새 production 함수 2개(computeSectionByHeading/selectSectionByHeading)는 위 표대로 테스트 잠금; CHECK는 additive 테스트 + api insert로 잠금.

## 5-D. Coverage 정직 분해
`chunk_chat_context.py` 95%(직접 단위 테스트). `chunk_chat.py` 53% — miss는 HTTP 핸들러 본문(TestClient worker-thread 미귀속, 8c reflow.py 동일 artifact); 10 API 테스트가 응답(201/422/202/404/502+영속/카운트) assert로 실행 증명.

## 5-E. 잔존 한계 (정직, 범위 외)
1. RAG(cross-doc + within-section top-K), figure 채팅, neighbor 재번역 = **8d-2b**.
2. 큰 섹션 = budget 절단 degraded(top-K=8d-2b). char-budget=coarse(token 아님).
3. 동시 post stale-history = 1.x 상속(기재); 진짜 동시 삭제는 SQLite 락으로 시뮬 불가 → FK + rollback re-check backstop.
4. live qwen E2E = smoke(섹션 28.3.5 정확 요약 확인); 재현 검증은 단위/통합. dev DB CHECK는 0007 적용 후 추가됨→dev DB엔 없음(재생성 시 반영; API가 enforce).
5. jsdom CI provisioning(8e 전), 볼드/영어 fallback(8e).

## 5-F. Scoring (100, self)
| Item | Score / Max | 근거 (R1 대비) |
| ---- | ----------- | -------- |
| 독창성 | 12 / 15 | heading_chunk_id anchor(이제 frontend도 일관)+degraded+typed context+1.x additive. (R1 confirm 12) |
| 완결성 | 31 / 35 | 핵심 섹션Q live E2E + 문단Q + 핀 + **중복 fix + ask/pin flow 테스트**(R1 gap 폐쇄). 차감: RAG/figure/neighbor 8d-2b. (R1 28→회복) |
| 안정성 | 27 / 30 | 718 green + **stale transcript fix + anchor CHECK** + LLM-fail/FK/anchor 검증. 차감: 라우터 53% 라인(5-D), 동시 post 상속. (R1 24→회복) |
| 확장성 | 17 / 20 | frontend가 heading chunk id 사용(R1 secNo-only 지적 해소)+context 빌더 8d-2b 토대. 차감: within-section top-K 8d-2b. (R1 15→회복) |
| **Total** | **87 / 100** | R1 실 결함 2개 fix로 docking 회복; 잔여는 8d-2b·본질적. |

## 5-G. Self verdict
- [ ] PASS_CANDIDATE (≥95)
- [x] **submit to cross-verify Round 2 (최종, cap)** (self 87 < 95, 정직). R1 실 결함 2개(중복섹션 frontend, stale transcript) fix + 테스트 잠금, chat ask/pin flow 잠금, anchor CHECK. 새 production fn 2개 테스트 잠금(5-C). 잔존은 8d-2b(RAG/figure/neighbor·top-K)·본질적(coverage TestClient·동시성). R2가 새 concrete 결함 없으면 push.
- [ ] FAIL → RE-PLAN
