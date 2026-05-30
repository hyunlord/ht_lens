# Phase 8b — Verify (self)

마지막 code commit: tests 커밋 (feat + test). git status = 코드 무변경(워크플로 stub 3개만 untracked). 2026-05-30.

## 5-A. Automated checks
| Check | Command | Result |
| --- | --- | --- |
| Lint | `uv run ruff check .` | All checks passed |
| Format | `uv run ruff format --check .` | 179 files already formatted |
| Type | `uv run mypy src` | Success: no issues found in 79 source files |
| Test | `uv run pytest -m "not llm and not slow" -q --no-cov` | 648 passed, 1 skipped, 7 deselected in 589.62s |
| Coverage | n/a (프로젝트 `make test-fast` 표준 `--no-cov`) | n/a |
| CI | prototype-reflow 브랜치 — GitHub CI는 8e cutover까지 미발생. 로컬 CI-equivalent green(위 4행). | n/a |

테스트 회계: 619 → 648 = +29 = 12 test_math_protect + 8 test_chunk_translate + 5 test_chunk_embed + 2 test_chunk_schema(0006 additive + round-trip) + 2 extract-mineru CLI.

## 5-B. DoD 검증 (ROADMAP 8b)
| DoD | Evidence |
| --- | --- |
| chunk 번역 + 수식 placeholder byte-identical 보존 | test_math_protect 12건(operatorname*/textstyle byte-identical, 누락 검출) + test_chunk_translate(math 보존, `⟦MATH` 잔존 0) + **실 E2E doc7 103 chunk**: equation content==translated_text(byte-identical passthrough), text `$...$` 보존, 리터럴 placeholder 잔존 0 |
| embedding 생성 | test_chunk_embed 5건(text/heading만, idempotent, model-change refresh) + chunk_embeddings COUNT |
| Phase 7a-2 5.66x 적용 | test_cache_dedup(3 chunk 중 동일 2개 → LLM 2회 호출) + Semaphore(7) + as_completed/cancel/retry_failed/status finalize 재사용 |

## 5-C. verify-cross R1(debate) contract fix 검증
| debate 지적 | 처리 | Evidence |
| --- | --- | --- |
| cache_key content-only 오류 | full `cache_key(content,src,tgt,model)` | test_cache_key_includes_src_tgt_model |
| missing placeholder append가 byte-identical 위반 | **status='failed', content 미변형** | test_math_lost_marks_chunk_failed (status=failed, "누락"/"MATH" 미포함) |
| chart content 손실 | image chunk content도 번역 | test_image_caption_and_chart_content_translated (chart translated_text="[KO] bar chart values") |
| 7a-2 retry/cancel/status 누락 | 충실 재사용 | chunk_pipeline retry_failed/as_completed cancel/_finalize + test_skips_already_translated |
| 0006 additive | additive-only | test_migration_0006_additive_only (1.x+chunks DDL byte-identical) |
| embedding 중복 | helper 재사용 thin upsert_chunk_embedding | store.py 공유 |
| type 택소노미 lock | 파서출력 (text/heading) | chunk_backfill 필터 + test |
| FK cascade | CASCADE | test_chunk_embedding_cascade_on_document_delete |

## 5-D. 1.x 무손상 (3중)
- test_migration_0006_additive_only: 1.x 7테이블 + chunks + documents DDL byte-identical.
- test_1x_translations_untouched (chunk_translate): 1.x translation "안녕" 유지.
- test_1x_block_embeddings_untouched (chunk_embed): 1.x block_embeddings 유지.
- full regression 619 영역 전부 green.

## 5-E. 잔존 한계 (정직)
1. **실 qwen 번역 미실행**: E2E는 MockLLMClient (1.x 테스트와 동일 관행). 실 qwen+v2_ko 번역 품질은 sandbox에서 검증됨, 8b는 파이프라인/수식보호 검증. 실 번역은 8e 마이그레이션.
2. **진짜 병렬성 미증명 (debate §5)**: dedup-count(LLM 2회)는 cache 동작 증명이나 Semaphore(7) 동시 실행을 타이밍/barrier로 증명하진 않음. 7a-2 구조 그대로 재사용이라 동시성 보존되나 8b 테스트는 dedup만.
3. **table 실검증 0**: doc7 챕터 table 0개. text 동일 로직(risk 낮음), 실검증 8e.
4. **chunk 검색(RAG) 미구현**: 임베딩 생성만, 검색은 1.x 유지(8d).

## 5-F. Scoring (self)
| Item | /Max | 근거 |
| --- | --- | --- |
| 독창성 | 12/15 | placeholder 보호(byte-identical/missing→failed) + 7a-2 일반화 + chunk-parallel embedding(1.x 무손상). 견고, 비-신규. |
| 완결성 | 32/35 | DoD 3/3 + 29 테스트 + 실 doc7 E2E(103 chunk) + full regression. 차감: 진짜 병렬성 테스트 미작성(§5), 실 qwen 미실행, table 미검증. |
| 안정성 | 27/30 | mypy/ruff clean, 0006 additive 증명, missing→failed(손실 0), 1.x 3중 무손상, FK cascade. 차감: 병렬성 타이밍 미증명. |
| 확장성 | 18/20 | chunk_translations/embeddings가 8c viewer/8d chat 수용, math_protect 재사용 가능, embedding helper 공유. 차감: chunk 검색 8d 연기. |
| **Total** | **89/100** | |

## 5-G. Self verdict
- [ ] PASS_CANDIDATE (≥95)
- [x] **submit to cross-verify** (self 89 < 95, 정직). DoD 3/3 + debate contract fix 전부 반영. 잔존은 구조적(실 qwen/병렬성 타이밍/table = 8e·운영). RE-CODE 후보: 진짜 병렬성 barrier 테스트(§5) 추가 여부 cross-verify 판단.
- [ ] FAIL → RE-PLAN
