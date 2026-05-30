# Phase 8d-2a — Summary (Chat 코어: 문단Q + 섹션Q + 영속 + UI + 핀)

## Status
**PASS_CANDIDATE** — cross-verify R2 DOWNGRADE(~83) → **Planner-directed micro-fix 완료** → push (R3 cross-verify 없음). cross-verify는 2-round cap 정지. R2의 evidence gap 2건(CHECK 미테스트·TOC 콜백 미잠금)을 **test-only**로 폐쇄(verify v3). R2는 새 functional 결함 0(Codex "not a reject-level phase"). 처리 내역은 "R2 micro-fix resolution" 절.

## Score
- Self (verify v2 → **v3**): **87 / 100** (R2 gap 2건 폐쇄 후)
- Cross R1 (`ae2ae46`): **DOWNGRADE ~79** (실 결함 2: 중복섹션 frontend, stale transcript) → RE-CODE
- Cross R2 (`a8bf4bd`, 최종/cap): **DOWNGRADE ~83** (새 functional 결함 없음, evidence gap) → Planner micro-fix → verify v3 (R3 없음)

## What was built (8d = 8d-1[완료] / 8d-2 → 8d-2a[본 phase] + 8d-2b)
- **영속**: 신규 `chunk_threads`/`chunk_messages`/`chunk_pins` (migration 0007, additive, 1.x threads/messages 무손상). 섹션 anchor = **heading chunk_id**(challenge R1, 중복/비번호 robust). 핀 = 별도 테이블(R3).
- **섹션Q (핵심)**: `build_section_context`(heading 앵커, secNo-depth 범위, 라벨 context, typed `ChatContext`, 큰 섹션 degraded). **라이브 qwen E2E 확인**(섹션 28.3.5 정확 요약).
- **문단Q**: `build_chunk_context`(±radius, 페이지 횡단).
- **chat API**: `/v2/threads`(anchor/doc 검증, LLM-call→DB-write 무행 보장 + FK/rollback orphan guard), `/v2/pins`.
- **frontend**: reflow 통합 chat 패널(문단 vs 섹션 선택, `sectionselect`→heading 앵커, ask/pin, assistant marked+DOMPurify sanitize). chat.js 격리(R10).
- RAG(cross-doc + within-section top-K)·figure 채팅·neighbor 재번역 = **8d-2b**.

## Files changed (8d-1 tip d041d22 → HEAD, src+tests; 1783 +/-)
```
 src/.../api/chunk_chat_context.py     206 ++  (신규: section/chunk context, secNo-depth)
 src/.../api/routers/chunk_chat.py     281 ++  (신규: /v2/threads + /v2/pins)
 src/.../api/schemas.py                 80 ++  (v2 chat 스키마)
 src/.../api/static/js/chat.js          183 ++  (신규: 패널, 선택, ask/pin, sanitize)
 src/.../api/static/js/sections.js       77 +/- (selectSectionByHeading + headingChunkId)
 src/.../api/static/js/reflow.js          7 +/- (initChat + selectSectionByHeading hook)
 src/.../db/migrations/.../0007_*.py    104 ++  (additive 3테이블 + anchor CHECK)
 src/.../db/models.py                    58 ++  (ChunkThread/Message/Pin + CHECK)
 + reflow.html/css, app.py, session.py(head 0007)
 tests: test_chunk_chat_{context,api,schema}.py + test_chat_ui_js.py + test_reflow_sections_js.py
        (+ test_chunk_schema.py: stale head 제거)
```
테스트: 692 → **718** (+26 신규 −1 stale): backend 20 + frontend 6.

## 양측 의견 (escalate 핵심)
### Worker (self) — 87
핵심 섹션Q 라이브 E2E + 문단Q + 핀 + 26 테스트(challenge R1–R11 + verify-cross R1 fix). 1.x additive 무손상. 718 green.

### Critic (Codex R2) — DOWNGRADE ~83
> "The important Round 1 functional defects appear fixed, and this is no longer a reject-level phase. … send it to the human Planner with a focused note, not another broad RE-CODE."

R2 잔여 (**evidence gap, functional 결함 아님**):
1. **DB CHECK 미테스트**: `ck_chunk_threads_anchor_type` 추가했으나 invalid anchor_type 직접 insert 거부 테스트 없음 → verify 회귀-증거 과장.
2. **TOC 버튼 콜백 미잠금**: `.toc-select`→`onSelect(node.chunkId)` 경로(R1 핵심)를 end-to-end 안 잠금(dup 테스트는 `selectSectionByHeading` 직접 호출). `test_render_toc_nested`는 버튼 수만 셈.
3. `computeSectionByHeading` grep 과장(직접 아닌 `selectSectionByHeading` 경유 간접 테스트).
4. `pinCurrent`가 `loadPins` await 안 함(minor; 테스트는 polling).

