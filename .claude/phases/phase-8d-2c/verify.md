# Phase 8d-2c — Verify (self)

neighbor-context 짧은-chunk 재번역(cache 우회 + cache_key=NULL) + 채팅 drawer resize(single-mode 본문 margin 연동). 8d 시리즈 마지막. 모든 값은 실측(코드 3 commit `96eb729`/`ceae9fa`/test 직후, git status clean).

## 5-A. Automated checks
| Check    | Command | Result |
| -------- | ------- | ------ |
| Lint     | `uv run ruff check .` | **All checks passed!** |
| Format   | `uv run ruff format --check .` | **197 files already formatted** |
| Type     | `uv run mypy src/` | **Success: no issues found in 84 source files** |
| Test     | `uv run pytest -m "not llm and not slow"` | **758 passed, 1 skipped, 8 deselected** (674.75s) |
| New tests | `pytest test_short_retranslate{,_cli} test_resize_js` | **9 + 5 + 8 = 22 passed** |
| Coverage | `--cov` (자동) | short_retranslate.py **92%** (미달 라인=헬퍼 분기/`__all__`) |
| CI       | GitHub Actions | **N/A** — CI는 main/PR만 실행(`prototype-reflow` 브랜치). 위 local fast suite가 CI-equivalent 증거. |

- 758 = 8d-2b 종료 시점 736 + 신규 22. deselect 8 / skip 1 모두 기존(@llm cross-lingual + jsdom-CI provisioning debt). 신규 테스트는 @llm/slow 마크 없음.

## 5-B. Functional checks

### live 재번역 demo (DoD: where→여기서) — 실 qwen, dev DB `data/ht_lens_v2.db` doc 1
```
# dry-run (무기록)
$ python -m ht_lens.cli translate-chunks --doc-id 1 --short-only --dry-run --db data/ht_lens_v2.db
  chunk 2: '어디에' -> '여기서'
  chunk 35: '모델은 다음과 같습니다:' -> '모델은 다음과 같습니다:'
ok: doc_id=1 mode=dry-run candidates=2 retranslated=0 failed=0
# apply
$ python -m ht_lens.cli translate-chunks --doc-id 1 --short-only --db data/ht_lens_v2.db
ok: doc_id=1 mode=apply candidates=2 retranslated=2 failed=0
# DB 확인
  id=2  content='where'                -> '여기서'                 cache_key=NULL status=translated
  id=35 content='model is as follows:' -> '모델은 다음과 같습니다:' cache_key=NULL status=translated
```
- **id=2 `where`: `어디에`→`여기서`** = DoD 핵심 오역 교정. 이웃 수식 context로 connective "where"가 locative "어디에"가 아닌 "여기서"로.
- **id=4/37/43 `(28.116)/(28.123)/(28.126)` = 후보에서 제외**(is_reference_number) → 정상 식번호 미손상.
- id=35 정상 단문은 재번역해도 동일 텍스트(무해), cache_key는 NULL로 전환(R1).
- dry-run candidates=2/retranslated=0 → **무기록 확인**. apply 후 cache_key=NULL → **content 캐시 비오염(R1) 실증**.

### 1.x 무손상 (prod `data/ht_lens.db`)
| 항목 | 값 | 비고 |
| ---- | -- | ---- |
| alembic | **0004** | 8d-2c는 migration 0건 (translate/frontend만) |
| blocks | **49850** | 1.x 데이터 불변 |
| 2.0 tables in prod | **NONE** | chunks/chunk_translations/... prod에 없음 |
- dev DB(ht_lens_v2.db)·prod DB(ht_lens.db) 모두 `.gitignore` → dev 재번역 write가 git status에 안 보임(정상).

### challenge R1–R10 매핑
| R | 요구 | 구현 | lock |
| - | ---- | ---- | ---- |
| R1 | 재번역 = cache 우회 + cache_key=NULL | `retranslate_short`는 `_cached_translate`/`make_cache_key` 미사용, 자체 `_translate_with_context`(fresh) + `cache_key=None` write | `test_..._writes_null_cache_key_no_poison`(_db_cache_lookup→None) + live apply(ck=NULL) |
| R2 | CLI `--short-only/--max-chars/--dry-run/--chunk-id` | `cli.py` translate-chunks 4 flag + short branch | `test_short_retranslate_cli`(5 subprocess) |
| R3 | target만 번역(이웃=context), placeholder/빈 출력 fail-preserve | `_translate_with_context`(target만, `context=ctx`); missing placeholder raise→preserve, empty→failed no-write | `test_..._malformed_llm_preserves_existing` |
| R4 | is_repeated 폐기 | 반복 카운트 함수 없음; <25 길이로 보일러플레이트(59자) 제외 | `test_..._duplicate_where_not_excluded`(중복 where 2개 유지) |
| R5 | is_reference_number = 타깃 regex (digit-ratio 금지) | `_REF_NUMBER_RE`(괄호/점/Eq.Fig.Table/appendix `A.1`) + `_BRACKET_CITE_RE`(`[12]`) | `test_is_reference_number_...`(K=10/p=0.5 통과) |
| R6 | is_math_dense = has_math + `\(`/`\[` | `is_math_dense` = `has_math` OR `\(`/`\[` | `test_is_math_dense_...` |
| R7 | 이웃 context = all-type 라벨 | `_neighbor_context` = `[섹션]/[수식]/[본문]...` 라벨, target 제외 | `test_neighbor_context_includes_all_types_labelled` |
| R8 | `--chunk-id` 명시 경로 | `chunk_ids` param + CLI flag(selector 우회) | `test_..._explicit_chunk_id_path` + `test_chunk_id_explicit_path_exit_0` |
| R9 | resize margin single-mode만, compare overlay, close→clear | `syncPaneMargin` = single+open만 margin, else clear (JS inline gating) | `test_compare_mode_does_not_squeeze_pane` + `test_close_then_reopen_round_trips_margin` |
| R10 | Codex 6 테스트 전부 | 22 테스트(위) | 전부 green |

