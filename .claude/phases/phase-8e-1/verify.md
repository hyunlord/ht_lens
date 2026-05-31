# Phase 8e-1 — Verify (self)

math 수식밀집 영어 fallback 교정(ASCII sentinel + 보존 지시 + retry, byte-identical) + 볼드 method spike(finding). 모든 값 실측, 코드 2 commit(`d08904b` feat / `bd3f166` test) 이후 git status clean(untracked=verify/summary/verify-cross 템플릿뿐).

## 5-A. Automated checks
| Check    | Command | Result |
| -------- | ------- | ------ |
| Lint     | `uv run ruff check .` | **All checks passed!** |
| Format   | `uv run ruff format --check .` | **197 files already formatted** |
| Type     | `uv run mypy src/` | **Success: no issues found in 84 source files** |
| Test     | `uv run pytest -m "not llm and not slow"` | **768 passed, 1 skipped, 8 deselected** (551.40s) |
| New tests | math_protect(+1) / translate_prompt(+2) / chunk_translate(+4) | **7 신규 passed** |
| Coverage | `--cov` (자동) | math_protect/chunk_pipeline 신규 경로 커버(아래 5-C) |
| CI       | GitHub Actions | **N/A** — main/PR만(`prototype-reflow` 트리거 없음). local 768이 CI-equivalent. |

- 768 = 8d-2c 종료 761 + 신규 7. 회귀 0(공유 `math_protect` sentinel 변경 + `_translate_system` 변경에도 8b/8d-2c/6f-5 테스트 전부 green).

## 5-B. Functional checks

### math 강건화 (DoD 핵심) — 실 qwen3.6-27b, dev DB doc1
**진단(challenge 전)**: `⟦MATHi⟧`(U+27E6/27E7)는 opaque하지 않음 — bracket-mangle(chunk16: `$\ll MATH0 \gg$`) 또는 math-hallucinate(chunk67: placeholder 무시, `\text{Dir}` 재생성). `[[MATHi]]`만으론 chunk67 0/6. **`[[MATHi]]` + 보존 지시문 → 16:3/3, 67:6/6, 71:4/4**(전부 복구).

**live 재처리 결과**(`translate-chunks --doc-id 1 --retry-failed`, dev DB):
```
BEFORE: failed=6  translated=97
AFTER:  failed=0  translated=103   (ok: translated=6 ... failed=0)
```
- 6 chunk(16/67/71/72/76/90) 전부 `failed`→`translated`, **잔존 영어 0**.
- **byte-identical**(원본 content math run vs 저장 translation): chunk16 3/3, chunk67 6/6, chunk90 3/3 — 전부 동일. (예: chunk67 `$p ( z ) = \operator...` 원본 그대로, hallucinate 아님.)

### 볼드 method spike (R-F finding)
- MinerU 3.2.1 CPU `pipeline` 산출물(middle.json/content_list.json) **span 키 = bbox/type/content/score/image_path/cross_page뿐. 스타일/bold/weight/font 키 없음**(초기 grep "bold"는 본문 텍스트 substring 오탐). raw md `**` 0개.
- **결론**: 볼드는 CPU pipeline에 미존재 → GPU `vlm/hybrid` backend 또는 PyMuPDF font-flag 재결합 필요. challenge R-F대로 **finding 문서화 + GPU 결정 8e-2 backend 선택으로 defer**. 8e-1 차단 아님(렌더는 marked가 `**`→`<strong>` 이미 지원).

### 1.x 무손상 (prod `data/ht_lens.db`)
```
alembic=0004  blocks=49850  chunk_tables=0
```
- live 재번역은 dev DB만 write(prod 불변). migration 0건(translate/llm만).

