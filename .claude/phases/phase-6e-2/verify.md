# Phase 6e-2 — Verify (self) — v2 (post RE-CODE)

`git status` clean (Phase 6e-2 영역 기준). 미커밋된 `ROADMAP.md`는 사용자 작업, `.env.backup.20260523_181759`은 Phase 6f-1 아티팩트 — 본 phase와 무관.

**v2 history**: v1 self-score 97/100 → cross-verify R1 DOWNGRADE 88/100 → RE-CODE (4 missing items) → 본 v2 재측정.

## 5-A. Automated checks
| Check | Command | Result |
| ----- | ------- | ------ |
| Lint | `uv run ruff check src/ tests/` | `All checks passed!` |
| Format | `uv run ruff format --check src/ tests/` | `122 files already formatted` |
| Type | `uv run mypy src/` | `Success: no issues found in 60 source files` |
| Test | `uv run pytest tests/ --no-cov -q` | `441 passed, 8 skipped` (8 skip 내역: 6건 live LLM env 미설정, 1건 `test_module_entrypoint_fails_closed_when_dotenv_absent` repo .env 있으면 skip — Phase 6e-2 직접 관련. 단 동등 케이스를 새 `test_module_entrypoint_exit_5_when_no_provider_and_no_dotenv`가 실측 cover. 1건 `test_dotenv_override_false_preserves_explicit_shell_export`는 .env 없을 때 skip — Phase 6c 기존 동작) |
| Coverage (changed src) | `uv run pytest <new tests> --cov=...` | `llm/errors.py 100% / llm/factory.py 95% (uncovered: 135-137 mock_fail import branch, 142 build_client misc — Phase 6e-2 신규 경로 아님) / dotenv_loader.py 100% (3 unit tests cover both branches)` |
| CI | (push 후 검증 예정) | — (R1 비판 인정 — push 후 결과 본 보고서에 추후 추가) |

## 5-B. Functional checks (RE-CODE 후 재실행)

### B-1. Repo `.env` 자동 load via `python -m ht_lens.translate` (env-cleared subprocess)
```
$ env -i bash -c 'export PATH=/usr/bin:/bin:/usr/local/bin; cd /home/hyunlord/github/ht_lens; .venv/bin/python -m ht_lens.translate --doc-id 4 --dry-run'
dry_run: doc_id=4 total=401 cache_hits=401 estimated_llm_calls=0
```
cache_hits=401은 model name이 `gemma-4-26b-a4b-it`로 정확히 resolve된 증거 (cache_key = `(text, src, tgt, model_name)`).

### B-2. Fail-closed via CLI subprocess (end-to-end exit 5 — R1 §4 #3 보강)
새 단위 테스트 `test_module_entrypoint_exit_5_when_no_provider_and_no_dotenv` (tests/integration/test_translate_cli.py:317-372)이 다음을 subprocess로 실행:
- LLM env 모두 clear
- `ht_lens.dotenv_loader._REPO_ROOT` 를 빈 tmp dir로 monkeypatch (subprocess 내부에서)
- `translate_command()` 호출
- 기대: exit code 5, stderr에 `LLM not configured` 또는 `No LLM provider configured`

실측: PASSED. R1 §2 (B-1/B-2가 factory level만 cover) + §4 #3 (exit-5 path end-to-end 미검증) 모두 해결.

### B-3. `ht-lens` 콘솔 스크립트 (installed launcher — R1 §2/§4 #2 보강)
- `test_ht_lens_console_script_translate_exit_0_with_explicit_mock` (PASSED): `.venv/bin/ht-lens translate --doc-id N`이 explicit `TRANSLATE_LLM_PROVIDER=mock`로 exit 0.
- `test_ht_lens_console_script_translate_exit_5_without_provider` (PASSED): 같은 launcher가 provider env 없으면 exit 5 + 에러 메시지.

`challenge.md §1` 약속 (양쪽 launcher path lock-in) 완전 충족.

