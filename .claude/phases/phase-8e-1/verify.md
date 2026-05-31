# Phase 8e-1 — Verify v2 (self, post verify-cross R1 RE-CODE)

math 수식밀집 영어 fallback 교정(ASCII sentinel + 보존 지시 + retry, byte-identical) + 볼드 method spike(finding). 모든 값 실측, 최종 code commit `e30874f`(fix) 이후 작성. git status는 code/test drift 없음(untracked = summary.md 템플릿 + scheduled_tasks.lock 뿐; verify.md 본 파일·bold_finding.md는 이 stage 산출물).

**v2 사유**: cross-verify R1(Codex DOWNGRADE 89)이 (a) byte-identical 증거가 6곳 중 3곳만, (b) hashed collision sentinel이 프롬프트 문구에 미포함, (c) coverage 수치 부재, (d) 볼드 finding 비영속 — 을 지적. (b)는 실 결함(프롬프트 일반화)으로 RE-CODE, 나머지는 증거 보강.

## 5-A. Automated checks
| Check    | Command | Result |
| -------- | ------- | ------ |
| Lint     | `uv run ruff check .` | **All checks passed!** |
| Format   | `uv run ruff format --check .` | **197 files already formatted** |
| Type     | `uv run mypy src/` | **Success: no issues found in 84 source files** |
| Test     | `uv run pytest -m "not llm and not slow"` | **768 passed, 1 skipped, 8 deselected** (577.99s; fix `e30874f` 이후 재실행) |
| Coverage | `pytest <file> --cov=<module>` | **math_protect.py 100%**, **chunk_pipeline.py 80%**(미달=transient retry/finalize 분기) |
| CI       | GitHub Actions | **N/A** — main/PR만(`prototype-reflow` 트리거 없음). local 768은 동일 환경 증거이며 GitHub CI green과 동치 아님(8e-3 main cutover 시 첫 실행). |

- 768 = 8d-2c 종료 761 + 신규 7. 프롬프트 일반화(`e30874f`) 후 재실행에도 768 유지(회귀 0).

## 5-B. verify-cross R1 resolution (DOWNGRADE 89 → 처리)
| R1 지적 | 판정 | 처리 | 증거 |
| ------- | ---- | ---- | ---- |
| §4#2 hashed collision sentinel `[[MATH<sha>n]]`이 프롬프트 문구(`[[MATH0]]/[[MATHn]]`)에 미포함 | **real(robustness)** | `_translate_system` 양 branch를 **`[[MATH`로 시작·`]]`로 끝나는 모든 토큰**으로 일반화(`e30874f`) | `test_en_to_ko_prompt_has_placeholder_preservation_rule`/`test_generic_..`(일반형 lock) |
| §4#1 byte-identical 증거 6곳 중 3곳만 | evidence | **6곳 전부 실 qwen(신 프롬프트) 재검증** | 아래 5-D, 6/6 missing=[] + byte-identical=True (chunk72 단일 span 포함) |
| §4#3 coverage 수치 부재 | evidence | 모듈별 실측 | math_protect **100%**, chunk_pipeline **80%** |
| §4#4 볼드 finding 비영속 | evidence | `.claude/phases/phase-8e-1/bold_finding.md` 영속 artifact(span 키 + 결론) | 파일 commit |
| §1 "git status clean"/"CI-equivalent" 과장 | wording | v2에서 정정(위 머리말·5-A CI 행) | — |

## 5-C. Functional checks

### math 강건화 — 실 qwen3.6-27b, dev DB doc1, 6곳 전부 (R1 §4#1 보강)
진단(challenge 전): `⟦MATHi⟧`는 opaque 아님(bracket-mangle / math-hallucinate). `[[MATHi]]`+보존 지시문이 fix.

**6곳 전부 재검증**(신 ASCII sentinel + **일반화된** 프롬프트, 실 qwen):
```
chunk 16: spans=3 missing=[] byte_identical=True -> OK
chunk 67: spans=6 missing=[] byte_identical=True -> OK
chunk 71: spans=4 missing=[] byte_identical=True -> OK
chunk 72: spans=1 missing=[] byte_identical=True -> OK   ← 단일 span(R1 지목)
chunk 76: spans=2 missing=[] byte_identical=True -> OK
chunk 90: spans=3 missing=[] byte_identical=True -> OK
ALL 6 RECOVERED + BYTE-IDENTICAL: True
```
- production 경로(`translate-chunks --retry-failed`)에서도 BEFORE failed=6 → AFTER failed=0, translated 97→103.

