# Phase 8d-2a — Challenge

Codex가 실 설계결함(섹션 anchor=sec_no)을 잡음. anchor를 **heading_chunk_id**로 전환(핵심 수정). 대부분 accept. 아키텍처(신규 v2 테이블 + context 빌더 + chat 엔드포인트 + 패널)는 유지 → PASS w/ revisions.

## Debate responses
### 1. Over-engineering
- **accept (frontend 범위)**: chat을 **별도 `chat.js` 모듈**로 격리, `reflow.js`는 선택 상태 hook만(최소). reflow.js 재작성 방지.
- **accept (핀 분리)**: "핀=빈 thread" 오버로드 폐기 → **별도 `chunk_pins` 테이블**. 핀(북마크)과 thread(대화) 분리. 핀 UI는 최소(버튼+목록+점프).
- **accept (큰 섹션)**: 8d-2a 섹션Q는 **소/중 섹션** 핵심. 큰 섹션은 **명시적 degraded**(heading+예산내 절단 + "[큰 섹션—일부만, 정밀=8d-2b]" 안내 + truncation 메타). "confidently bad" 방지.
- **partial (영속 stack)**: chunk_threads/chunk_messages는 필요(영속+히스토리). 단 핀 분리·frontend 격리로 코어 축소.

### 2. Hidden assumptions
- **accept (중대)**: sec_no는 doc 내 유일 아님(부록/예제/중복). → **섹션 anchor = `(doc_id, heading_chunk_id)`**. sec_no는 표시용. `section_chunks`는 heading **chunk_id**에서 범위 산출. **sec_no 컬럼 불요**(chunk_id로 통일). 8d-1 `selectSection`이 `headingChunkId`를 이벤트에 추가(backward-compat).
- **accept (unnumbered)**: `Appendix A.1`/비번호 heading도 heading_chunk_id로 anchor 가능. 범위 경계: secNo 있으면 depth≤시작, 없으면 **다음 heading(아무거나) 직전까지** fallback.
- **accept (doc/chunk 정합)**: CHECK로 불가 → `POST /v2/threads`에서 chunk.doc_id==doc_id 검증(아니면 422). 테스트.
- **accept (token≠char)**: budget은 **char 기준 coarse guard**(token-정확 아님). 보수적 6000 + history 포함 시 초과 가능 → 정직 기재; token-aware는 후속. 큰 섹션 degraded가 1차 방어.

### 3. Edge cases
- **accept**: 중복 secNo → heading_chunk_id anchor로 해소(UI가 선택 heading의 chunk_id 전송). 테스트.
- **accept**: 챕터급 heading은 doc 끝까지 span → 큰 섹션 degraded(절단+안내+메타). 소/중이 코어.
- **accept (라벨 context)**: chunk type/번역상태 **라벨링**(`[heading]`/`[본문]`/`[수식]`/`[표]`/`[그림캡션]`, translated status='translated'면 번역 else 원문). 혼합 KO/EN/LaTeX 무라벨 방지.
- **accept (트랜잭션)**: LLM-call→DB-write(messages.py 패턴) 유지 → LLM 실패 시 **무행** 보장(테스트). 동시 post stale-history는 1.x 상속 한계로 기재.
- **accept (delete in-flight)**: thread 삭제 중 write → FK 위반 → 클린 에러(orphan 0). 테스트.

### 4. Alternative approaches
- **accept**: 섹션 anchor `(doc_id, heading_chunk_id)`(§2). chunk_threads.anchor = anchor_type + **chunk_id**(둘 다; section=heading chunk). sec_no 컬럼 제거.
- **partial (order_idx API 노출)**: 8d-2a는 server가 DB order_idx로 범위 산출(JS는 응답순서) → **동일 fixture parity 테스트**로 drift 방지. API에 order_idx 노출은 불요(server-side 자체 쿼리).
- **accept (chunk_pins 별도)**: §1.
- **accept (typed context)**: `build_*_context`가 **dataclass**(prompt text + included_chunk_ids + truncated + total) 반환 → 테스트가 "모델이 본 것" assert.

