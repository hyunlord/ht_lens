# Phase 6f-5 — Verify (self)

`git status` clean (Phase 6f-5 영역 기준). 미커밋: `ROADMAP.md` (사용자 작업), `.env.backup.gemma4_20260524_184518` + `.env.backup.20260523_181759` (ops artifact, git ignore 대상). 이번 phase의 src/test commit 모두 완료.

## 5-A. Automated checks
| Check | Command | Result |
| ----- | ------- | ------ |
| Lint | `uv run ruff check src/ tests/` | `All checks passed!` |
| Format | `uv run ruff format --check src/ tests/` | `123 files already formatted` |
| Type | `uv run mypy src/` | `Success: no issues found in 60 source files` |
| Test | `uv run pytest tests/ --no-cov -q` | `451 passed, 8 skipped` (이전 442 → +9 신규 prompt branch tests, 회귀 0) |
| CI | (push 후 검증 예정) | — |

## 5-B. Functional checks

### B-1. Prompt branch unit tests (10건 모두 pass)
```
test_en_to_ko_returns_korean_instruction_prompt        PASSED
test_en_to_ko_prompt_has_no_qwen_era_english_signature PASSED
test_en_to_ko_prompt_is_majority_korean                PASSED
test_ko_to_en_uses_generic_english_prompt              PASSED
test_en_to_ja_uses_generic_english_prompt              PASSED
test_uppercase_lang_codes_hit_korean_branch            PASSED
test_whitespace_lang_codes_hit_korean_branch           PASSED
test_mixed_case_lang_codes_hit_korean_branch           PASSED
test_empty_or_none_lang_codes_fall_through_to_generic  PASSED
test_cache_key_does_not_include_system_prompt          PASSED
```
- en→ko v2_ko 분기 + 영어 잔재 검출 + Korean ratio floor
- 다른 방향 (ko→en, en→ja) generic 보존
- lang code 정규화 (upper / whitespace / mixed)
- Phase 6f-5 cache policy lock (prompt 변경이 cache_key 영향 없음 — 사용자 "보존" 결정 cement)

### B-2. qwen rollback infrastructure
| 항목 | 결과 |
|---|---|
| Gemma 4 docker stop | 즉시 |
| qwen sglang docker run (Phase 6f-1 보존 launch command) | container `009900359ca9` |
| qwen ready | **321s** |
| sglang thinking-OFF smoke (top-level `chat_template_kwargs`) | `content='딥러닝 모델이 점점 더 커지고 있습니다.'`, `reasoning_tokens=0`, `finish=stop` ✓ |
| ht_lens restart (강화 절차: 특정 PID SIGTERM → SIGKILL fallback) | port 해제 확인 후 새 PID 3587325 정상 가동 |
| HTTP 200 / 7 documents | 즉시 응답 |
| **ht_lens 다운타임** | 약 6분 (Gemma 4 stop → qwen ready 321s → restart) |

### B-3. E2E retranslate (challenge §4 DoD evidence)
5 blocks in doc 4 (text/header, 100-500 chars) → `POST /blocks/{id}/retranslate`:

| block | KR | model | latency |
|---:|---:|---|---:|
| 148 | 0.95 | `manual-retranslate:qwen3.6-27b:1779616044` | 7.6s |
| 155 | **1.00** | `manual-retranslate:qwen3.6-27b:1779616050` | 6.7s |
| 156 | **1.00** | `manual-retranslate:qwen3.6-27b:1779616055` | 4.5s |
| 158 | **1.00** | `manual-retranslate:qwen3.6-27b:1779616060` | 4.7s |
| 160 | 0.84 | `manual-retranslate:qwen3.6-27b:1779616067` | 7.9s |

- **평균 KR 0.96** (Phase 6f-2 재진단의 Gemma 4 prod 측정 0.546 대비 +0.41, Gemma 4 v2_ko A/B 0.755 대비 +0.21)
- DoD evidence pattern `LIKE 'manual-retranslate:qwen3.6-27b:%'` 100% 일치
- 5/5 한국어 정상 응답, finish_reason normal

### B-4. Chat E2E
- POST `/threads` block_id=156 → thread 15 생성
- POST `/threads/15/explain` → model=`qwen3.6-27b`, KR=0.82, 한국어 구조화 설명 (논문 단락 의미 해설), latency 107s
- chat path 변경 없음 검증 — chat router는 build_block_context 결과를 system으로 직접 받음 (translate 분기 무관)

### B-5. Regression check (RE-CODE 없음, 1차 implement)
| 신규 코드 경로 | 잠금 테스트 |
|---|---|
| `_translate_system()` en→ko 분기 | `test_en_to_ko_returns_korean_instruction_prompt`, `_no_qwen_era_english_signature`, `_is_majority_korean` |
| lang code 정규화 (lower/strip) | `test_uppercase_lang_codes_hit_korean_branch`, `_whitespace`, `_mixed_case`, `_empty_or_none_fall_through` |
| else 절 generic prompt 보존 | `test_ko_to_en_uses_generic_english_prompt`, `_en_to_ja_uses_generic` |
| Cache key 정책 (prompt 변경 invariance) | `test_cache_key_does_not_include_system_prompt` |
| `.env` 변경 → factory routing | 회귀 (test_factory_split + test_dotenv_loader 모두 green) + E2E B-3/B-4 |
| ht_lens restart 절차 (특정 PID SIGKILL) | manual 검증 (B-2) — 단위 자동화 안 됨 |

## 5-C. Scoring (100, self-assessment)
| Item | Score / Max | Evidence |
| ---- | ----------- | -------- |
| 독창성 | 13 / 15 | A/B 측정 결과를 prod 결정으로 직접 환원 (qwen 0.874 > Gemma 0.755 → rollback). Phase 6f-1 swap을 evidence-driven으로 reverse. lang code 정규화 + cache policy 명문화로 운영 함정 미리 차단. 미세 감점: prompt를 transport 클라이언트에 박은 layering 비최적 (Phase 6f-6 후보로 documented). |
| 완결성 | 33 / 35 | DoD 6 항목 모두 evidence: prompt branch unit (10), .env + ht_lens restart smoke, E2E retranslate 5/5 (KR 0.84-1.00 + manual-retranslate prefix), chat E2E (model=qwen3.6-27b, KR 0.82). Codex critique 4건 모두 ACCEPT 또는 명시적 defer (cache prompt-versioning Phase 6f-6). 미세 감점: CI는 push 후 결과 필요. |
| 안정성 | 28 / 30 | 451/451 pass + 8 expected skip. mypy / ruff / format clean. 회귀 0. 강화된 restart 절차 (특정 PID SIGKILL). 미세 감점: prompt-versioned cache 부재로 옛 qwen cache가 새 PDF에서 hit 가능 (의도된 사용자 결정이지만 운영 risk). |
| 확장성 | 17 / 20 | Phase 6e LLMClient split + Phase 6e-2 fail-closed + Phase 6f-5 prompt branch까지 layered 인프라 검증. `_translate_system` 분기는 향후 ja/zh 추가 시 N개 분기 폭발 위험 (Codex 지적). policy layer refactor Phase 6f-6 후보 명시. |
| **Total** | **91 / 100** | |

## 5-D. Self verdict
- [x] PASS_CANDIDATE (≥90, 보수적)
- [ ] FAIL → RE-CODE
- [ ] FAIL → RE-PLAN

근거: 모든 자동 검사 green (451/451), Codex debate critique 4건 모두 ACCEPT + 반영, E2E 5 blocks 평균 KR 0.96 (목표 >0.8 초과), chat 영향 없음 검증. R1 cross-verify 결과 대기.