## 5-C. Regression / new code-path lock (CLAUDE.md 가드)
| 새 코드 경로 | 잠금 테스트 (grep) | 회귀 무손상 |
| ------------ | ----------------- | ----------- |
| `PH_OPEN/PH_CLOSE = [[/]]` + escape된 `_PLACEHOLDER_RE` | `test_phase8e1_sentinel_is_ascii_brackets`, `test_source_placeholder_collision_detected` | 8b `test_math_protect`(byte-identical round-trip) 전부 green |
| `_translate_system` placeholder 규칙(양 branch) | `test_en_to_ko_prompt_has_placeholder_preservation_rule`, `test_generic_prompt_has_placeholder_preservation_rule` | 6f-5 `test_translate_prompt`(ko ratio>0.6, 분기) green |
| `_MATH_LOSS_RETRIES` retry loop(`_translate_protected`) | `test_math_loss_retries_until_placeholder_restored`(§5.1), `..._exhaustion_fails_with_no_cache`(§5.2) | 기존 `test_math_lost_marks_chunk_failed`(retry 소진→failed) green |
| dedup owner-future 내부 retry | `test_math_loss_retry_dedups_duplicate_chunks`(§5.3, calls==2 no storm) | 기존 `test_cache_dedup_one_llm_call` green |
| caption all-or-nothing(명시 주석) | `test_caption_math_loss_discards_body_all_or_nothing`(§5.4) | 기존 caption 테스트 green |
| 공유 코드 영향(8d-2c short_retranslate가 protect/restore 재사용) | `test_short_retranslate*`(ASCII prefix 자동 상속) | 8d-2c 25 테스트 green |
- 새 식별자 grep: `git grep "_MATH_LOSS_RETRIES" src/` → 1 def + 1 use. `grep "test_math_loss" tests/` → 3 신규.

## 5-D. Scoring (100, self-assessment)
| Item | Score / Max | Evidence |
| ---- | ----------- | -------- |
| 독창성 | 13 / 15 | 진단-주도(실 qwen 실측으로 원인 확정 후 설계): sentinel mangle vs hallucinate 분리, 보존 지시문이 hallucinate 교정. retry는 dedup-safe owner-future. (−2: sentinel/지시문은 표준 기법) |
| 완결성 | 33 / 35 | math 6/6 복구 + byte-identical, R-A~E + 7 테스트(Codex §5 전부), 볼드 R-F finding. (−2: 볼드는 finding/defer — DoD "method"는 충족하나 구현은 8e-2 GPU 결정 의존) |
| 안정성 | 29 / 30 | byte-identical 3/3·6/6·3/3, 768 green(공유 코드 변경 회귀 0), retry bounded+dedup-safe, caption all-or-nothing, 1.x 0004/49850/0. (−1: retry는 temp=0 결정성에선 무효 — R-A/B가 실질 교정, retry는 nondeterminism 대비 net) |
| 확장성 | 18 / 20 | ASCII sentinel + 지시문은 7-doc(8e-2) 일반 적용 가능. 볼드 backend 결정 8e-2로 명확 defer. (−2: 볼드 GPU 경로 미실증) |
| **Total** | **93 / 100** | |

## 5-E. Self verdict
- [x] **PASS_CANDIDATE (93)** → Stage 5-B cross-verify Round 1. 진단-주도 설계, 6/6 live 복구 + byte-identical, 768 green, 1.x 무손상, Codex §5 테스트 전부.
- [ ] FAIL → RE-CODE
- [ ] FAIL → RE-PLAN

### 결정 필요 / 잔여 (R1 선공개)
1. **볼드 GPU 결정(사용자)**: CPU pipeline 미지원 확정 → 8e-2에서 (a) 1회성 GPU vlm/hybrid 추출 vs (b) 볼드 영구 defer. (challenge R-F 게이트)
2. retry는 결정적 손실엔 무효(R-A/B가 실질 교정); provider nondeterminism 대비 net으로만 유지(bounded=2 attempts).
3. `\(`/`\[` 미보호(MinerU `$` emit) — 8b 한계 유지, 문서화.