### 5. Missing tests — 전부 accept (추가)
1. `test_create_chunk_thread_rejects_chunk_doc_mismatch` — doc A + chunk B → 422, 무행.
2. `test_section_context_duplicate_secno_uses_selected_heading_chunk` — 중복 28.4, 2번째 heading_chunk_id 선택 → 2번째 범위.
3. `test_section_context_unnumbered_heading_graceful` — Appendix/비번호 heading anchor → 다음-heading fallback 범위.
4. `test_v2_message_llm_failure_writes_no_messages` — LLM raise → user/assistant 무행.
5. `test_v2_delete_thread_during_inflight_no_orphan` — 삭제 후 write → orphan 0 + 결정적 에러.
6. `test_build_section_context_reports_truncation_metadata` — over-budget: heading 포함 + included ids 결정적 + truncated=True.
7. `test_chat_markdown_sanitizes_assistant_html` — `<script>`/onerror 등 DOMPurify 제거(jsdom).

## Plan revisions (after debate)
- R1 **섹션 anchor = heading_chunk_id**(sec_no 컬럼 제거). `section_chunks(doc_id, heading_chunk_id)`. 8d-1 `selectSection`에 `headingChunkId` 이벤트 추가.
- R2 chunk_threads: id/doc_id/anchor_type('chunk'|'section')/chunk_id(FK)/title/created_at. (chunk·section 둘 다 chunk_id; section=heading chunk.)
- R3 **별도 `chunk_pins`** 테이블(id/doc_id/chunk_id/created_at). 핀≠thread.
- R4 `POST /v2/threads`에서 chunk.doc_id==doc_id 검증(422).
- R5 큰 섹션 = 명시적 degraded(heading+절단+안내+truncation 메타). 소/중 코어.
- R6 라벨 context(type/번역상태). translated(status=='translated') else 원문.
- R7 typed context dataclass(text/included_chunk_ids/truncated/total).
- R8 LLM 실패 무행 + delete-in-flight FK 에러(orphan 0).
- R9 char-budget=coarse(token 아님), 보수적 6000, 정직 기재.
- R10 chat.js 별도 모듈, reflow.js는 선택 hook만(최소 변경).
- R11 JS/Python 섹션 parity 테스트 + Codex 7 테스트 전부.

## DoD checklist
| DoD item | Status | Evidence |
| -------- | ------ | -------- |
| 문단 클릭 → 채팅(context 자동) | 계획 | build_chunk_context + API + 사용자 |
| 섹션 선택 → 섹션 베이스 질문(핵심) | 계획 | heading_chunk_id anchor + build_section_context + API |
| 핀 chunk anchor | 계획 | chunk_pins + API/UI |
| 1.x 무손상 | 계획 | 0007 additive(신규 3테이블), 1.x threads/messages 무변경, blocks=49850 |
| figure/neighbor/cross-doc RAG/within-section top-K | 범위 외 | 8d-2b |

## Risk register
| Risk | L | I | Mitigation |
| ---- | - | - | ---------- |
| 중복/비번호 섹션 anchor | 중 | 고 | heading_chunk_id anchor(R1) + 테스트 |
| 큰 섹션 confidently-bad | 중 | 고 | degraded+메타(R5), 소/중 코어 |
| doc/chunk anchor 불일치 | 중 | 중 | POST 검증(R4) |
| LLM 실패/삭제 중 write orphan | 중 | 중 | call→write 순서 + FK(R8) |
| token 초과(char budget) | 중 | 중 | 보수적+degraded(R9); token-aware 후속 |
| reflow.js 비대/회귀 | 중 | 중 | chat.js 격리(R10) |
| 1.x chat 회귀 | 저 | 고 | /v2 신규, 1.x 무변경, 회귀 스위트 |

## Decision
- [x] **PASS → proceed to code** (R1–R11). anchor=heading_chunk_id가 핵심 수정이나 아키텍처(v2 테이블+context 빌더+chat 엔드포인트+패널) 유지 → RE-PLAN 불요.
- [ ] RE-PLAN
