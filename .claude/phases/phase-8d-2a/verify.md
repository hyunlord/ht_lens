# Phase 8d-2a — Verify (self)

마지막 code commit: `e5154ed test(phase-8d-2a): drop stale ALEMBIC_HEAD==0006 assertion`. 작성 직전 `git status` = clean. 2026-05-31. backend(0007+context+/v2/threads+pins) + frontend(chat 패널) + 테스트. RAG/figure/neighbor = 8d-2b.

## 5-A. Automated checks (실측, CI-equivalent)
| Check | Command | Result |
| ----- | ------- | ------ |
| Lint | `uv run ruff check .` | All checks passed |
| Format | `uv run ruff format --check .` | 191 files already formatted |
| Type | `uv run mypy src` | Success: no issues found in 82 source files |
| Test | `uv run pytest -m "not llm and not slow" -q` (coverage 포함) | **714 passed, 1 skipped, 7 deselected in 678.34s** |
| Coverage | 위 + 타깃 측정 | `chunk_chat_context.py` **95%**(직접 테스트), `chunk_chat.py` **53%**(핸들러 본문=TestClient worker-thread 미귀속, 5-D) |
| CI | prototype-reflow — GitHub CI는 8e cutover까지 미발생 | n/a; **jsdom CI provisioning 부채**(8d-1 등록, 8e 전 필수) |

테스트 회계: 692 → **714** (+23 신규 −1 stale): `test_chunk_chat_context`(8) + `test_chunk_chat_api`(10) + `test_chunk_chat_schema`(2) + `test_chat_ui_js`(3); stale `test_alembic_head_is_0006` 제거(head→0007, `test_chunk_chat_schema::test_alembic_head_is_0007`로 대체). 기존 jsdom 28 + 1.x 회귀 green.

## 5-B. Functional checks
### 핵심: 섹션 선택 → 그 섹션 베이스 질문 (라이브 E2E + 단위)
| 검사 | Evidence |
| --- | --- |
| **라이브 qwen 섹션질문 E2E** | 8086 dev(0007) + 실 qwen: section 28.3.5 thread 생성 → "핵심 한 문장 요약" → 정확한 답("지수족 가능도…변분 EM…잠재 요인 추정") → cleanup. **핵심 가치 작동 확인.** |
| 섹션 경계(secNo-depth, 부모=자식) | test_section_range_parent_includes_children |
| 중복 secNo → heading_chunk_id anchor (R1) | test_section_range_duplicate_secno_uses_heading_id |
| 비번호 heading fallback | test_section_range_unnumbered_heading_fallback |
| 섹션 context 전체(≤budget) | test_build_section_context_full_small |
| 큰 섹션 degraded + truncation 메타 (R5/R7) | test_build_section_context_degraded_large |
| 문단 context ±radius(페이지 횡단) | test_build_chunk_context_radius_crosses_pages |
| parse_section_no JS 패리티 | test_parse_section_no_parity_with_js |

### chat API (messages.py 패턴 재사용)
| 검사 | Evidence |
| --- | --- |
| chunk/section thread 생성 | test_create_chunk_and_section_threads |
| doc/chunk 정합 검증 (R4) | test_create_rejects_chunk_doc_mismatch (422) |
| section anchor=heading 강제 | test_section_anchor_must_be_heading (422) |
| 섹션 context가 LLM에 전달 + 영속 | test_post_message_uses_section_context_and_persists |
| LLM 실패 → 무행 (R8) | test_message_llm_failure_writes_no_messages (502, 0 rows) |
| 삭제된 thread post → 404 | test_post_to_deleted_thread_404 |
| FK orphan 방지 (R8 backstop) | test_fk_prevents_orphan_messages |
| 목록 + 메시지 카운트 | test_list_threads_with_counts |
| 핀 생성/목록/삭제 (R3 별도 테이블) | test_pins_create_list_delete |
| 1.x threads 무영향 | test_v2_chat_does_not_touch_1x_threads |

