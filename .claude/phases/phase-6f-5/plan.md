# Phase 6f-5 — Plan

## Goal
Phase 6f-1 Gemma 4 swap 결정을 **확장 A/B 측정 결과 기반으로 reverse**: prod LLM을 qwen3.6-27b로 rollback하고, A/B에서 검증된 v2_ko Korean-instruction translate prompt를 en→ko 경로에 적용한다.

## Context
ht_lens 평가 사이클이 두 번 깊어진 결과:

1. **Phase 6e-2 재진단**: 본문 (pure_text) 카테고리에서 Gemma 4 (현 prod)가 KR 0.546, AllKor 0%. qwen 시절 baseline (doc 1) 64% 대비 큰 폭 낮음.
2. **첫 prompt A/B**: Gemma 4 + Korean-instruction prompt (v2_ko)로 KR 0.546→0.755 개선, AllKor 0%→25%. 단 격차 잔존.
3. **qwen rollback A/B**: 첫 시도 broken (75% empty — sglang raw HTTP에서 `extra_body` literal key 무시 → thinking mode ON → max_tokens 소진). Root cause 식별 후 v2 재측정:
   - qwen_current 0.867 (baseline조차 Gemma_v2 0.755보다 우세)
   - qwen_tuned_v2_ko **0.874** (>0.85 rollback trigger)
   - Matched-block 14/20 qwen 우세, gemma 0 압도

Phase 6f-1 swap의 정성 근거 (Phase E1.5 chrF +3.7, LLM-judge)는 Korean purity가 아닌 다른 axis를 측정한 것으로 추정. 사용자 체감 Issue B (영어/한글 섞임)가 본 측정과 정합.

## Scope
**In**:
- `_translate_system()` (openai_compat.py:175-185)에 **`tgt == "ko"` 분기 추가**: en→ko 면 v2_ko Korean-instruction prompt, 그 외 (ko→en, en→ja 등)는 기존 generic 영어 prompt 유지
- `.env`: TRANSLATE_LLM_* + CHAT_LLM_* + 레거시 LLM_* + OLLAMA_* → qwen3.6-27b @ `localhost:8081`
- `.env` backup (`.env.backup.gemma4_<timestamp>`)
- qwen sglang docker 가동 (Phase 6f-1 보존 launch command)
- Gemma 4 sglang docker 정지 (메모리 회수). weights/image 보존
- ht_lens restart
- 단위 테스트: prompt 분기 lock (en→ko v2_ko, ko→en/en→ja generic 보존)
- 회귀 테스트: chat path 영향 없음, override semantics 보존

**Out**:
- chat system prompt 변경 (translate 전용)
- 모델별 prompt 분기 (현 한 모델만 — 별도 phase 필요 시)
- 기존 번역 일괄 invalidate / re-translate (사용자 선택)
- Gemma 4 weights / docker image 정리 (며칠 안정 후 결정)
- Phase E2 fine-tune (qwen baseline 강함 → ROI 재평가 필요)

## Approach
1. **Prompt 분기**: `_translate_system(src, tgt)` 함수 본문에서:
   - `if src == "en" and tgt == "ko"`: return v2_ko Korean-instruction prompt (A/B 검증된 정확한 문자열)
   - else: 기존 generic 영어 prompt (보존)
2. **Generic prompt 보존 이유**: ko→en 방향 (Phase 6e-2 진단 시 doc 1 sample_mixed에서 한국어 본문이 영어로 번역된 사례 발견)이나 향후 en→ja 등 다른 방향 지원 시 안전.
3. **`.env` 변경**: 5쌍 (scoped translate, scoped chat, legacy, OLLAMA backup)의 BASE_URL + MODEL만 변경 (포트 8082→8081, model gemma-4-26b-a4b-it→qwen3.6-27b). 다른 변수 (PROVIDER=openai_compat, MAX_TOKENS, TEMPERATURE, TIMEOUT, API_KEY) 그대로.
4. **GPU swap 절차**: docker stop sglang-gemma4 → docker run sglang-qwen (Phase 6f-1 보존 launch command 그대로). qwen ready ~320s.
5. **ht_lens restart**: `pgrep -af "ht-lens serve"` 사용 패턴 (Phase 6f-1에서 학습한 정확 매칭).
6. **테스트**:
   - `tests/unit/test_translate_prompt.py` (신규): en→ko 분기는 한국어 instruction, 다른 방향은 영어 prompt 보존.
   - 회귀: 442 → 444 (신규 2-3건). 기존 `test_translate_pipeline_mock.py` 등 mock 사용 테스트는 prompt 문자열 검증 안 함 → 영향 없음 (Stage 0 grep 0건 확인).
