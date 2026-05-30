# Phase 8d-2a — Plan (Chat 코어: 문단Q + 섹션Q + 영속 + UI + 핀)

## Goal
reflow에서 **문단(chunk) 선택 → 질문**과 **섹션(목차) 선택 → 그 섹션 전체를 베이스로 한 질문**(핵심 가치)을 qwen으로 답하고, chunk-anchored 대화/핀을 영속한다. **RAG-free**(cross-doc + within-section top-K는 8d-2b).

## 배경 / 분할 (Planner 확정)
8d = 8d-1(마크다운+섹션트리/선택/점프, 완료 d041d22) / 8d-2(chat). 8d-2 6기능이 커서 재분할: **8d-2a(코어)** = 문단Q+섹션Q+영속+UI+핀, **8d-2b** = figure 채팅+neighbor 재번역+cross-doc RAG.
- cross-doc RAG와 within-section top-K는 **같은 chunk-embedding 검색 머신**(`search_chunks`/`get_or_encode_chunk_vector` 신규 필요) → 둘 다 8d-2b. 따라서 **8d-2a는 embed/RAG 불필요**.
- 결과: 8d-2a 섹션Q context = **작으면 전체(≤~6000자), 크면 heading + 예산내 chunk 절단 + 안내**(결정적). top-K 정제는 8d-2b. (Planner 하이브리드 budget ~6000 확정; top-K는 8d-2b로 이연 — challenge에서 확인.)

## Stage 0 실측 (plan 가정 근거)
- Phase 5 chat: `routers/messages.py`(LLM-call→DB-write 순서, semaphore, `_map_llm_error`) + `api/chat_context.py`(`build_block_context_with_refs`: target + 같은-페이지 ±radius + cross-doc RAG). Thread.block_id=**NOT NULL blocks FK** → chunk anchor 불가 → 신규 v2 테이블.
- 섹션 경계: heading text_level **전부 2(평탄)** → text_level 경계 불가. **dotted secNo 깊이**로(8d-1 `computeSectionChunks` Python 포팅: heading secNo부터 depth≤시작 heading 전까지).
- alembic head 0006 → 신규 **0007**. Chunk: content(heading은 영문 원문+번호)/order_idx/doc_id/type. doc7 chunk_embeddings=0(8d-2a 불요).

## Scope
**In (8d-2a)**
- 영속: 신규 `chunk_threads`/`chunk_messages` (migration **0007**, **additive-only, 1.x 무 ALTER**). anchor = `anchor_type('chunk'|'section')` + nullable `chunk_id`(FK chunks) | `sec_no`(str). 정확히 한 쪽만.
- `section_chunks(doc_id, sec_no)` — secNo-depth 경계(부모=자식 포함). `build_section_context(doc_id, sec_no, budget=6000)` — 전체/heading+절단. `build_chunk_context(chunk_id, radius)` — 같은 doc order_idx ±radius 이웃(reflow 연속, 페이지 횡단 허용). **RAG refs 없음**(8d-2b).
- v2 chat 라우터: `POST /v2/threads`(anchor 생성=핀/대화 시작), `GET /v2/documents/{id}/threads`(목록=핀/대화), `POST /v2/threads/{id}/messages`(context→qwen→영속), `GET /v2/threads/{id}/messages`, `DELETE /v2/threads/{id}`.
- frontend: reflow 통합 채팅 패널(drawer) — 선택 상태(문단 vs 섹션, 8d-1 `sectionselect` 소비 + chunk 클릭), 질문/답(assistant는 vendored marked/DOMPurify), 핀 목록.
- 핀: chunk anchor를 chunk_threads로 영속(핀 = 앵커된 thread; 사이드바 목록 + 클릭 점프/대화).

**Out (→8d-2b / 그 외)**
- figure 채팅, neighbor 재번역(짧은chunk), cross-doc RAG, within-section top-K = **8d-2b**(embed setup 포함).
- 수식밀집 영어 fallback 6곳 = 8e. 볼드 = 8e.

## Approach
### 1) 영속 (0007, additive)
- `chunk_threads`: id, doc_id(FK documents), anchor_type, chunk_id(FK chunks, null), sec_no(str, null), title, created_at. CHECK/검증: anchor_type='chunk'→chunk_id 有/sec_no null; 'section'→sec_no 有/chunk_id null.
- `chunk_messages`: id, thread_id(FK chunk_threads), role, content, model, created_at. (Message 미러.)
- **1.x threads/messages 무변경**(신규 테이블만) — 8a 가드레일. verify에서 additive 스키마-diff 검증.

### 2) 섹션 그룹핑 + context (핵심)
- `parse_section_no(text)` (8d-1 JS 포팅): 선두 점표기.
- `section_chunks(session, doc_id, sec_no)`: heading(content 원문) secNo 일치 → 다음 depth≤시작 heading 전까지 chunk 전부(부모=자식 포함). 없으면 빈.
- `build_section_context(session, doc_id, sec_no, budget)`: 합계≤budget→전체; 초과→heading + 예산내 chunk + "[섹션 길어 일부]" 안내. 번역 우선(없으면 원문). 8d-2b가 top-K로 정제.

