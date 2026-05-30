# Phase 8b — Summary

## Status
**ESCALATE_TO_PLANNER** (cross-verify Round 2 cap, REJECT). push 보류.
8a/6i와 달리 R2가 **실제 결함 1건**을 지적 — score quibble 아님. Planner 결정 필요: micro-fix 지시 vs accept.

## Score
- Self (v2): **91 / 100**
- Codex R1: **DOWNGRADE** (~78) — persistent DB cache 누락, dead cached stat, collision-raw-math, CLI 약함
- Codex R2: **REJECT** (~81) — R1 지적 전부 fix 확인, 단 RE-CODE가 남긴 **CLI 결함** 발견

## R2가 찾은 실제 결함 (Planner 판단의 핵심)
1. **`translate-chunks`가 번역 실패해도 exit 0** — `stats.failed>0`인데 CLI는 `ok ... failed=N` 출력 + exit 0. 1.x `translate`는 실패 시 `Exit(1)`. → 자동화가 실패를 놓침. **실 결함.**
2. **`LLMHealthCheckFailed` except 분기 dead** — `translate_chunks_command`은 1.x와 달리 `health_check()`를 호출 안 함. per-chunk LLM 예외는 failed row로 흡수되어 CLI까지 전파 안 됨 → 그 분기 도달 불가. (`LLMConfigurationError`는 factory에서 raise되어 도달 가능.)
3. **새 CLI 에러 분기가 translate-chunks 테스트로 미잠금** (doc-404만 테스트). `mock_fail` 기반 실패-exit 테스트 없음.
4. **accepted table 테스트 미작성** (challenge §3.4 수용했으나 doc7 table 0개라 후순위; 8e).

## 권장 micro-fix (Planner 지시 시, <30분)
- `translate_chunks_command`: `if stats.failed > 0: raise typer.Exit(code=1)` (1.x translate와 동일 계약).
- dead `LLMHealthCheckFailed` 분기: (a) translate 전 `await llm.health_check()` 호출 추가(1.x 패턴) 또는 (b) 도달 불가 분기 제거. (a) 권장 — fail-fast.
- 테스트: `TRANSLATE_LLM_PROVIDER=mock_fail`로 translate-chunks 실패→exit 1, config 에러→exit 5.
- (table은 8e로 유지.)
이는 **Planner-directed fix** (push 정책: Planner가 직접 검증). R3 cross-verify 금지(cap).

## What was built (전체)
- math_protect (placeholder 보호, byte-identical, missing→failed, collision-nonce)
- chunk_pipeline (7a-2 일반화: in-run dedup + **persistent DB cache** + live cached stat + peak-concurrency + equation passthrough + image/chart/table + retry/cancel/status)
- chunk_embeddings (chunk-parallel ADD, 1.x 무손상; idempotent + model-refresh + cascade)
- migration 0006 (additive), CLI translate-chunks/embed-chunks + extract-mineru CLI 테스트(8a 잔존 closure)

## Evidence
- ruff/format/mypy(79) clean, **653 passed** (619 + 34)
- 실 E2E doc7 103 chunk (Mock): equation byte-identical passthrough, $ 보존, ⟦MATH 잔존 0
- 1.x 무손상 3중 (additive diff + translations intact + block_embeddings intact)
- DoD 3/3 충족 (단 #1 CLI 결함이 "7a-2 적용" 운영 품질에 흠)

## Known issues / debt
위 R2 결함 1~4 + 실 qwen 미실행(8e) + caption DB 캐시 미구현(minor) + chunk 검색 8d.

## Recommended next (Planner)
1. **micro-fix 지시** [권장] — CLI exit-on-failure + health_check + 실패 테스트 (위). R2가 실 결함을 짚었으므로 8a처럼 그냥 PASS보다 fix가 옳음. fix 후 push.
2. accept-as-is — DoD 3/3 + 653 green이나 CLI 결함이 남음 (비권장).
3. RE-PLAN — 불필요.

Push: **HELD**. Planner 지시 대기.