7. **E2E 검증**: doc 4에서 5 block을 API `POST /blocks/{id}/retranslate`로 재번역 → DB `translations.model` 컬럼이 `qwen3.6-27b`로 갱신 + 응답 한국어 비율 (KR > 0.8) 확인.
8. **Chat 검증**: 새 thread + `POST /threads/{id}/explain` → model=qwen3.6-27b 응답.

## File-level changes
| Path | Action | Note |
| ---- | ------ | ---- |
| `src/ht_lens/llm/openai_compat.py` | MODIFY | `_translate_system()` 안에 `if src == "en" and tgt == "ko"` 분기 + v2_ko prompt 추가. 기존 generic prompt는 else 절로 보존. |
| `.env` | MODIFY | 5개 변수의 port 8082→8081 + model gemma-4-26b-a4b-it→qwen3.6-27b. |
| `.env.backup.gemma4_<ts>` | NEW (artifact) | 현 .env 백업 (rollback 보험). |
| `tests/unit/test_translate_prompt.py` | NEW | en→ko 분기 v2_ko Korean instruction lock + 다른 방향 generic prompt 보존 lock. |

## Dependencies (new)
| Package | Why |
| ------- | --- |
| (none) | 코드 변경 1개 함수 내부, 의존성 추가 없음 |

## Test strategy
- **Unit (신규 ~3 tests)**:
  - `_translate_system("en", "ko")`가 한국어 instruction (Korean ratio > 0.6, "한국어로 번역" 포함, "고유명사"/"수식"/"코드"/"URL"/"arXiv" 등 keep-as-is 항목 명시).
  - 영어 prompt 흔적 없음 (en→ko 출력에서 "professional translator" 또는 "Output only the translation" 미포함).
  - `_translate_system("ko", "en")` / `_translate_system("en", "ja")`가 generic 영어 prompt 보존 (백워드 호환).
- **회귀**:
  - 기존 442 테스트 모두 green 유지.
  - `test_translate_pipeline_mock.py` 등 mock 사용 — MockLLMClient는 `_translate_system` 호출 안 함 (영향 없음).
- **수동 E2E**:
  - `POST /blocks/{id}/retranslate` 5개 block × DB model 컬럼 검증.
  - `POST /threads/{id}/explain` chat 응답 model 검증.

## DoD mapping
| DoD item | How to satisfy | Evidence plan |
| -------- | -------------- | ------------- |
| qwen prod 복귀 | sglang docker 8081 가동 + `.env` 변경 + ht_lens restart | `docker ps` + `curl /v1/models` |
| v2_ko prompt 적용 (en→ko) | `_translate_system` 분기 | unit test + 새 retranslate 응답 KR > 0.8 |
| 기존 generic prompt 보존 (다른 방향) | else 절 unchanged | unit test |
| chat 영향 없음 | translate prompt만 변경 | 회귀 테스트 + E2E `/explain` |
| 회귀 0 | mypy strict / ruff / pytest | verify.md |
| Rollback 자산 | Gemma 4 sglang weights/image + .env.backup | grep + `du -sh` |

## Risk / 주의
- **Cache key 변동**: `make_cache_key(original_text, src_lang, tgt_lang, model_name)`. prompt는 cache_key에 포함 안 됨 → 기존 Gemma 4 번역은 model_name 다름 (= miss). qwen 시절 옛 캐시 (model=qwen3.6-27b)는 hit 가능. 새 번역만 v2_ko prompt 사용. **기존 번역 자동 재번역 안 함** (사용자 선택).
- **chat 시 system prompt**: `messages.py:explain_thread()`가 `build_block_context()` 결과를 system으로 전달. translate prompt 변경과 무관.
- **Phase 6e/6e-2 인프라 검증**: 본 phase가 .env scoped vars 변경 → factory가 정상 routing 하는지 implicit 검증.
- **debate에서 다룰 질문**:
  - prompt 분기 조건 (`src=="en" and tgt=="ko"`) — 향후 ja/zh 등 추가 시 N개 분기 폭발 위험. 지금 시점에서 OK인지?
  - v2_ko prompt 정확한 문자열에 typo/오타 검증 (사용자 prompt에서 복사하므로 안전하지만 lock test로 cement).
  - `_translate_user()` (context 처리)는 변경 안 함 — translate context를 한국어 prompt에 영어 context로 넘기는 게 의도된 동작인지.
