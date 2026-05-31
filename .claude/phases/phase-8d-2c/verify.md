# Phase 8d-2c — Verify v2 (self, post verify-cross R1 RE-CODE)

neighbor-context 짧은-chunk 재번역(cache 우회 + cache_key=NULL) + 채팅 drawer resize(single-mode 본문 margin 연동). 8d 시리즈 마지막.

**v2 사유**: cross-verify R1(Codex DOWNGRADE 86)이 CLI 안전 갭 2개(real defect) + 테스트 명칭 overclaim 1개를 지적 → RE-CODE(`8771386`) → verify 재작성. 모든 값은 RE-CODE commit 이후 실측, git status clean(코드 drift 없음; untracked=summary.md 템플릿 + scheduled_tasks.lock 뿐).

## 5-A. Automated checks (RE-CODE 이후 재실행)
| Check    | Command | Result |
| -------- | ------- | ------ |
| Lint     | `uv run ruff check .` | **All checks passed!** |
| Format   | `uv run ruff format --check .` | **197 files already formatted** |
| Type     | `uv run mypy src/` | **Success: no issues found in 84 source files** |
| Test     | `uv run pytest -m "not llm and not slow"` | **761 passed, 1 skipped, 8 deselected** (554.28s) |
| New tests | `pytest test_short_retranslate{,_cli} test_resize_js` | **10 + 7 + 8 = 25 passed** |
| Coverage | `--cov` (자동) | short_retranslate.py **97%** (미달=헬퍼 2 분기) |
| CI       | GitHub Actions | **N/A** — CI는 main/PR만(`prototype-reflow` 트리거 없음). local fast suite가 CI-equivalent. push 후 PR 시 확정. |

- 761 = verify v1 시점 758 + RE-CODE 신규 3(unit unknown-id raises, CLI dry-run-misuse exit 2, CLI unknown chunk-id exit 2). deselect 8 / skip 1 모두 기존(@llm cross-lingual + jsdom-CI provisioning debt).

## 5-B. verify-cross R1 resolution (Codex DOWNGRADE 86 → 처리)
| R1 지적 | 판정 | 처리 (commit `8771386`) | lock |
| ------- | ---- | ---------------------- | ---- |
| **A. `--dry-run` without `--short-only`/`--chunk-id` → 정상 path로 fall-through하여 WRITE** | **real defect** | `_run()` 최상단 guard: `dry_run and not (short_only or chunk_id)` → `ValueError`(exit 2, LLM health 전 fail-fast). 정상 translate_chunks는 dry-run 없음 | `test_dry_run_without_short_or_chunk_id_exit_2_no_write`(exit 2 + seed row 불변) |
| **B. 존재하지 않는 `--chunk-id` → silent candidates=0 exit 0** | **real defect** | `retranslate_short`: `missing = chunk_ids - {c.id}` → `ValueError`(exit 2). manual repair 경로 typo가 success로 안 보임 | `test_short_retranslate_unknown_chunk_id_raises`(unit) + `test_chunk_id_unknown_exit_2`(CLI) |
| **C. "malformed" 테스트가 challenge의 delimiter-free prose 미커버** | **valid(명칭)** | R3 target-only 설계는 추출 로직을 제거 → echo할 이웃·malform할 delimiter 자체가 없음. 테스트를 `..._empty_or_lost_placeholder_preserves_existing`로 rename + docstring에 설계 근거 명시. placeholder 살아있는 비어있지-않은 출력은 번역으로 신뢰(LLM 설명문 판별=fragile heuristic, 8e) | `test_short_retranslate_empty_or_lost_placeholder_preserves_existing` |
| 라이브 evidence가 dev DB mutate, fixture 비재현 | 동의(보조) | durable evidence=25 테스트. where→여기서는 실 qwen 보조 demo(mock는 한국어 connective 미검증) | (테스트가 1차 evidence) |
| CI N/A | 동의(disclosed) | 브랜치 트리거 없음; local 761 green = CI-equivalent | — |

## 5-C. Regression check (CLAUDE.md RE-CODE 가드 — 새 코드 경로 명시 잠금)
RE-CODE는 **새 분기 2개**(guard, missing-id) 도입 → 둘 다 단위/subprocess 테스트로 grep-가능 잠금. 회귀 0.

| RE-CODE 새 코드 경로 | 잠금 테스트 (grep) | 기존 contract 무손상 |
| -------------------- | ----------------- | ------------------- |
| cli.py `if dry_run and not (short_only or chunk_id): raise ValueError` | `test_dry_run_without_short_or_chunk_id_exit_2_no_write` | 기존 `translate-chunks --doc-id X`(dry_run=False)는 guard 통과 → 정상 path 불변. `translate-chunks --dry-run` 사용 기존 테스트 0건(grep 확인) |
| short_retranslate.py `missing = chunk_ids - {c.id for c in chunks}` → raise | `test_short_retranslate_unknown_chunk_id_raises`, `test_chunk_id_unknown_exit_2` | 유효 chunk_id 경로(`test_..._explicit_chunk_id_path`) 여전히 retranslated=1, cache_key NULL |
| 테스트 rename(코드 경로 변화 없음) | `test_short_retranslate_empty_or_lost_placeholder_preserves_existing` | empty + placeholder-loss fail-preserve 잠금 유지(이름만 정확화) |
| (R1 fix 영역 회귀) CLI exit code dispatch 1/2/4 | `test_short_retranslate_cli` 7개(dry-run/apply/chunk-id/exit2×2/exit4) | 1.x `translate` exit code(`test_translate_cli.py`)는 별 command(`ht_lens.translate`) → 무영향 |
| (resize 영역 회귀) chat.js/reflow.js import resize.js | 기존 36 JS 테스트(`test_chat_ui_js`/`test_reflow_*`/`test_viewer_history_thread_js`) green | initResize/syncPaneMargin은 .pane/.chat 부재·opaque-origin서 graceful no-op |

