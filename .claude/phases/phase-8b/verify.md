# Phase 8b — Verify (self) — v2 (post RE-CODE)

마지막 code commit: `fix(phase-8b): persistent DB cache + live cached stat + collision-safe math + CLI errors`.
git status = 코드 무변경(워크플로 summary.md stub만 untracked). 2026-05-30. RE-CODE = verify-cross R1 DOWNGRADE 대응.

## 5-A. Automated checks
| Check | Command | Result |
| --- | --- | --- |
| Lint | `uv run ruff check .` | All checks passed |
| Format | `uv run ruff format --check .` | clean |
| Type | `uv run mypy src` | Success: no issues found in 79 source files |
| Test | `uv run pytest -m "not llm and not slow" -q --no-cov` | 653 passed, 1 skipped, 7 deselected in 570.77s |
| Coverage | n/a (프로젝트 `make test-fast` 표준 `--no-cov`) | n/a |
| CI | prototype-reflow — GitHub CI는 8e cutover까지 미발생, 로컬 CI-equivalent green | n/a |

테스트 회계: 619 → v1 648 (+29) → v2 653 (+5 RE-CODE) = +34 total.

## 5-B. DoD 검증 (ROADMAP 8b)
| DoD | Evidence |
| --- | --- |
| chunk 번역 + 수식 placeholder byte-identical | test_math_protect 12 + test_chunk_translate(math 보존, ⟦MATH 잔존 0) + 실 E2E doc7 103 chunk (equation byte-identical passthrough, $ 보존) |
| embedding 생성 | test_chunk_embed 5 (text/heading, idempotent, model-change, cascade) |
| Phase 7a-2 5.66x 적용 | **(R1 fix 후 완전)** in-run dedup + **persistent DB cache**(cross-doc) + **live stats.cached** + **peak-concurrency 병렬 증명**(Semaphore(3)→peak 3) + retry/cancel/status |

## 5-C. verify-cross R1 DOWNGRADE 지적 → 처리
| R1 지적 | 처리 | Evidence |
| --- | --- | --- |
| persistent DB cache 누락 (ix_chunk_tr_cache 미사용) | `_db_cache_lookup` 추가, cross-run/doc 재사용 | test_persistent_db_cache_across_runs (2nd doc, LLM 0 호출, cached=1) |
| stats.cached dead accounting | `_cached_translate→(text,fresh)`, 캐시 chunk는 cached 카운트 | test_cached_stat_reflects_dedup, dedup 테스트 translated=2/cached=1 |
| collision guard가 real math raw 전송 | nonce sentinel prefix로 보호(skip 아님) | test_collision_with_real_math_still_protected ($x^2+y^2$ byte-identical 생존) |
| translate-chunks CLI 약한 에러 처리 | LLMConfig(5)/Health(4)/doc-404(2) 매핑 | test_translate_chunks_cli_unknown_doc_exits_2 |
| peak-concurrency 미증명 (debate §5) | barrier 테스트 | test_peak_concurrency_is_parallel_and_bounded |

## 5-D. Regression check (RE-CODE — CLAUDE.md 필수)
| RE-CODE 변경 | 잠금 테스트 (grep) |
| --- | --- |
| `_db_cache_lookup` (chunk_pipeline) | test_persistent_db_cache_across_runs (`_db_cache_lookup` 경로) |
| `_cached_translate` → (text, fresh) + stats.cached | test_cached_stat_reflects_dedup, test_cache_dedup (translated=2/cached=1) |
| `_translate_protected` nonce prefix + `protect_math(token_prefix=)` | test_collision_with_real_math_still_protected |
| CLI except LLMConfig/Health/ValueError | test_translate_chunks_cli_unknown_doc_exits_2 |
- R1 fix 영역 회귀: 기존 24 chunk 테스트(math/passthrough/image/1.x intact) 전부 green; dedup 테스트만 의미 변경(translated=2/cached=1, 올바름). full regression 648→653, 기존 영역 회귀 0.
- grep 확인: `_db_cache_lookup`/`token_prefix`/`stats.cached`/`LLMConfigurationError` 모두 src+test에 등장.

## 5-E. 1.x 무손상 (3중, R1 후 유지)
test_migration_0006_additive_only + test_1x_translations_untouched + test_1x_block_embeddings_untouched + full regression 619 영역 green.

## 5-F. 잔존 한계 (정직)
1. 실 qwen 번역 미실행 (Mock E2E; 실 번역은 8e). 2. table 실검증 0 (doc7 챕터 table 없음; 8e). 3. caption은 in-run 캐시만(content는 DB 캐시), 캡션 DB 재사용은 미구현(영향 작음). 4. chunk 검색(RAG)은 8d.

## 5-G. Scoring (self)
| Item | /Max | 근거 |
| --- | --- | --- |
| 독창성 | 12/15 | placeholder(byte-identical/missing→failed/collision-nonce) + 7a-2 완전 일반화(DB 캐시 포함) + chunk-parallel embedding. |
| 완결성 | 33/35 | DoD 3/3 + 34 테스트 + 실 E2E + full regression. R1의 7a-2 reuse 갭(DB 캐시/cached stat/병렬) 전부 해소. 차감: 실 qwen/table 미검증(8e). |
| 안정성 | 28/30 | mypy/ruff clean, 0006 additive, missing→failed, collision-safe, 1.x 3중 무손상, CLI 에러 매핑. 차감: caption DB 캐시 미구현(minor). |
| 확장성 | 18/20 | chunk_translations/embeddings가 8c/8d 수용, persistent 캐시가 8e 대량 재처리에 유효, helper 재사용. 차감: chunk 검색 8d 연기. |
| **Total** | **91/100** | |

## 5-H. Self verdict
- [ ] PASS_CANDIDATE (≥95)
- [x] **submit to cross-verify Round 2 (최종, CLAUDE.md cap)** (self 91 < 95, 정직). R1 DOWNGRADE의 concrete 지적(DB 캐시/cached stat/collision/CLI/병렬) 전부 fix+테스트. 잔존은 8e·8d 영역(구조적). R2가 새 concrete 결함 없이 REJECT면 Planner escalate.
- [ ] FAIL → RE-PLAN