### frontend (chat.js, jsdom)
| 검사 | Evidence |
| --- | --- |
| 문단 vs 섹션 선택 상태 | test_set_selection_paragraph_and_section |
| sectionselect(headingChunkId) 소비 | test_section_select_event_drives_selection |
| assistant HTML sanitize (R7) | test_render_assistant_sanitizes_html (script/onerror/js: 제거, markdown 보존) |
| 라이브 자산 | 8086 chat.js 200, reflow.html 200 |

## 5-C. 1.x 무손상 + additive
- 0007 = **신규 3테이블만**(chunk_threads/chunk_messages/chunk_pins). 1.x threads/messages + 8a/8b 테이블 byte-identical: test_migration_0007_additive_only.
- prod `data/ht_lens.db` 불변(alembic 0004, blocks=49850). dev DB만 0007 업그레이드(사용자 평가용).

## 5-D. Coverage 정직 분해
- `chunk_chat_context.py` **95%**(94 stmt/2 miss): 직접 단위 테스트(섹션 범위/context). miss=방어 분기 일부.
- `chunk_chat.py` **53%**(114/44 miss): miss(87-100 create 본문, 193-234 pins 본문 등)는 **TestClient worker-thread 미귀속**(8c reflow.py 69%와 동일 artifact). 10개 API 테스트가 **응답을 assert**(201/422/202/404/502 + 영속/카운트)하므로 핸들러 실행은 증명됨.

## 5-E. 잔존 한계 (정직, 범위 외)
1. RAG(cross-doc + within-section top-K), figure 채팅, neighbor 재번역 = **8d-2b**(chunk 검색 머신 필요).
2. 큰 섹션은 top-K 아닌 budget 절단(degraded, 명시). char-budget=coarse(token 아님). top-K=8d-2b.
3. 동시 post stale-history = 1.x 상속 한계(기재). 진짜 동시 삭제는 SQLite 락으로 시뮬 불가 → FK backstop로 보장.
4. dev DB live chat은 서버 재기동 필요(완료). jsdom CI provisioning(8e 전).
5. 볼드/영어 fallback = 8e.

## 5-F. Scoring (100, self)
| Item | Score / Max | Evidence |
| ---- | ----------- | -------- |
| 독창성 | 12 / 15 | heading_chunk_id anchor(중복/비번호 robust), degraded 섹션+typed context, 1.x 무 ALTER 신규 테이블, chat.js 격리. 차감: 표준 chat 패턴 재사용. |
| 완결성 | 31 / 35 | 핵심 섹션Q **라이브 E2E** + 문단Q + 핀 + 23 테스트. 차감: RAG/figure/neighbor 8d-2b, 큰 섹션 degraded(top-K 미구현). |
| 안정성 | 27 / 30 | ruff/format/mypy + 714 green + LLM-fail 무행/FK orphan/anchor 검증 잠금 + 1.x 무손상(additive). 차감: 라우터 53% 라인(본문은 assert·5-D), 동시 post 상속 한계. |
| 확장성 | 17 / 20 | /v2 분리, 신규 테이블(8a 가드레일), context 빌더가 8d-2b RAG/figure 토대, secNo-depth 재사용. 차감: 8d-2b가 within-section top-K 추가 필요. |
| **Total** | **87 / 100** | |

## 5-G. Self verdict
- [ ] PASS_CANDIDATE (≥95)
- [x] **submit to cross-verify Round 1** (self 87 < 95, 정직). 핵심 섹션Q 라이브 E2E + 23 테스트(R1–R8 잠금) + 1.x additive 무손상 + 714 green. 잔존은 8d-2b(RAG/figure/neighbor·top-K)·본질적(coverage TestClient·동시성 상속). R1이 새 concrete 결함 없으면 push.
- [ ] FAIL → RE-CODE / RE-PLAN