### B-4. Loader missing-file branch — R1 §4 #1 보강
`test_load_repo_dotenv_noop_when_file_missing` (tests/unit/test_dotenv_loader.py:28-50): `monkeypatch.setattr(loader_mod, "_REPO_ROOT", tmp_path)` 로 진짜 .env 없는 디렉토리를 가리키게 함. `tmp_path` 가 fresh이므로 `.env` 미존재 보장. branch 실제 진입 + 부작용 없음 검증. v1의 "그냥 호출만" 케이스 (실제 branch 미진입 가능) 대체.

### B-5. docs drift — R1 §4 #4 보강
`docs/CONFIGURATION.md:48-83`에 fail-closed 동작 명시. provider 줄에 "no built-in default" 추가, `LLMConfigurationError` raise + exit code 5 명시, 의도적 mock 사용 시 explicit export 안내, Phase 6e-2 산출물 링크.

### B-6. Regression check (RE-CODE 신규 코드 경로 잠금 — CLAUDE.md 가드)
| RE-CODE 도입 새 코드 경로 | 잠금 테스트 (grep 검증) |
|---|---|
| `dotenv_loader._REPO_ROOT` runtime resolution | `tests/unit/test_dotenv_loader.py` (`monkeypatch.setattr(loader_mod, "_REPO_ROOT", tmp_path)`) |
| `tests/integration/test_translate_cli.py` subprocess + sitecustomize injection 패턴 | 신규 2건 (console-script exit 0/5) 모두 PASS |
| docs/CONFIGURATION.md fail-closed 섹션 | 텍스트 — 직접 grep으로 명문화: `grep -c "fail-closed\|fails closed" docs/CONFIGURATION.md` → 2건 |

`grep` 검증:
```
$ grep -l "LLMConfigurationError\|load_repo_dotenv\|_REPO_ROOT" tests/ src/
src/ht_lens/dotenv_loader.py
src/ht_lens/api/app.py
src/ht_lens/llm/factory.py
src/ht_lens/llm/errors.py
src/ht_lens/translate/cli.py
tests/integration/test_translate_cli.py
tests/unit/test_dotenv_loader.py
tests/unit/test_factory_split.py
tests/unit/test_llm_mock.py
tests/unit/test_cli_no_import_side_effects.py
```
→ 모든 신규 / 변경 경로가 src + test 양쪽에 grep 가능.

## 5-C. Scoring (100, self-assessment — R1 비판 반영)
| Item | Score / Max | R1 → v2 | Evidence |
| ---- | ----------- | ------- | -------- |
| 독창성 | 14 / 15 | 14 → 14 | R1 confirm. 변경 없음. |
| 완결성 | 32 / 35 | 29 → 32 | R1 비판 4건 모두 RE-CODE로 해결: missing-file branch genuine test (§4 #1), end-to-end exit-5 test (§4 #3), 양쪽 launcher path (§4 #2), docs drift (§4 #4). 미세 감점 잔존: CI는 여전히 push 후 결과 필요 (현 보고서에 미반영). |
| 안정성 | 28 / 30 | 26 → 28 | R1 비판 2건 해결: ① loader missing-file branch 진짜 테스트, ② exit-5 CLI path end-to-end 실증. coverage 측정 추가. 미세 감점: `factory.py`의 mock_fail import branch와 build_client 일부 (uncovered lines 135-137, 142)는 Phase 6e-2 직접 도입 아님이지만 자체 측정 안 함. |
| 확장성 | 19 / 20 | 19 → 19 | R1 confirm + docs drift fix로 운영자 안내 일관성 확보. 향후 N개 scope 추가 시 `_resolve_provider`가 scope-specific signature라는 점은 잔존 한계. |
| **Total** | **93 / 100** | 88 → 93 | |

R1 fair score 88 → v2 self-score 93 (모든 R1 비판 명시적 해결). R2 cross-verify에서 새 missing item 발견 시 추가 RE-CODE 또는 Planner escalate.

## 5-D. Self verdict
- [x] PASS_CANDIDATE (≥90, R1 reflection 후 보수적)
- [ ] FAIL → RE-CODE
- [ ] FAIL → RE-PLAN

근거: 모든 자동 검사 green, R1 비판 4건 명시적 RE-CODE 반영 + grep 검증, RE-CODE 신규 코드 경로 모두 단위 테스트 잠금. v1 자기점수 인플레이션 (97→88) 인정한 후 v2는 보수적 93. R2 cross-verify 결과 대기.
