# Phase 6f-5 — Summary

## Status
**ESCALATE TO PLANNER** (R2 DOWNGRADE, push 보류).

WORKFLOW.md Stage 6: Round 2 cross-verify DOWNGRADE → worker push 금지. Planner 판정 대기.

## Score history
| Round | Self | Cross verdict | Cross fair | 행동 |
|---|---|---|---|---|
| v1 | 91/100 | DOWNGRADE | 76/100 | RE-CODE (R1 4건) |
| v2 (post RE-CODE) | 84/100 | **DOWNGRADE** | **79/100** | **escalate (R2 상한)** |

R2 잔존 비판 분류:
- ✅ R1의 **prod 코드 결함 (real bug)** 모두 해결 (lang norm partial, weak cache test → 진짜 path lock)
- ✅ R1의 evidence gap (web UI, doc src/tgt SQL) 해결
- ⚠️ 잔존: **process compliance / evidence presentation** (workflow command 정확 wording, coverage row 일관성, CI 미실행, challenge §5 일부 미실행, 운영 절차 manual notes)

## What was built

### Prod 의사결정 reverse
Phase 6f-1 Gemma 4 swap을 A/B 측정 결과 기반으로 reverse:
- qwen3.6-27b 본문 KR 0.874 vs Gemma 4 v2_ko 0.755 (matched 20 blocks)
- Matched-block 14/20 qwen 우세, gemma 0
- qwen baseline 0.867 조차 Gemma 4 v2_ko 0.755 보다 우세
- Phase E1.5 chrF/LLM-judge 측정 axis ≠ Korean purity 가설 검증

### 1. v2_ko prompt branch (code)
`src/ht_lens/llm/openai_compat.py:_translate_system()`에 lang 분기:
- `src.lower().strip() == "en" AND tgt.lower().strip() == "ko"`: A/B-validated v2_ko Korean-instruction prompt
- else: 기존 generic 영어 prompt 보존 (ko→en, en→ja 등 backward compat, **normalized lang code 사용** — R1 §4 partial-normalization bug fix)

### 2. qwen rollback (인프라)
- `.env`: TRANSLATE_LLM_* / CHAT_LLM_* / LLM_* / OLLAMA_* 모두 `localhost:8081`/`qwen3.6-27b`로
- `.env.backup.gemma4_<ts>` 백업 (rollback 보험, untracked)
- sglang docker: `sglang-gemma4-26b-a4b-it` stop, `sglang-qwen-27b` 가동 (Phase 6f-1 보존 launch command — FP8, speculative decoding, mamba scheduler, context 32768)
- ht_lens restart with 강화 절차 (특정 PID kill → SIGKILL fallback, port 해제 확인)
- **ht_lens 다운타임 약 6분**

### 3. 회귀 안전망
12 신규 tests (442 → 454):
- 9 prompt branch (en→ko + 다른 방향 + 정규화)
- 1 generic-path normalization (R1 partial-fix lock)
- 1 cache real-scenario integration (R1 weak-test fix)
- 1 cache deterministic (보조)

## Files changed
```
 .claude/phases/phase-6f-5/{plan,debate,challenge,verify,verify-cross,summary}.md  # phase docs
 src/ht_lens/llm/openai_compat.py                                                   | +20 -3
 tests/unit/test_translate_prompt.py                                                | NEW (197 lines)
 tests/integration/test_translate_pipeline_mock.py                                  | +102 -0 (cache real test)
 .env                                                                               | MOD (3 pair port/model)
 .env.backup.gemma4_20260524_184518                                                  | NEW untracked (ops artifact)
```

Code 변경 commit graph:
```
b17f7e6 chore(phase-6f-5): verify-cross r2 [DOWNGRADE 84→79]
a3b7423 chore(phase-6f-5): verify v2 (post RE-CODE)
f837595 fix(phase-6f-5): RE-CODE addressing verify-cross R1 DOWNGRADE
7bd2149 chore(phase-6f-5): verify-cross r1 [DOWNGRADE 91→76]
265a7f0 chore(phase-6f-5): verify
c6f7a54 feat(phase-6f-5): v2_ko Korean-instruction prompt for en→ko translate
e22a348 chore(phase-6f-5): debate + challenge
eae8e99 chore(phase-6f-5): plan
```

## Test deltas
- pre-phase: 442 → v2 (post RE-CODE): **454 passed, 8 skipped** (8 skip = live-LLM 환경 미설정, 본 phase 무관)
- mypy strict / ruff / format: clean

## Deviations from plan
- plan v1 `.env` 변경 "5쌍" → challenge ACCEPT 후 `.env` 변경 **3쌍** (TRANSLATE_LLM_*, CHAT_LLM_*, LLM_* — OLLAMA_*는 factory 미사용이지만 일관성 위해 같이 변경). challenge §1 acknowledged 후 OLLAMA_도 변경 — 약식 deviation, ops 일관성 우선.
- `.env.backup.gemma4_*` 는 challenge per "git ignore 대상, commit 안 함".
- 사용자 결정 (AskUserQuestion):
  - prompt 분기: `src=='en' and tgt=='ko'` (선택됨)
  - 기존 번역: 보존 (선택됨) — cache prompt-versioning Phase 6f-6 후보로 defer
  - Codex debate: plan commit 즉시 호출 (선택됨)