### Worker 평가 (R2 응답)
4건 모두 **사실**. 1·2는 concrete evidence gap(테스트로 cheap 폐쇄 가능), 3은 정직성 nit, 4는 minor async. **새 functional 결함·R1 회귀 0**(Codex 명시). 8b(R2 실 결함)와 다르고, 8c(R2 concrete-cheap gap)·8a/8d-1(R2 process)과 동형.

## R2 micro-fix resolution (Planner-directed, test-only → verify v3 `6fa2441`)
Codex R2: "important R1 defects fixed, not a reject-level phase, send to Planner not RE-CODE." Planner → micro-fix(8c 선례, test-only → R3 없음). R2 4건 처리:
| R2 항목 | 처리 | Evidence |
| --- | --- | --- |
| #1 DB CHECK 미테스트 | invalid anchor_type 직접 insert → IntegrityError | test_anchor_type_check_rejects_invalid |
| #2 TOC 콜백 미잠금(핵심 product path) | `.toc-select` 클릭 → onSelect(node.chunkId) | test_toc_select_button_passes_heading_chunk_id |
| #3 computeSectionByHeading grep 과장 | verify v3에서 "간접 테스트(selectSectionByHeading 경유)"로 정정 | verify v3 §5-C |
| #4 pinCurrent await 안 함 | minor; eventual render 테스트 + 한계 기재 | verify v3 §5-E |
- production 변경 0(test-only +2) → R3 cross-verify 없음. 718→**720** green. ruff/mypy clean.

## Deviations from plan
- 8d-2 재분할(8d-2a 코어 / 8d-2b RAG·figure·neighbor) — Planner 확정.
- 섹션 anchor sec_no→**heading_chunk_id** (challenge R1, 중복/비번호 robust).
- 큰 섹션 top-K → 8d-2b(8d-2a는 budget 절단 degraded).
- dev DB는 0007 적용 후 CHECK 추가됨 → dev DB엔 CHECK 없음(API enforce; 재생성 시 반영).

## Evidence index
- plan `96675f8` / debate `4c56320`(Codex) / challenge `ff1cf0f`(PASS R1–R11)
- backend feat `5717faa` + test `5223f17` / frontend `eefd060` / stale-fix `e5154ed`
- verify v1 `3df6e09`(87) → cross R1 `ae2ae46`(79) → **RE-CODE `87fde93`** → verify v2 `5502c79`(87) → **cross R2 `a8bf4bd`(83, cap)**
- 실측: ruff/format/mypy(82) clean, **718 passed**, jsdom 31, 1.x blocks=49850 불변(prod 0004), 0007 additive, 라이브 qwen 섹션Q E2E.

## Known issues / debt
1. DB CHECK invalid-insert 테스트 부재 (R2) — micro-fix 후보.
2. TOC `.toc-select` 버튼 클릭→콜백 end-to-end 미잠금 (R2) — micro-fix 후보.
3. RAG/figure/neighbor/within-section top-K = 8d-2b.
4. 동시 post stale-history(1.x 상속), router 53% 라인(TestClient), jsdom CI provisioning(8e 전), 볼드/영어 fallback(8e).
5. dev DB CHECK 미반영(API enforce). secNo-first helper 일부 잔존(jump/ref용).

## Recommended next
- **8d-2a 완료** (R2 micro-fix 반영, push). 후속:
- **8d-2b**: figure 텍스트 채팅 + neighbor 재번역(짧은 chunk) + cross-doc RAG + within-section top-K(chunk 검색 머신 `search_chunks`/`get_or_encode_chunk_vector` 신규). dev DB chunk_embeddings embed setup 필요.
- **8e**: 7-doc 마이그레이션 + 실 볼드(재추출) + jsdom CI provisioning + cutover. dev DB CHECK 반영(재생성).

## Push 정책
**Push 진행** — R2 DOWNGRADE escalate → Planner micro-fix 지시 → 처리 완료(test-only +2 → production 무변경 → R3 cross-verify 없음, CLAUDE.md cap 준수). verify v3 self 87, **720 green**. branch prototype-reflow(main은 8e cutover까지 1.x).
