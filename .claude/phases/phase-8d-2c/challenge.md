# Phase 8d-2c — Challenge

Codex가 실 correctness 버그(cache poisoning) + self-defeating 설계(text-only 이웃) + CLI 경로 오류를 잡음. 전부 accept. scope(neighbor+resize)는 Planner가 8d-2c로 명시 분리한 8d 잔여 → 유지하되 하드닝 + `--chunk-id` 안전 경로 추가. PASS w/ revisions.

## Debate responses
### 1. Over-engineering
- **partial**: auto-selector는 8e 7-doc 위해 필요(Planner scope). 단 Codex 안전 경로 채택 → `--chunk-id`(명시 chunk 재번역) **추가**. auto(`--short-only`)는 보수적 `<25`+regex 제외로 유지. heuristic은 dry-run으로 선확인.
- **accept(분리)**: 번역 mutation vs resize UI는 독립 → 테스트 파일 분리(test_short_retranslate / test_resize_js), verify에서 별도 검증.

### 2. Hidden assumptions
- **accept (CRITICAL, cache poisoning)**: content-only `cache_key`에 context-specific 번역 저장 시 미래 동일 content가 오재사용. → 재번역은 **cache 우회(fresh LLM)** + 결과 row **`cache_key=NULL`** 저장(content-only 캐시 비오염). 테스트.
- **accept (CLI 경로)**: 실제는 `src/ht_lens/cli.py:372` translate-chunks. plan의 `translate/cli.py`는 오류 → **cli.py** 타깃, `--short-only/--max-chars/--dry-run/--chunk-id`.
- **accept (LLM 출력)**: "neighbors+target 번역 후 추출" 폐기 → **target만 번역**(이웃은 system context, to-translate 아님) → 출력=target 번역(추출 불요). math_protect 왕복; placeholder 누락/빈 출력 → **fail-preserve**(기존 row 유지). 테스트.
- **partial (분포 일반화)**: doc7 분포는 표본. `<25`가 다른 doc fragment 놓칠 수 → dry-run + `--chunk-id`로 보완; 8e 7-doc서 분포 재검토(기재).

### 3. Edge cases
- **accept (is_repeated 폐기)**: count≥2가 정당한 반복 'where'/'Proof.'를 제외. **is_repeated 제거** — 저작권 보일러플레이트는 `<25` 길이(59자)로 이미 제외됨. 보일러플레이트는 **패턴**(필요 시)으로만, 반복 카운트 금지. 테스트(중복 'where' 미제외).
- **accept (is_reference_number regex)**: digit-ratio 금지(K=10/p=0.5 오제외). **타깃 regex**: `^\(?\d+(\.\d+)*\)?[.:]?$` + `Eq.`/`Fig.`/`Table`/`[숫자]` prefix. 테스트.
- **accept (math 확장)**: selector의 `is_math_dense` = `has_math($)` OR `\(`/`\[` 포함(선택 안전). math_protect 자체는 8e.
- **accept (CRITICAL, 이웃 all-type)**: text-only는 'where'가 필요로 하는 **수식/heading context 제거** → 실패 재현. 이웃 context = **all type 라벨**(`[수식] $$...$$` 등), 8d-2a build_chunk_context 스타일. 테스트.
- **accept (resize compare/close)**: margin은 **single mode만**; compare는 overlay(margin 0, 1fr-1fr 보존); close 시 margin clear. 테스트(compare 무squeeze + close→margin0).

### 4. Alternative approaches
- **accept**: `--chunk-id ... --dry-run/--apply` 명시 경로 추가(측정된 defect 1개에 안전). auto `--short-only`와 병존.
- **accept**: context-retranslate row `cache_key=NULL`(content-only 캐시 비오염) — §2.
- **accept**: resize는 single-mode-only margin(compare overlay).

### 5. Missing tests — 전부 accept
1. `test_short_retranslate_does_not_poison_content_cache` — 'where'(이웃A) 재번역 후, 다른 'where'(이웃B) 번역이 A의 한국어 미재사용(cache_key NULL).
2. `test_short_retranslate_duplicate_where_not_excluded` — 중복 'where'는 후보 유지(count 기반 제외 없음).
3. `test_short_retranslate_malformed_llm_preserves_existing` — 빈/delimiter-free/placeholder누락 출력 → 기존 translated 불변.
4. CLI subprocess(`cli.py`): `--short-only --dry-run` 무기록, missing doc exit 2, LLM health fail exit 4, `--chunk-id`.
5. `test_resize_compare_no_squeeze` + `test_resize_close_then_toggle_clears_margin` + restore.
6. is_reference_number / is_math_dense / neighbor-all-type 단위.

## Plan revisions (after debate)
- R1 재번역 = **cache 우회 + cache_key=NULL**(poisoning 방지).
- R2 CLI = `src/ht_lens/cli.py` translate-chunks `--short-only/--max-chars/--dry-run/--chunk-id`.
- R3 target만 번역(이웃=system context) + placeholder/빈 출력 fail-preserve(추출 로직 없음).
- R4 **is_repeated 제거**(보일러플레이트는 <25 길이로 이미 out; 반복 카운트 금지).
- R5 is_reference_number = 타깃 **regex**(digit-ratio 금지).
- R6 is_math_dense = has_math + `\(`/`\[`.
- R7 이웃 context = **all type 라벨**(수식/heading 포함; text-only 폐기).
- R8 `--chunk-id` 명시 경로 추가.
- R9 resize margin = **single mode만**, compare overlay, close→clear.
- R10 Codex 6 테스트 전부.

## DoD checklist
| DoD item | Status | Evidence |
| -------- | ------ | -------- |
| 짧은 fragment 개선(where→여기서) | 계획 | select + all-type neighbor retranslate + 사용자 |
| 수식/참조/보일러플레이트 제외 | 계획 | regex ref + math + <25(boilerplate) 테스트 |
| 덮어쓰기 안전 | 계획 | dry-run no-write + fail-preserve + cache_key NULL 테스트 |
| resize + 본문 연동 + sessionStorage | 계획 | resize jsdom(single margin/compare overlay/clamp/sessionStorage/close) |
| 1.x 무손상 | 계획 | translate/frontend만, migration 0, blocks=49850, 736 회귀 |

## Risk register
| Risk | L | I | Mitigation |
| ---- | - | - | ---------- |
| cache poisoning | 중 | 고 | 우회+cache_key NULL(R1) + 테스트 |
| 정상 번역 덮어쓰기 | 중 | 중 | <25+regex 제외+dry-run+fail-preserve |
| 이웃 context 부족(where 재실패) | 중 | 중 | all-type 이웃(R7) |
| LLM 출력 오염 | 중 | 중 | target만 번역+placeholder fail-preserve(R3) |
| resize compare squeeze/stale gutter | 중 | 중 | single-mode margin+close clear(R9) + 테스트 |
| 1.x 회귀 | 저 | 고 | translate/frontend 신규·확장만, migration 0, 736 회귀 |

## Decision
- [x] **PASS → proceed to code** (R1–R10). Codex correctness/안전 fix 전부 반영, scope(Planner) 유지 + `--chunk-id` 안전 경로. RE-PLAN 불요(설계 유지, 하드닝).
- [ ] RE-PLAN