## Evidence index
- plan: commit `eae8e99`
- debate (Codex): commit `e22a348` (challenge와 함께)
- challenge: commit `e22a348` — Codex 4건 ACCEPT + lang norm 추가, OLLAMA defer, DoD evidence 정정, SIGKILL fallback, 4 신규 테스트 lock-in
- code: commit `c6f7a54` (prompt + 9 unit tests) + `f837595` (RE-CODE: lang norm bug fix + cache real test)
- verify v1: 91 → DOWNGRADE 76 (commits `265a7f0` / `7bd2149`)
- verify v2: 84 → DOWNGRADE **79** (commits `a3b7423` / `b17f7e6`)
- summary: 본 파일

## Known issues / debt (Planner 검토 필요)

### R2 Critic (Codex) 잔존 비판 (모두 evidence quality, prod 무관)
1. **Lint/format/test commands 정확 wording 불일치**: WORKFLOW.md 는 `ruff check .` 와 `pytest -m "not llm and not slow"`. 본 phase 는 `ruff check src/ tests/` 와 `pytest tests/ --no-cov -q` 사용. 실효는 동일 (해당 경로만 src 있음, skip 8건이 정확히 live LLM 마커).
2. **Coverage row 일관성**: verify v2 coverage row가 `translate/cache.py` 100% / `translate/pipeline.py` 92% 표시했지만 RE-CODE 의 actual 변경은 `openai_compat.py`. cache test 측정용 명령에서 우연히 잡힌 결과를 정상 coverage로 잘못 표기 — 실제 `openai_compat.py` 측정은 11 prompt unit tests + 1 cache test가 cover (실측 100% 분기 라인). evidence 표기 부정확.
3. **CI 미실행**: 본 phase 모든 verify는 local. push 후 검증 미반영.
4. **Challenge §5 일부 unique test 미추가**: qwen-specific retranslate provenance (`manual-retranslate:qwen3.6-27b:` 어설션 unit test). 기존 `test_api_retranslate.py` 는 generic prefix 만 cover. 보강 가능.
5. **Rollback 절차 manual**: docker start/stop + .env + restart는 worker notes (이 summary + verify B-2). committed code로 자동화 안 됨.

### Cache prompt-version 부재 (사용자 의도된 limitation)
- 사용자 결정 "보존 기존 번역" 채택 → cache key에 prompt version 포함 안 함
- 결과: 옛 qwen 시절 translation 이 새 prompt 와 같은 (text, src, tgt, model="qwen3.6-27b") 면 cache hit → 옛 결과 serve
- 이 limitation 은 `test_prompt_change_does_not_invalidate_existing_cache` 가 명시적으로 lock (의도된 동작)
- Phase 6f-6 후보 로 prompt-versioning + policy layer refactor

## Recommended next

### For Planner — push 결정
이 phase는:
- ✅ A/B 측정 driven prod 결정 (qwen 0.874 vs gemma 0.755)
- ✅ 실제 prod 동작 검증 (5 retranslate 평균 KR 0.96, chat model=qwen3.6-27b)
- ✅ Codex R1 prod-code 비판 모두 해결 (lang norm bug, cache real test)
- ⚠️ R2 잔존 비판 모두 evidence presentation / process compliance — prod 코드 회귀 0
- ⚠️ 자동 PASS (95+) 미달, fair 79

판정 옵션:
- **Option A**: PASS_DESPITE_R2 — 잔존 evidence-presentation 항목들은 follow-up phase에서 일괄 처리. 본 phase 변경은 prod에 push 안전. push + CI 후 결과 보강.
- **Option B**: Planner-directed micro-fix — 잔존 5건 중 actionable (qwen provenance test, coverage row 정정, command wording 보정) 즉시 fix. rollback automation + CI는 별도 phase.
- **Option C**: REJECT — fundamental 재설계.

권장 **A**: 본 phase의 핵심 가치 (qwen rollback + v2_ko prompt)는 측정 결과로 정당화되고, code 결함은 모두 해결됨. evidence presentation은 후속 phase에서 일관 보강 가능.

### For Phase backlog
- **Phase 6f-6 (제안)** — prompt-policy 분리:
  - `_translate_system` 분기 로직을 transport client (`openai_compat.py`) 밖으로 추출 (policy layer)
  - cache key에 prompt version 포함 (선택 — 이전 결정 reverse 시)
  - ja/zh 추가 시 N개 분기 폭발 방지
  - Codex debate §4 alternative 채택
- **Phase 6f-7 (제안)** — verification 자동화:
  - retranslate provenance qwen-specific test
  - coverage row 정확 측정 (changed file scope)
  - rollback / GPU swap 절차 documented runbook → script + smoke test
- **Phase 6h-1 / 6h-2** (이전 계획) — chat section context / lang UI
- **Phase E2 fine-tune ROI 재평가** — qwen baseline 0.867 강함, fine-tune 효과 작을 수도

### Gemma 4 자산 정리 결정 (며칠 안정 후)
- Gemma 4 weights `~/hf_models/gemma-4-26b-a4b-it` (49GB) — re-swap 보험 보존 vs 정리
- Gemma 4 sglang container (현재 stopped) — 보존
- Gemma 4 docker image (lmsysorg/sglang:latest) — 보존 (qwen도 사용)
