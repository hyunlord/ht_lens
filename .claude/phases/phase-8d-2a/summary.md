# Phase 8d-2a — Summary (Chat 코어: 문단Q + 섹션Q + 영속 + UI + 핀)

## Status
**ESCALATE_TO_PLANNER** — cross-verify Round 2 = DOWNGRADE(~83), 2-round cap 도달. CLAUDE.md "Round 2 이후엔 호출하지 마라. summary.md에 양측 의견 명시하고 Planner에게 escalate" 적용. **Push 보류.** (R2: R1 실 결함 fix 확인, 새 functional 결함 없음 — Codex 자체가 "send to Planner, not RE-CODE" 권고.)

## Score
- Self (verify v2): **87 / 100**
- Cross R1 (`ae2ae46`): **DOWNGRADE ~79** (실 결함 2: 중복섹션 frontend, stale transcript) → RE-CODE
- Cross R2 (`a8bf4bd`, 최종/cap): **DOWNGRADE ~83** (새 functional 결함 없음, evidence gap)

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

## Recommended next (Planner 결정)
- **Worker 권고: micro-fix** (8c 선례 — concrete-cheap gap, **test-only → production 무변경 → R3 불필요**, verify v3 → push). 묶음(~20분):
  - (a) test: invalid `anchor_type` 직접 insert → IntegrityError (CHECK 잠금, R2 #1).
  - (b) jsdom: `renderToc` 렌더 후 `.toc-select` 클릭 → onSelect가 `node.chunkId` 수신 (R1 product path end-to-end, R2 #2).
  - (c) verify 문구 정정(computeSectionByHeading 간접 테스트 명시, R2 #3).
- **대안: PASS** (8a/8d-1 선례 — 새 functional 결함 0; Codex "not a reject"). 단 evidence gap 2건이 기록에 남음.
- **RE-CODE(broad)/RE-PLAN: 불필요** (Codex 명시).

## Push 정책
**보류** — R2 DOWNGRADE, Planner escalate(CLAUDE.md Stage 6). Planner 결정(PASS / micro-fix) 후 진행.