### 볼드 method spike (R-F finding — `bold_finding.md` 영속)
- MinerU 3.2.1 CPU `pipeline` span 키 = `bbox/type/content/score/image_path/cross_page`뿐. **style/bold/weight/font 키 0**(초기 grep은 본문 substring 오탐). raw md `**` 0.
- 결론: 볼드는 CPU 미존재 → GPU vlm/hybrid 또는 PyMuPDF 폰트플래그 필요 → **8e-2 backend 결정으로 defer**(challenge R-F). 렌더는 marked가 이미 `**`→`<strong>`.

### 1.x 무손상 (prod `data/ht_lens.db`)
```
alembic=0004  blocks=49850  chunk_tables=0
```
- live 재번역은 dev DB만 write. migration 0건.

## 5-D. Regression / new code-path lock
| 새 코드 경로 | 잠금 테스트 (grep) | 회귀 무손상 |
| ------------ | ----------------- | ----------- |
| `PH_OPEN/PH_CLOSE=[[/]]` + escape `_PLACEHOLDER_RE` | `test_phase8e1_sentinel_is_ascii_brackets`, `test_source_placeholder_collision_detected` | 8b `test_math_protect` 100% green |
| `_translate_system` 일반화 placeholder 규칙(양 branch) | `test_en_to_ko_prompt_has_placeholder_preservation_rule`, `test_generic_prompt_has_placeholder_preservation_rule` | 6f-5 prompt 테스트 green |
| `_MATH_LOSS_RETRIES` retry(`_translate_protected`, owner-future) | `test_math_loss_retries_until_placeholder_restored`(§5.1), `..._exhaustion_fails_with_no_cache`(§5.2), `..._dedups_duplicate_chunks`(§5.3) | 기존 `test_math_lost_marks_chunk_failed`/`test_cache_dedup` green |
| caption all-or-nothing(명시) | `test_caption_math_loss_discards_body_all_or_nothing`(§5.4) | 기존 caption 테스트 green |
| hashed collision sentinel(프롬프트 일반형 + 파이프라인) | `test_collision_with_real_math_still_protected` + 프롬프트 일반형 lock | 동일 |
- 새 식별자 grep: `git grep _MATH_LOSS_RETRIES src/`→1 def+1 use; `grep test_math_loss tests/`→3.

## 5-E. Scoring (100, self v2)
| Item | Score / Max | Evidence |
| ---- | ----------- | -------- |
| 독창성 | 13 / 15 | 진단-주도(실측 후 설계), sentinel mangle vs hallucinate 분리, 지시문이 hallucinate 교정, dedup-safe retry. (−2: 표준 기법) |
| 완결성 | 33 / 35 | math **6/6** 복구 + byte-identical(전수), R-A~E + 7 테스트(Codex §5 전부) + R1 일반화. (−2: 볼드는 finding/defer — DoD "method" 충족, 구현은 8e-2) |
| 안정성 | 28 / 30 | 6/6 byte-identical, 768 green(공유코드 회귀 0), retry bounded+dedup-safe, caption all-or-nothing, hashed sentinel 프롬프트 커버, 1.x 0004/49850/0. (−2: retry는 temp=0 결정성엔 무효—R-A/B가 실질, net 용도; hashed live는 rare-path) |
| 확장성 | 18 / 20 | ASCII sentinel+일반 지시문 7-doc 적용 가능, 볼드 backend 8e-2 명확 defer. (−2: 볼드 GPU 경로 미실증) |
| **Total** | **92 / 100** | R1 89 → 일반화 fix + 전수 증거로 안정성/완결성 보강 |

## 5-F. Self verdict
- [x] **PASS_CANDIDATE (92)** → cross-verify Round 2(마지막). R1 real 결함(프롬프트 일반화) fix+lock, 증거 갭(byte-identical 전수/coverage/볼드 artifact) 폐쇄.
- [ ] FAIL → RE-CODE
- [ ] FAIL → RE-PLAN

### 잔여 (R2 선공개)
1. **볼드 GPU 결정(사용자, 8e-2)**: CPU 미지원 확정 → (a) 1회성 GPU vs (b) PyMuPDF 폰트플래그 vs (c) defer.
2. hashed collision sentinel은 rare-path(소스에 `[[MATHi]]`형 토큰 존재 시만); 프롬프트 일반형으로 커버 + 파이프라인 테스트 존재, 실 qwen hashed 동작은 live 미측정(rare).
3. retry는 결정적 손실엔 무효(R-A/B가 실질 교정), provider nondeterminism 대비 net(bounded 2).
