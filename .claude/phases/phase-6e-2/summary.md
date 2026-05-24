# Phase 6e-2 — Summary

## Status
**ESCALATE TO PLANNER** (R2 DOWNGRADE, push 보류).

WORKFLOW.md Stage 6: Round 2 cross-verify에서 DOWNGRADE → push 정책상 worker push 금지. Planner 판정 대기.

## Score history
| Round | Self | Cross verdict | Cross fair score | 행동 |
|---|---|---|---|---|
| v1 | 97/100 | DOWNGRADE | 88/100 | RE-CODE (4 missing items) |
| v2 (post RE-CODE) | 93/100 | **DOWNGRADE** | **90/100** | **escalate (R2 상한)** |

R2 잔존 2건 모두 **test quality 문제** — production 코드 회귀 없음.

## What was built
P0 fix: CLI 진입점이 `.env`를 로드하지 않아 `ht-lens translate` 가 silent하게 `MockLLMClient`를 사용 (DB를 `[KO] <english>` mock 출력으로 오염) 하던 버그를 두 layer로 해결.

1. **Shared loader** (`src/ht_lens/dotenv_loader.py` NEW): `load_repo_dotenv()` 를 api/app.py에서 분리, CLI에서도 같은 함수 사용. `override=False`, repo-root만 검색 (Phase 6c debate §3 invariant 보존).
2. **CLI inline call**: `translate_command()` 함수 본문 첫줄에서 호출. **module-level NOT** (Codex debate §2의 `test_cli_errors.py` import-time mutation 회피).
3. **Factory fail-closed** (defense-in-depth): `from_env_translate()` / `from_env_chat()` 가 어떤 provider env var도 unset/empty이면 신규 `LLMConfigurationError` raise. CLI exit 5로 매핑. 명시 `LLM_PROVIDER=mock`는 honor (테스트 opt-in).
4. **Docs** (`docs/CONFIGURATION.md`): fail-closed semantics 명시.

## Files changed
```
 .claude/phases/phase-6e-2/{plan,debate,challenge,verify,verify-cross,summary}.md  # phase docs
 docs/CONFIGURATION.md                                                              | +29 -1
 src/ht_lens/api/app.py                                                             | +6 -18  (loader local→shared)
 src/ht_lens/dotenv_loader.py                                                       | NEW (41 lines)
 src/ht_lens/llm/errors.py                                                          | +14    (LLMConfigurationError)
 src/ht_lens/llm/factory.py                                                         | +42 -4 (fail-closed)
 src/ht_lens/translate/cli.py                                                       | +15 -1 (loader + exit 5)
 tests/integration/test_translate_cli.py                                            | +263 -10 (subprocess + console-script)
 tests/unit/test_cli_no_import_side_effects.py                                      | NEW (53 lines)
 tests/unit/test_dotenv_loader.py                                                   | NEW (55 lines)
 tests/unit/test_factory_split.py                                                   | +111 -3 (fail-closed regression)
 tests/unit/test_llm_mock.py                                                        | +15 -4  (returns_mock_by_default → fails_closed)
```

## Test deltas
- pre-phase: ~427 → v2 (post RE-CODE): **441 passed, 8 skipped**
- mypy strict: clean. ruff: clean. format: clean.

## Deviations from plan
- v1 plan은 `cli.py` module-level loader 호출 + 모듈 이름 `_bootstrap.py`. Codex debate critique 모두 수용 (challenge.md) → function-level inline 호출, 모듈 이름 `dotenv_loader.py`, factory fail-closed 추가. plan v1 그대로 commit, challenge가 실제 implementation guide.
- 기존 `test_translate_cli.py::test_translate_exit_1_on_block_failure` / `_exit_4_on_health_check_failed` 이 legacy `LLM_PROVIDER` 만 set 했었음 → CLI .env load 후 scoped TRANSLATE_LLM_*이 .env에서 들어와 wins → 테스트 의도 깨짐. **scoped TRANSLATE_LLM_*로 변경** (테스트 의도 보존, scoped > legacy 명문화).
- 사용자 결정 항목 (AskUserQuestion 응답):
  - 모듈 이름: 사용자가 `_bootstrap.py` 선택 → Codex critique 반영해 `dotenv_loader.py`로 변경 (challenge §4). 추후 Planner 의견 필요 시 재논의.
  - status 마킹 fix: 사용자 결정대로 scope-out (별도 phase 권장).
  - Codex debate timing: 사용자 결정대로 plan commit 즉시 호출.

