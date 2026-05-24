# Phase 6f-5 — Challenge

## Debate responses

### 1. Over-engineering (Codex)

> The plan bundles two separate decisions: operational rollback and translation-policy redesign. `ROADMAP.md:320-328` says Phase 6f should reuse Phase 6e infra with "도메인 코드 변경 0".

**PARTIAL ACCEPT — keep bundle with explicit justification.**

근거:
- 사용자 prompt가 명시적으로 두 part 묶음 (Part A 인프라 + Part B 코드). worker가 임의로 split하면 사용자 의도 위배.
- 두 변경은 rollout 관점에서 결합: qwen + 옛 prompt vs qwen + v2_ko prompt 의 A/B 차이는 +0.7% (0.867 → 0.874). qwen rollback 만으로도 사용자 issue B 대부분 해결.
- ROADMAP.md 의 "도메인 코드 변경 0" 원칙은 인프라 phase 일반 가이드 — prompt 한 줄 변경은 인프라 결정 (어떤 모델 prod, 어떤 prompt 사용)의 한 axis로 봐도 무리 없음.
- 단 commit 분리: rollback commit (`.env` + sglang docker) 과 prompt commit (코드 + 테스트) 별도. Stage 4 sub-commit으로 처리.

**summary.md에 명시**: "두 axis 묶음 — Codex가 split 권고했으나 rollout 결합도와 사용자 prompt 명시로 유지. commit은 분리".

> Rewriting `OLLAMA_*` and committing `.env.backup.gemma4_<ts>` is unnecessary blast radius.

**ACCEPT.**
- `OLLAMA_*` 는 factory.py가 안 읽음 — 변경 안 함 (현 .env에 있다면 그대로 유지).
- `.env.backup.gemma4_*` 는 git ignore 대상 (현 `.env.backup.20260523_181759`도 untracked). commit 안 함, ops artifact.
- plan v1 §3 "5개 변수" → **3쌍** (TRANSLATE_LLM_BASE_URL/MODEL, CHAT_LLM_BASE_URL/MODEL, LLM_BASE_URL/MODEL) 으로 정정.

> Hardcoding a Korean-specific policy into `OpenAICompatibleClient._translate_system()` couples provider transport to translation strategy.

**ACCEPT 분석, 본 phase scope-out으로 처리.**
- Codex 정당. transport client에 정책 박는 건 layering bad.
- 본 phase: 1줄 분기 (`if src.lower() == "en" and tgt.lower() == "ko"`)로 최소 침습. prompt를 policy layer로 추출하는 refactor는 별도 phase (6f-6 후보)로 cataloged.
- summary.md에 follow-up phase 명시.

### 2. Hidden assumptions (Codex)

> The branch `if src == "en" and tgt == "ko"` assumes normalized lower-case ISO codes.

**ACCEPT — 정규화 적용.**
- `_translate_system(src, tgt)`에 `src = (src or "").lower().strip()` / `tgt = (tgt or "").lower().strip()` 추가. `"en-US"` → "en-us" → 분기 miss (false negative)는 받아들임 (현 DB 모든 doc src/tgt가 simple "en"/"ko"). plan에 lock test 추가.
- 추가 안전망: lock test 가 "EN"/"En"/"en-US" 도 분기 활성 시키도록 확장하지 않고 의도적으로 strict 매칭 (지금 prod 데이터 100% lowercase).

> The E2E evidence plan is wrong on its face. `src/ht_lens/api/routers/blocks.py:95-99` stores `manual-retranslate:{base_model}:{timestamp}` after `POST /blocks/{id}/retranslate`, not bare `qwen3.6-27b`.

**ACCEPT — DoD evidence 정정.**
- plan v1 DoD: "DB `translations.model` 컬럼이 `qwen3.6-27b`로 갱신"
- v2: "`translations.model` 이 `manual-retranslate:qwen3.6-27b:<unix_ts>` 패턴으로 갱신" — 즉 `model LIKE 'manual-retranslate:qwen3.6-27b:%'` 검증.
- summary.md / verify.md 에 정정된 evidence 사용.

> The cache assumption is the biggest unstated bet. ... old qwen outputs and new v2_ko outputs are indistinguishable.

**PARTIAL ACCEPT — known limitation으로 명시.**
- Cache 분석 상세 (코드 grep):
  - `translate_document()` (pipeline.py:156-160)는 `status=="translated"` 인 row를 LLM 호출 전에 skip. 옛 qwen 번역은 다시 LLM 안 보냄 → "stale cache가 새 prompt 통해 serve" 시나리오 발생 안 함 (DB row 그대로 보존, prompt와 무관).
  - 새 block (status=ingested) 만 `_call_translate` → cache lookup → 새 row INSERT.
  - 그 새 block 의 cache lookup: `make_cache_key(text, src, tgt, model_name="qwen3.6-27b")` — 옛 qwen 번역이 동일 (text, src, tgt) 라면 hit. 이 경우 옛 (non-v2_ko prompt) 결과 재사용. → **true cache stale**.
  - 단 doc 내 같은 text가 다른 doc에도 있는 비율 (이전 진단의 cache_hit ratio): doc 4 38건 (8%), doc 5 61건 (16%) — 적지 않음.