- 새 함수/필드 grep 증거: `grep -rn "unknown_chunk_id\|dry_run_without_short" tests/` → 두 테스트 존재. `git grep "raise ValueError" src/ht_lens/translate/short_retranslate.py` → missing-id guard 1.

## 5-D. Functional checks (불변, 재측정)

### live 재번역 demo (DoD: where→여기서) — 실 qwen, dev DB doc 1 (persisted)
```
$ python -m ht_lens.cli translate-chunks --doc-id 1 --short-only --dry-run --db data/ht_lens_v2.db
  chunk 2: '어디에' -> '여기서'
  chunk 35: '모델은 다음과 같습니다:' -> '모델은 다음과 같습니다:'
ok: doc_id=1 mode=dry-run candidates=2 retranslated=0 failed=0
$ python -m ht_lens.cli translate-chunks --doc-id 1 --short-only --db data/ht_lens_v2.db
ok: doc_id=1 mode=apply candidates=2 retranslated=2 failed=0
# 재측정(verify v2): DEV chunk 2 where -> '여기서' cache_key=NULL
```
- **id=2 `where`: `어디에`→`여기서`** = DoD 핵심. cache_key=NULL → content 캐시 비오염(R1) 실증. `(28.116/123/126)`=is_reference_number 제외.

### 1.x 무손상 (prod `data/ht_lens.db`, verify v2 재측정)
```
PROD ht_lens.db: alembic=0004 blocks=49850 chunk_tables=0
```
- migration 0건(translate/frontend만). dev·prod DB 모두 .gitignore → dev write가 git status에 안 보임(정상).

### challenge R1–R10 (전부 구현+테스트; R2/R8은 R1 fix로 강화)
R1 cache_key=NULL / R2 CLI 4-flag(+misuse guard) / R3 target-only fail-preserve / R4 no is_repeated / R5 ref regex(+appendix `A.1`) / R6 has_math+`\(`/`\[` / R7 all-type 이웃 / R8 `--chunk-id`(+unknown-id guard) / R9 single-mode margin·compare overlay / R10 25 테스트. (상세 표는 verify v1 이력 참조)

## 5-E. Scoring (100, self-assessment v2)
| Item | Score / Max | Evidence |
| ---- | ----------- | -------- |
| 독창성 | 13 / 15 | content-cache 우회(cache_key=NULL) 문맥 교정 + all-type 라벨 이웃 + JS-inline margin gating(compare 보존). (−2: scope=번역수리+resize 묶음) |
| 완결성 | 33 / 35 | R1–R10 + R1-fix A/B/C, live where→여기서, 25 테스트. (−2: reflow.js radio→syncPaneMargin은 함수 단위(양모드) 검증, e2e jsdom 미작성 — disclosed) |
| 안정성 | 29 / 30 | **A/B fail-fast(exit 2)** 추가로 dry-run footgun·silent no-op 제거 + 테스트. fail-preserve, dry-run no-write, 1.x 0004/49850/0, 761 green, ruff/mypy clean. (−1: 자동 selector math 제외로 placeholder-loss 분기는 --chunk-id로만 도달 — 설계, 테스트됨) |
| 확장성 | 18 / 20 | `--chunk-id`(이제 unknown-id 안전) + `--max-chars`로 8e 7-doc 분포 대비. (−2: math-dense 판정은 8e math 강건화 의존) |
| **Total** | **93 / 100** | v1 92 → R1 안전 갭 폐쇄로 안정성 +1 |

## 5-F. Self verdict
- [x] **PASS_CANDIDATE (93)** → Stage 5-B cross-verify Round 2 (마지막 라운드). RE-CODE 후 작성, git status clean, 전 값 실측. R1 real defect 2개 fix+lock, overclaim 1개 정정.
- [ ] FAIL → RE-CODE
- [ ] FAIL → RE-PLAN

### 잔여 gap (R2 선공개, functional 결함 아님)
1. reflow.js mode-radio → `syncPaneMargin` wiring: 함수 단위(syncPaneMargin 양모드) 검증; reflow.js auto-init side-effect로 e2e jsdom 미작성.
2. 자동 selector math 제외 → `_translate_with_context` placeholder-loss 분기는 `--chunk-id`로만 도달(테스트는 chunk_ids 강제).
3. `(A.1)-(A.3)` 범위형 참조 단일 regex 미커버(단일 `(A.1)`은 커버); 8e 7-doc 분포 재검토.
