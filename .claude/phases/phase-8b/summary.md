# Phase 8b — Summary

## Status
**PASS (Planner-directed)** — R2 REJECT의 실 결함을 Planner 지시로 micro-fix 완료. push 진행.

## Score
- Self v3: **92 / 100**
- Codex R1: DOWNGRADE (~78) → RE-CODE (persistent DB cache, live cached stat, collision-nonce, CLI errors)
- Codex R2: REJECT (~81) → **실 결함**(translate-chunks exit-0-on-failure, dead health_check) → Planner-directed micro-fix
- R3 cross-verify 미호출 (CLAUDE.md cap). Planner 직접 검증 경로.

## 결함 → fix (R2 핵심)
1. translate-chunks 실패해도 exit 0 → **`if stats.failed>0: Exit(1)`** (8e batch가 실패 감지). 1.x translate 일관.
2. LLMHealthCheckFailed dead → **translate 전 `await llm.health_check()`** (fail-fast → exit 4 도달 가능).
3. 테스트: mock_fail→exit 1, health fail→exit 4 (+ 기존 doc-404→exit 2).
4. accepted table 테스트 → 8e 연기 (Planner 지시, doc7 챕터 table 0개).

## What was built
- **math_protect**: $..$/$$..$$ → ⟦MATHi⟧ → byte-identical 복원, missing→failed, collision-nonce sentinel.
- **chunk_pipeline**: 7a-2 완전 일반화 — in-run dedup + persistent DB cache(cross-doc, ix_chunk_tr_cache) + live cached stat + peak-concurrency(Semaphore) + equation passthrough + image/chart/table + retry/cancel/status + **CLI fail-fast/exit-1**.
- **chunk_embeddings**: chunk-parallel ADD (block 모듈 무수정, 1.x RAG 무손상) — idempotent + model-refresh + FK cascade.
- migration 0006 (additive), CLI translate-chunks/embed-chunks + extract-mineru CLI(8a 잔존 closure).

## Evidence
- ruff/format/mypy(79) clean, **655 passed** (619 + 36)
- 실 E2E doc7 103 chunk (Mock): equation byte-identical passthrough, $ 보존, ⟦MATH 잔존 0
- 1.x 무손상 3중 (0006 additive diff + translations intact + block_embeddings intact)
- DoD 3/3 + R1/R2 모든 concrete 지적 해소

## Deviations from plan
- cache_key: plan 약식 "hash(content)" → 실제 `cache_key(content,src,tgt,model)` 4-튜플(debate §2).
- missing placeholder: append-comment(plan) → status='failed'(debate §1, byte-identical 진정성).
- chart content: caption만(plan) → content도 번역(debate §3).
- persistent DB cache / live cached stat / collision-nonce / CLI exit-1+health_check: cross-verify R1/R2 대응 추가(plan 외).
- table 실검증: 8e 연기.

## Known issues / debt
실 qwen 미실행(8e) · table 실검증(8e) · caption DB 캐시 미구현(minor) · chunk 검색(8d).

## Recommended next
- Phase 8c (reflow viewer): chunk → reading view. result_v2.html prototype seed + chunk schema(content/type/text_level/img_path/caption) + 8b 번역(translated_text/caption_translated) 사용.
- 8e에서 실 qwen 번역 + table doc 실검증 + extract-mineru 실 추출.

Push: prototype-reflow (main 아님, cutover 8e). GitHub CI는 8e 머지 시.