- 사용자 결정 ("기존 번역 보존 권장") 채택 → 자동 invalidate 안 함. 새 PDF/block의 cache hit (옛 qwen 결과 재사용) 가능성 명시. 사용자가 retranslate 트리거하면 cache 갱신.
- 본 phase 에서는 cache key에 prompt version 추가하지 **않음** (scope creep 위험). 별도 phase (6f-6 후보) 에서 prompt-policy refactor와 함께 처리 가능.
- summary.md "Known issues / debt" 에 명시.

### 3. Edge cases (Codex)

> Previously translated qwen documents are not a corner case; they are the default rollback case.

**ACCEPT — Risk register에 등재.**
- 사용자 결정 ("보존") → 기존 번역 그대로. 새 prompt 효과는 새 번역에만 적용.
- 이 phase 검증의 E2E sample은 의도적으로 **새 retranslate** (cache miss 보장) — 옛 qwen 번역 강제 재호출이 아닌, 신규 prompt 효과 확인.

> The manual smoke test can fail for irrelevant reasons. `POST /blocks/{id}/retranslate` only accepts `text` and `header` blocks.

**ACCEPT — sample 선택 기준 명시.**
- E2E SQL: `WHERE b.type IN ('text', 'header') AND LENGTH(b.original_text) BETWEEN 100 AND 500` 로 fix.
- 5개 block 선택 시 type 보장.

> The restart procedure ignores a roadmap-known defect. `ROADMAP.md:344-345` already records that `ht_lens` ignores SIGTERM and may need SIGKILL.

**ACCEPT — restart에 SIGKILL fallback.**
- Phase 6f-1 swap 시도에서 이미 SIGTERM 무시 사례 발생, pkill -9로 해결한 경험 있음 (그러나 `pkill -9 -f` 패턴이 다른 background bash 명령 매칭 사고도 발생).
- 본 phase restart: `pgrep -af "ht-lens serve"` 정확 PID 수집 → `kill PID` → 5s 대기 → 여전히 살아있으면 `kill -9 PID` (특정 PID, `-f` 패턴 안 씀).
- 검증 명령: `! ss -tlnp | grep :8080` 로 listen 해제 확인 후 새 start.

> Readiness is hand-waved. ... If `.env` flips to `localhost:8081` before the container is actually ready, the rollback will fail at startup.

**ACCEPT — readiness 강화.**
- Stage 순서: qwen sglang 가동 → **`curl /v1/models | grep qwen` 성공 + 1 smoke call non-empty 검증** → ht_lens .env 변경 → ht_lens restart.
- ht_lens 시작 시 health_check이 8081 호출. 실패 시 startup 거부 → log에서 명확.

### 4. Alternative approaches (Codex)

> Honor Phase 6f boundary: pure config rollback first. Match `ROADMAP.md:320-328`.

**REJECT — 사용자 명시 bundle.**
- 위 §1 답변 참조. 사용자가 둘 묶음 prompt 작성, 본 worker가 split 권한 없음.
- summary.md 에서 Codex 권장과 일관성 있게 follow-up phase 후보 정리.

> If prompt tuning must ship, do not bury it in `OpenAICompatibleClient`. Put prompt selection behind a translate-policy setting or wrapper.

**ACCEPT (defer).**
- 본 phase: 1줄 분기로 침습 최소. policy layer refactor는 별도 phase로.

> If the team insists on same-model rollback plus prompt change, version the prompt in cache identity.

**PARTIAL — 본 phase는 hold, 별도 phase 후보.**
- 이유: cache key 변경은 (1) `make_cache_key` 시그니처 변경, (2) 모든 호출 사이트 (`translate_document`, `_call_translate`, manual retranslate route, dry-run estimator) 일관 갱신, (3) DB의 옛 cache_key 처리 정책 결정 필요 — 본 phase 규모 초과.
- summary.md "Recommended next" 에 Phase 6f-6 후보로 등재.

### 5. Missing tests (Codex)

**모두 ACCEPT.**

1. **Retranslate provenance prefix**: `tests/integration/test_api_retranslate.py` 신규 또는 기존 보강 — `model LIKE 'manual-retranslate:qwen3.6-27b:%'` 어설션.
2. **Cache behavior**: `tests/integration/test_translate_pipeline_mock.py` 또는 신규 — 옛 qwen cache 가 새 prompt 호출에서 hit 되는지 (= 의도된 behavior). mock 환경에서 cache_key 동등성 검증.
3. **End-to-end scoped config**: `tests/integration/test_translate_cli.py` 신규 — subprocess가 fake `.env` (qwen3.6-27b @ unreachable port)을 로드 → health_check 실패로 exit 4 → 즉 .env가 LLM 구성에 도달 검증 (현 6e-2 R2 fix와 유사 패턴).
4. **Language code normalization**: `tests/unit/test_translate_prompt.py` 신규 — `_translate_system("EN", "KO")` 또는 `("en ", " ko")` 케이스가 정규화로 v2_ko 분기 hit 검증. 단 `"en-US"` 같은 IETF tag는 의도적으로 false (현 prod 데이터 모두 simple 코드, 향후 확장 시 별도 처리).

