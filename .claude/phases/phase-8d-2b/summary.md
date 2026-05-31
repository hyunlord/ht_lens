# Phase 8d-2b — Summary (chunk RAG 머신 + within-section top-K + cross-doc RAG + figure 채팅)

## Status
**PASS_CANDIDATE** — cross-verify R2 DOWNGRADE(~86) → **Planner-directed micro-fix 완료** → push (R3 없음). R1 REJECT 실 결함 2개 fix(R2 확인) + R2 follow-up gap 4개(budget continue·figure/section cross-doc·cross-lingual) 폐쇄(verify v3, 736 green). Codex R2 "not fundamentally broken, not another broad RE-CODE". 처리: "R2 micro-fix resolution" 절.

## Score
- Self (verify v2): **88 / 100**
- Cross R1 (`bcca2ed`): **REJECT ~76** (실 결함: section-chat embedding 실패 500, top-K budget 무시) → RE-CODE
- Cross R2 (`b752d7f`, 최종/cap): **DOWNGRADE ~86** (새 functional 결함 없음, follow-up gap)

## What was built (범위 축소: RAG 축; neighbor 재번역+resize → 8d-2c)
- **chunk RAG 머신**(Phase 7a block 일반화): `load_all_chunks`, `chunk_search`(search_chunks/ChunkSearchHit, min_chars=20, graceful empty/dim/zero), `get_or_encode_chunk_vector`/`encode_query`.
- **within-section top-K**: `build_section_context_topk`(별도 fn, budget cap, 빈 hit→8d-2a 절단 fallback).
- **cross-doc RAG**: `build_cross_doc_chunk_refs` + `RelatedChunkRef` → **API 응답 refs**. best-effort(실패 skip), no-write 보장. dev=doc7만→empty(8e live).
- **figure 채팅**: `build_figure_context`(caption+이웃=query, 빈 content 아님), image-anchor 분기(anchor_type 불변), UI "그림" 라벨.
- migration 0건(0007 재사용). 1.x block RAG/chat 무변경.

## Files changed (challenge b7d1003 → HEAD; +1100)
```
 embedding/chunk_search.py        122 ++ (신규)
 embedding/store.py                28 ++ (load_all_chunks)
 embedding/lookup.py               37 ++ (get_or_encode_chunk_vector + encode_query)
 api/chunk_chat_context.py        193 ++ (figure/topk/cross-doc refs + RelatedChunkRef)
 api/routers/chunk_chat.py         90 ++ (embedding dep, figure/topk/cross-doc, R5 no-write)
 api/schemas.py / static/js/chat.js (ChunkRelatedRef / figure 라벨)
 tests: test_chunk_search(신규) + test_chunk_chat_{context,api} + test_chat_ui_js (14 신규)
```
테스트: 720 → **733** fast (+1 @llm cross-lingual deselected).

## 양측 의견 (escalate 핵심)
### Worker (self) — 88
RAG 머신 + figure(builder+API) + cross-doc(응답 refs) + within-section top-K(positive+budget) + 14 테스트. R1 실 결함 2개 fix+lock. 733 green, 1.x 무손상.

### Critic (Codex R2) — DOWNGRADE ~86
> "The R1 blockers were fixed and the v2 self-assessment is substantially more credible … I would not recommend another broad RE-CODE at the two-round cap; these are concrete follow-up tests/design locks, not evidence that the phase is fundamentally broken."

R2 잔여 (**follow-up gap, functional 결함 아님**):
1. budget-cap edge: `build_section_context_topk`가 top hit이 budget 초과 시 즉시 break(이후 작은 hit 미포함) → heading-only. `continue` 패킹 vs break(관련성 우선) 선택 미테스트.
2. figure cross-doc `_cross_doc_refs`(image anchor) end-to-end 미테스트(embedding+2-doc 없음).
3. section cross-doc 계약(heading 벡터) 미테스트.
4. cross-lingual은 @llm(fast gate 제외) — 설계상.

### Worker 평가
4건 모두 사실, 전부 **cheap test/1-line lock**. R1 실 결함(section 500, budget 무시)은 fix+테스트 확인(R2 인정). 8b(R2 실 결함)와 다르고, 8c/8d-2a(R2 concrete-cheap gap → micro-fix)·8d-1(R2 process → PASS)과 동형.

## Deviations from plan
- 범위 축소(challenge R1, Planner): neighbor 재번역 + resize → 8d-2c.
- 섹션 anchor cross-doc = heading 벡터, within-section top-K = question 벡터(검증 분리; verify §5-F 명시).
- cross-doc live = 8e(dev doc7만; 2-doc 단위 + @llm cross-lingual 검증).

## Evidence index
- plan `d4dd1a6` / debate `111d192`(Codex) / challenge `b7d1003`(PASS R1–R10, 범위축소)
- feat `2f3011a` + test `72a015a` / **RE-CODE** fix `3aba497` + test `4e5171a`
- verify v1 `85c99de`(88) → cross R1 `bcca2ed`(76 REJECT) → RE-CODE → verify v2 `dbd7281`(88) → **cross R2 `b752d7f`(86, cap)**
- 실측: ruff/format/mypy(83) clean, **733 passed**(+@llm 1), 1.x 0004/blocks=49850 불변, 0007 migration 무변경.

## Known issues / debt
1. budget-cap break-vs-continue edge (R2 #1) — micro-fix 후보(1-line + test).
2. figure/section cross-doc end-to-end 테스트 (R2 #2/#3) — micro-fix 후보.
3. cross-lingual @llm(fast 제외), router 라인 coverage TestClient, get_or_encode source_hash-only(mixed-model 후속), brute-force(≤50K).
4. neighbor 재번역 + resize = 8d-2c. cross-doc live = 8e. 볼드/영어fallback = 8e.

## R2 micro-fix resolution (Planner-directed, verify v3 `394e369`)
| R2 항목 | 처리 | Evidence |
| --- | --- | --- |
| #1 budget-cap break→heading-only | `break`→`continue`(큰 hit skip, 작은 관련 hit pack — 큰 섹션 답 품질) | test_within_section_topk_packs_smaller_hit_when_top_oversized |
| #2 figure cross-doc 미테스트 | image anchor + 2-doc + embedding → related_chunks | test_figure_cross_doc_refs_end_to_end |
| #3 section cross-doc 계약 | section anchor + 2-doc → 다른 doc ref(heading 벡터) | test_section_cross_doc_refs_use_heading_vector |
| #4 cross-lingual @llm | 설계상(fast 제외); 기재 | (불변) |
- (a)는 1-line production 로직 개선 + 2 cross-doc 테스트. 733→**736** green. R3 cross-verify 없음(Planner, Codex broad RE-CODE 불요).

## Recommended next
- **8d-2b 완료**(R2 micro-fix 반영, push). 8d 시리즈 잔여: **8d-2c**(neighbor 재번역 --short-only + 사이드탭 resize).
- **8e**: 7-doc 마이그레이션 + 실 볼드(재추출) + cross-doc RAG live + jsdom CI provisioning + cutover.

## Push 정책
**Push 진행** — R2 DOWNGRADE escalate → Planner micro-fix 지시 → 처리 완료(R1 실 결함 fix + R2 gap 폐쇄, R3 없음, cap 준수). verify v3 self 88, **736 green**, 1.x 무손상.