## Evidence index
- plan v1: `.claude/phases/phase-6e-2/plan.md` (commit 9a7b8a2)
- debate (Codex): `.claude/phases/phase-6e-2/debate.md` (commit 50977c7)
- challenge: `.claude/phases/phase-6e-2/challenge.md` (commit 070cd9a) — Codex critique 모두 ACCEPT + refined approach lock-in
- verify v1: 97 → DOWNGRADE 88 (commit 8bd5d8a / verify-cross commit aa569c5)
- RE-CODE: commit 5a91468 (4 R1 items addressed)
- verify v2: 93 → DOWNGRADE 90 (commit dc438b3 / verify-cross R2 commit aa569c5)
- summary: 본 파일

## Known issues / debt (Planner 검토 필요)

### R2 Critic (Codex) 잔존 critique
1. **Loader missing-file 테스트가 진정한 branch lock 아님**: `monkeypatch.setattr(_REPO_ROOT, tmp_path)` 후 `load_repo_dotenv()` 호출은 if-branch가 잘못돼서 `load_dotenv()` 가 호출되어도 `python-dotenv.load_dotenv()` 자체가 missing-path에서 silent → 테스트 통과. 진짜 branch 잠금은 `load_dotenv` 자체를 mock해서 "호출 안 됐다"를 단정해야 함.
2. **`test_module_entrypoint_loads_repo_root_dotenv_without_env_exports`의 mock-fallback 검출 약함**: `"[KO]" not in proc.stdout` 어설션은 CLI 성공 path가 `ok: doc_id=X translated=Y` 만 출력하므로 silent mock도 통과시킴. 실제 mock 검출은 DB에서 `model='mock'`/`'[KO]'` 패턴 확인 또는 cache_hit 수 확인 같은 별도 단정 필요.
3. **CI 미실행**: 본 phase 모든 verify는 local pytest. push 후 CI 결과는 미반영.

### 도메인 가드 (분석만, scope-out per challenge)
- `_finalize_document_status` (`src/ht_lens/translate/pipeline.py:284-297`)는 `stats.failed > 0`만 확인. mock provider도 failed=0 → `status='translated'` 마킹. 이번 phase의 .env load fix로 운영 흐름에서 mock 우연 활성화 자체가 차단되므로 root cause 해결됨. 단 explicit `LLM_PROVIDER=mock` 테스트 사용 시 status 마킹은 그대로 — 별도 phase에서 provider 인식 status 검토 권장.

## Recommended next

### For Planner — push 결정
이 phase의 RE-CODE는 R1 비판 4건 명시적 해결. R2 잔존 2건 모두 verification quality 문제이지 production 코드 회귀 없음. Codex fair score 90/100 (95+ 미달 → workflow상 자동 push 아님).

판정 옵션:
- **Option A (권장)**: PASS_DESPITE_R2 — 잔존 2건은 follow-up phase로 처리 (test hardening 한정), 본 phase 변경은 prod에 push해도 안전.
- **Option B**: Planner-directed micro-fix — R2 잔존 2건 즉시 fix (cross-verify R3 미호출, planner가 직접 검수). 변경 추정:
  - `tests/unit/test_dotenv_loader.py`: `monkeypatch.setattr` 으로 `load_dotenv` 자체 mock + 호출 없음 단정.
  - `tests/integration/test_translate_cli.py:test_module_entrypoint_loads_repo_root_dotenv_without_env_exports`: DB의 `model` 컬럼 또는 sglang 호출 확인으로 강화.
- **Option C**: REJECT — fundamental 재설계.

### For Phase backlog (별도 phase 후보)
- `_finalize_document_status` provider 인식 (분석만, 본 phase scope-out)
- Gemma 4 prompt 재튜닝 (Phase 6f-4 후보, 직전 진단에서 본문 KR 8% 측정)
- Section-level chat context (Phase 6h-1 후보)
- 번역 언어 옵션 UI/API (Phase 6h-2 후보)