### 3) chunk context
- `build_chunk_context(session, chunk_id, radius=2)`: 같은 doc order_idx ±radius(페이지 횡단). target 강조 + 이웃 원문/번역. cross-doc RAG는 8d-2b.

### 4) chat 엔드포인트 (messages.py 패턴 재사용)
- anchor별 context: chunk→build_chunk_context, section→build_section_context. LLM-call→DB-write 순서, semaphore, `_map_llm_error`, history. 신규 v2 schemas.

### 5) frontend 채팅 패널
- reflow.html drawer; 선택 상태(문단=chunk 클릭, 섹션=`sectionselect`); "질문"→thread 생성+message; assistant markdown 렌더(vendored). 핀 버튼+목록. 1.x viewer.html 무손상.

## File-level changes
| Path | Action | Note |
| ---- | ------ | ---- |
| `src/ht_lens/db/migrations/versions/0007_*.py` | 신규 | chunk_threads/chunk_messages (additive, 1.x 무 ALTER) |
| `src/ht_lens/db/models.py` | 수정 | ChunkThread/ChunkMessage 모델(신규 테이블) |
| `src/ht_lens/api/chunk_chat_context.py` | 신규 | section_chunks/build_section_context/build_chunk_context/parse_section_no |
| `src/ht_lens/api/routers/chunk_chat.py` | 신규 | `/v2/threads` 라우터 |
| `src/ht_lens/api/schemas.py` | 수정 | v2 chat 스키마(ChunkThreadCreate/Read, ChunkMessageCreate/Read) |
| `src/ht_lens/api/app.py` | 수정 | chunk_chat 라우터 include |
| `src/ht_lens/api/static/reflow.html` | 수정 | 채팅 패널 컨테이너 |
| `src/ht_lens/api/static/js/chat.js` | 신규 | 선택상태+질문+핀 (sectionselect 소비) |
| `src/ht_lens/api/static/js/reflow.js` | 수정 | chat.js 연동(선택 상태 전달) |
| `src/ht_lens/api/static/css/reflow.css` | 수정 | 채팅 패널 스타일 |
| `tests/integration/test_chunk_chat_*.py` | 신규 | context/api/migration |
| `tests/integration/test_chat_ui_js.py` | 신규 | jsdom 선택상태/렌더 |

## Dependencies (new)
| Package | Why |
| ------- | --- |
| (없음) | qwen(.env TRANSLATE/CHAT_LLM), marked/DOMPurify(vendored). 신규 0. |

## Test strategy
- Python: `section_chunks`(secNo-depth 경계, 부모=자식, 누락 graceful), `build_section_context`(전체≤budget / 초과 절단+안내), `build_chunk_context`(±radius 페이지횡단), v2 chat API(chunk/section anchor 생성, anchor 검증=정확히 한쪽, message=mock LLM로 context 전달+영속, 목록, unknown 404, 1.x threads 무영향), **0007 additive-only 스키마-diff**(1.x 테이블 무 ALTER/DROP — 8a 패턴).
- LLM mock(8b 패턴)로 chat 엔드포인트(실 qwen 없이 결정적).
- jsdom: 채팅 패널 선택 상태(문단 vs 섹션), `sectionselect` 소비, assistant 메시지 렌더.
- 회귀: 692 → 692+신규. ruff/format/mypy clean. 1.x `blocks`=49850 불변.

## DoD mapping (8d-2a = ROADMAP 8d의 chat 코어 + 사용자 섹션Q)
| DoD item | How to satisfy | Evidence plan |
| -------- | -------------- | ------------- |
| chunk(문단) 클릭 → 채팅 (context 자동) | build_chunk_context + /v2/threads(chunk) | test_chunk_chat_api + 사용자 8086 |
| **섹션 선택 → 그 섹션 베이스 질문** (사용자 핵심) | build_section_context(전체/절단) + /v2/threads(section) | test 섹션 context + API + 사용자 |
| 핀 chunk anchor | chunk_threads 영속 + 목록 | test_chunk_chat_api(생성/목록) |
| 1.x 무손상 | 신규 테이블만(0007 additive), 1.x threads/messages 무변경 | additive 스키마-diff + blocks=49850 |
| figure/neighbor/cross-doc RAG/within-section top-K | (범위 외) 8d-2b | plan 명시 |

## 위험 / 완화
- 섹션 경계(secNo-depth) 누락/오판 → 8d-1 검증 로직 포팅 + 단위테스트(부모=자식, 누락 graceful).
- 큰 섹션 context 토큰 초과 → budget 절단+안내(top-K는 8d-2b); budget 보수적 6000.
- 문단/섹션 선택 상태 혼동 → 패널에 상태 명시(문단 vs "28.4.2 선택") + 이벤트 분리(8d-1 sectionselect).
- anchor 무결성(chunk_id XOR sec_no) → 검증 + 테스트.
- 1.x chat 회귀 → 신규 테이블/라우터(/v2), 1.x /threads 무변경; 회귀 스위트.
- qwen 미가용 → `_map_llm_error`(502) + mock 테스트(8b health 패턴).