## Plan revisions (after debate)

### Revised file changes
| Path | Action | Note |
| ---- | ------ | ---- |
| `src/ht_lens/llm/openai_compat.py` | MODIFY | `_translate_system()`: lang code lower/strip 정규화 + `if src == "en" and tgt == "ko"` 분기 + v2_ko prompt. else 절은 기존 generic 보존. |
| `.env` | MODIFY | **3쌍** (TRANSLATE_LLM_BASE_URL/MODEL, CHAT_LLM_BASE_URL/MODEL, LLM_BASE_URL/MODEL) 만 변경. **OLLAMA_* 손대지 않음** (factory 미사용). |
| `.env.backup.gemma4_<ts>` | NEW (untracked ops artifact) | git에 commit 안 함. |
| `tests/unit/test_translate_prompt.py` | NEW | en→ko 분기 v2_ko 한국어 instruction 검증 + 다른 방향 generic 보존 + lang code 정규화 lock. |
| `tests/integration/test_api_retranslate.py` 또는 신규 | EXTEND/NEW | 옛 qwen `LIKE 'manual-retranslate:qwen3.6-27b:%'` provenance 검증. |
| `tests/integration/test_translate_pipeline_mock.py` 또는 신규 | EXTEND/NEW | 옛 qwen cache hit이 새 prompt 호출에서도 발생하는지 (현 의도된 동작) 검증. |
| `tests/integration/test_translate_cli.py` | EXTEND | subprocess로 qwen URL이 fake .env 통해 factory에 도달 검증. |

### Restart 절차 (강화)
```bash
# 정확 PID 수집
PIDS=$(pgrep -af "ht-lens serve" | awk '$2 !~ /bash|grep/ {print $1}')
[ -n "$PIDS" ] && kill $PIDS && sleep 5
# 잔존 시 SIGKILL (특정 PID만)
for pid in $PIDS; do
    [ -d /proc/$pid ] && kill -9 $pid
done
# Port 해제 확인
until ! ss -tlnp 2>&1 | grep -q ":8080.*LISTEN"; do sleep 1; done
```

### Stage 순서 변경 (debate §3 readiness 반영)
1. qwen sglang docker run
2. qwen ready 검증 (`/v1/models` + 1 smoke call non-empty)
3. **그 후** ht_lens `.env` 변경
4. ht_lens restart (위 강화 절차)

## DoD checklist (revised)
| DoD item | Status | Evidence |
| -------- | ------ | -------- |
| qwen prod 복귀 | planned | `docker ps` + `curl /v1/models` smoke pass |
| v2_ko prompt 적용 (en→ko) | planned | unit test + retranslate 응답 KR > 0.8 |
| 기존 generic prompt 보존 (다른 방향) | planned | unit test |
| Lang code 정규화 동작 | planned | unit test (`"EN"`, `" ko"` 케이스) |
| Retranslate provenance | planned | integration test `LIKE 'manual-retranslate:qwen3.6-27b:%'` |
| Cache behavior 명문화 | planned | integration test (현 동작 = 옛 cache hit, lock-in) |
| Scoped config end-to-end | planned | integration test (fake .env subprocess) |
| chat 영향 없음 | planned | 회귀 + chat E2E |
| Restart SIGKILL fallback | planned | restart 절차 (위) |
| 회귀 0 | planned | mypy / ruff / pytest |
| Rollback 자산 | planned | grep + `du -sh` |

## Risk register
| Risk | Likelihood | Impact | Mitigation |
| ---- | ---------- | ------ | ---------- |
| 옛 qwen cache가 새 PDF에서 hit되어 stale prompt 결과 serve | High | Mid | 사용자 결정 "보존" + 운영 매뉴얼에 retranslate 권장 명시. Phase 6f-6에서 prompt-versioned cache 도입 검토 |
| Lang code "en-US" 등 IETF tag 시 분기 miss | Low | Low | 현 prod 모든 doc simple "en"/"ko" — false negative 자동. 향후 확장 시 별도 분기 |
| `OpenAICompatibleClient`에 정책 박혀 layering bad | Mid | Low | 본 phase 1줄 침습으로 최소화. policy layer refactor Phase 6f-6 후보 |
| ht_lens SIGTERM 무시로 재시작 실패 | Low (해결) | Mid | 강화된 restart 절차 (특정 PID SIGKILL) |
| qwen sglang 시작 실패 | Low | Mid | rollback: Gemma 4 docker start (image 보존) + .env restore |
| chat path 회귀 | Low | Mid | translate prompt만 변경, chat 코드 경로 무변경. E2E /explain 검증 |

## Decision
- [x] PASS → proceed to code
- [ ] RE-PLAN

근거: Codex critique 모두 ACCEPT 또는 명시적 defer (cache key versioning은 별도 phase). plan v1 비해 lang 정규화, OLLAMA_ 미변경, DoD evidence 정정, SIGKILL fallback, 4 신규 테스트 추가. 사용자가 명시한 bundle 유지 + 사용자 결정 (보존, en→ko 분기) 반영. 코딩 진행.