## 5-C. New code-path lock (CLAUDE.md RE-CODE 가드 — 신규 함수/state 명시 잠금)
| 신규 코드 경로 | 잠금 테스트 (grep 가능) |
| -------------- | ---------------------- |
| `retranslate_short` (재번역 + cache_key=NULL write) | `test_short_retranslate_writes_null_cache_key_no_poison`, `..._dry_run_writes_nothing`, `..._explicit_chunk_id_path` |
| `select_short_retranslate` (선택 필터) | `test_select_short_retranslate_includes_where_excludes_others`, `..._duplicate_where_not_excluded` |
| `_translate_with_context` (placeholder 왕복 + raise) | `test_short_retranslate_malformed_llm_preserves_existing` |
| `is_reference_number` / `is_math_dense` / `_neighbor_context` | 동명 3 단위 테스트 |
| CLI `--short-only/--chunk-id/--dry-run` 분기 + exit code | `test_short_retranslate_cli`(dry-run/apply/chunk-id/exit2/exit4) |
| `resize.js` clampWidth/applyChatWidth/syncPaneMargin/initResize | `test_resize_js`(8) — clamp/session/margin/compare/close-reopen/restore/default/drag |
| chat.js·reflow.js wiring (initResize 호출 + toggle/radio→syncPaneMargin) | 기존 36 JS 테스트 회귀 green + syncPaneMargin 양모드 단위 |

회귀 가드: 기존 chat.js/reflow.js import resize.js 추가 → `test_chat_ui_js`/`test_reflow_*_js`/`test_viewer_history_thread_js` **36 passed** (no regression).

## 5-D. Scoring (100, self-assessment)
| Item | Score / Max | Evidence |
| ---- | ----------- | -------- |
| 독창성 | 13 / 15 | 이웃-context 재번역이 content-cache를 우회(cache_key=NULL)해 poisoning 없이 문맥 교정. all-type 라벨 이웃. JS-inline margin gating으로 compare 그리드 보존 |
| 완결성 | 33 / 35 | R1–R10 전부 구현+테스트, live where→여기서 실증, CLI 4 flag, 22 신규 테스트. (−2: reflow.js radio→syncPaneMargin wiring은 end-to-end jsdom 미검증, syncPaneMargin 로직만 양모드 단위 검증) |
| 안정성 | 28 / 30 | fail-preserve(placeholder/empty), dry-run no-write, 1.x 무손상(0004/49850/2.0 tables NONE), 758 green, ruff/mypy clean. (−2: 자동 selector는 math 제외라 placeholder-loss 경로는 --chunk-id로만 도달 — 설계상, 테스트됨) |
| 확장성 | 18 / 20 | `--chunk-id`/`--max-chars`로 8e 7-doc 분포 재검토 대비, retranslate_short는 doc-범용. (−2: math-dense 판정은 8e math 강건화에 의존) |
| **Total** | **92 / 100** | |

## 5-E. Self verdict
- [x] **PASS_CANDIDATE** → Stage 5-B cross-verify(Codex Round 1). 코드 3 commit 후 작성, git status clean, 모든 값 실측. self 92(8d-2a/2b 동급 evidence 수준).
- [ ] FAIL → RE-CODE
- [ ] FAIL → RE-PLAN

### 알려진 gap (cross-verify 선공개)
1. reflow.js의 mode-radio → `syncPaneMargin` wiring은 단위 함수(syncPaneMargin, 양모드)로만 검증; reflow.js auto-init side-effect 때문에 end-to-end jsdom 미작성.
2. 자동 selector가 math 제외 → `_translate_with_context`의 placeholder-loss 분기는 `--chunk-id` 경로로만 도달(테스트는 chunk_ids로 강제).
3. `(A.1)-(A.3)` 같은 범위형 참조는 단일 regex 미커버(단일 `(A.1)`은 커버). 8e 7-doc서 분포 재검토.
