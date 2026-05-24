# Phase 6e-2 — Challenge

## Debate responses

### 1. Over-engineering (Codex)
> The `_bootstrap.py` extraction plus module-level side effect in `src/ht_lens/cli.py` is broader than the bug. The failure happens where `src/ht_lens/translate/cli.py:50-56` constructs the LLM.

**ACCEPT (큰 폭 수정).** Codex가 정확.
- Plan v1은 `src/ht_lens/cli.py`에 module-level `load_repo_dotenv()` 추가를 가정 → `extract`, `ingest`, `serve --help`, 그리고 `tests/integration/test_cli_errors.py:10`의 `from ht_lens.cli import main`까지 모두 의도하지 않은 env 변경 트리거.
- **Revised approach**: loader 호출을 **LLM-construction site 내부에 인라인**. 즉 `translate/cli.py:translate_command()` 함수 본문 첫줄에서 호출 (typer subcommand가 실제로 invoke될 때만). `cli.py` module은 변경 0.
- `ht-lens translate` 도 `cli.py:32`에서 `from ht_lens.translate.cli import translate_command`로 같은 함수를 import → 같은 inline 호출이 양쪽 entry path 모두 cover.

> The “status analysis” item is scope creep.

**ACCEPT.** plan v1 §5 "status 분석" 섹션은 본 phase에서 제거하고, 별도 follow-up note만 summary.md에 남김 (실제 수정 0).

### 2. Hidden assumptions (Codex)
> The plan assumes `ht-lens translate` is the only affected entry point. That is false. `python -m ht_lens.translate` goes through `src/ht_lens/translate/__main__.py` and `src/ht_lens/translate/cli.py`, completely bypassing `src/ht_lens/cli.py`.

**ACCEPT.** 위 §1 revised approach가 이 문제도 해결 — `translate_command()` 내부 호출은 두 entry 모두 cover.

> It assumes `_isolate_llm_env` in `tests/conftest.py:24-49` makes module-level dotenv loading safe. It does not.

**ACCEPT.** `tests/integration/test_cli_errors.py:10`의 module-level `from ht_lens.cli import main` 확인됨. autouse fixture는 test 시작 시 snapshot — collection-time mutation은 snapshot에 이미 들어와 leak. Function-internal 호출로 회피.

> It assumes auto-loading `.env` is enough to satisfy "Silent mock 방지" DoD. It is not. `from_env_translate()` still defaults to `"mock"` in `src/ht_lens/llm/factory.py:136-158`. Missing `.env`, incomplete `.env`, bad repo-root detection, or installed-package execution outside a repo checkout will still silently select mock.

**ACCEPT — scope 확장.** .env load 만으로는 부족. 본 phase에 **fail-closed 변경** 추가:
- `from_env_translate()`/`from_env_chat()`이 mock으로 fall through하는 경우 = `os.environ`에 어떤 provider env var (`TRANSLATE_LLM_PROVIDER`, `CHAT_LLM_PROVIDER`, `LLM_PROVIDER`)도 없는 상태.
- 이 경우 **`LLMConfigurationError`** (새 exception) raise. 테스트가 mock을 의도하면 `LLM_PROVIDER=mock` 명시 export하면 OK (기존 동작).
- 즉, "implicit mock"만 차단. "explicit mock"는 보존.

> `override=False` only holds for the same key. Because `from_env_translate()` prefers `TRANSLATE_LLM_*` over `LLM_*`, a repo `.env` with scoped vars can still beat a shell or test that only exports `LLM_PROVIDER=mock`.

**ACCEPT 분석, 동작 변경 없음.** 이는 정상 design intent: scoped vars > legacy vars. `tests/conftest.py:_isolate_llm_env`가 scoped + legacy 둘 다 snapshot에 포함하므로 테스트가 정확히 어떤 var를 set 하느냐 결정 가능. 새 unit test로 의도를 명문화.

### 3. Edge cases (Codex)
> `python -m ht_lens.translate --doc-id ...` remains broken unless `src/ht_lens/translate/cli.py` or `src/ht_lens/translate/__main__.py` is changed.

**RESOLVED by §1 revised.**

> `python -m ht_lens.extract` and direct `from ht_lens.cli import main` imports will now load `.env` even though they never build an LLM.

**RESOLVED by §1 revised** — cli.py 변경 0이므로 `from ht_lens.cli import main`은 env 변경 안 함. `extract`/`ingest` typer commands도 LLM 구성 안 함 → loader 호출 안 함.

> A checkout without `.env` is common in CI and on fresh machines. The plan's smoke command uses `--dry-run`, but `src/ht_lens/translate/cli.py:57-61` skips `health_check()` in dry-run mode.

**ACCEPT.** Smoke를 **non-dry-run** subprocess test로 교체. 정상 .env 없는 환경에서 fail-closed → exit code (`LLMConfigurationError`) 검증. dry-run이 health_check skip 한다는 사실은 추가 회귀로 명문화.

> Empty or partial shell exports are not addressed.

**ACCEPT 분석, 부분 처리.** `LLM_PROVIDER=""` 빈 값의 경우 `_resolve()` 의 기존 `or "mock"` 가 mock fall-back. fail-closed 변경에서 "no key in os.environ at all"과 "key present but empty/whitespace"를 둘 다 mock fallback 조건으로 처리. 단 사용자가 의도적으로 `LLM_PROVIDER=` (empty)를 export하는 케이스는 흔치 않음 — empty도 unset과 동일 처리.

### 4. Alternative approaches (Codex)
> The minimal fix is to call the shared loader only at the actual LLM-construction sites.

**ACCEPT (1차 추천 적용).**

> The stronger P0 fix is fail-closed behavior in `translate_command()`.

**ACCEPT (defense-in-depth 같이 적용).** Codex가 두 가지를 alternative로 제시했지만 본 phase는 **둘 다** 적용. Cli loader 호출 (minimal) + factory fail-closed (stronger). 두 layer 가 독립적으로 silent mock을 차단.

> `_bootstrap.py` is the wrong name. Use something explicit like `env.py` or `dotenv_loader.py`.

**ACCEPT.** `src/ht_lens/dotenv_loader.py`로 변경. 사용자가 plan 승인 시 `_bootstrap.py`를 선택했지만 Codex 비판에 따라 challenge에서 재조정 (`_bootstrap`는 dotenv 외 다른 용도가 들어올 위험 — naming 명확성 우선).

### 5. Missing tests (Codex)
**모두 ACCEPT.** 다음 신규 테스트 항목 (모두 challenge에 lock-in):

1. `tests/integration/test_translate_cli.py::test_module_entrypoint_loads_repo_root_dotenv_without_env_exports`
   - subprocess: `python -m ht_lens.translate --doc-id <X>`
   - env: `LLM_*` / `TRANSLATE_LLM_*` 모두 unset
   - repo `.env` → unreachable openai_compat endpoint
   - expected: exit 4 (`LLMHealthCheckFailed`), NOT mock success
2. `tests/integration/test_translate_cli.py::test_ht_lens_translate_subcommand_loads_repo_root_dotenv_without_env_exports`
   - 같은 시나리오로 installed `ht-lens translate` (subprocess: `python -m ht_lens translate --doc-id ...` 또는 `ht-lens` entry script가 가용하면 그쪽).
3. `tests/unit/test_cli_no_import_side_effects.py` (NEW)
   - `import ht_lens.cli`가 `LLM_*`/`TRANSLATE_LLM_*`/`CHAT_LLM_*` 환경변수를 mutate하지 않는지 (snapshot before/after).
4. `tests/unit/test_factory_split.py` 추가
   - `from_env_translate()`: 모든 provider env var unset → `LLMConfigurationError` raise.
   - 명시 `LLM_PROVIDER=mock` export 시 → MockLLMClient 정상.
   - `TRANSLATE_LLM_PROVIDER=openai_compat`만 set + shell `LLM_PROVIDER=mock` export → scoped vars win (현 동작 명문화).
   - `TRANSLATE_LLM_PROVIDER=""` (empty) → fail-closed.
5. `tests/unit/test_dotenv_loader.py` (NEW)
   - `load_repo_dotenv()`: repo-root에서만 검색 (CWD 무시).
   - file 없으면 raise 없음, no-op.
   - `override=False` 보존 (shell export 우선).

## Plan revisions (after debate)

### Revised file changes
| Path | Action | Note |
| ---- | ------ | ---- |
| `src/ht_lens/dotenv_loader.py` | NEW | `load_repo_dotenv()` 공유. 이름은 `dotenv_loader` (Codex §4). |
| `src/ht_lens/api/app.py` | MODIFY | local `_load_repo_dotenv()` 제거, `dotenv_loader.load_repo_dotenv` import + 호출. backward-compat: `_load_repo_dotenv = load_repo_dotenv` alias 유지 (test_dotenv_load.py:64가 직접 import). |
| `src/ht_lens/translate/cli.py` | MODIFY | `translate_command()` 함수 본문 첫줄에 `load_repo_dotenv()` 호출 (function-level, NOT module-level). |
| `src/ht_lens/llm/factory.py` | MODIFY | `from_env_translate()` + `from_env_chat()` fail-closed: 모든 provider env var unset/empty → `LLMConfigurationError` raise. 신규 exception. |
| `src/ht_lens/llm/errors.py` | MODIFY | `LLMConfigurationError(LLMError)` 추가. exit code 매핑은 typer가 `Exception` 일반 path로 처리 (exit 1) 또는 별도 mapping. |
| `src/ht_lens/cli.py` | (변경 없음) | Codex §1 — module-level mutation 회피. |
| `tests/integration/test_translate_cli.py` | EXTEND | 2개 신규 test (Codex §5 #1, #2). |
| `tests/unit/test_cli_no_import_side_effects.py` | NEW | env mutation 회귀 (Codex §5 #3). |
| `tests/unit/test_factory_split.py` | EXTEND | fail-closed + scoped/legacy precedence (Codex §5 #4). |
| `tests/unit/test_dotenv_loader.py` | NEW | loader 자체 (Codex §5 #5). |

### LLMConfigurationError exit code
Typer에서 `LLMConfigurationError`를 capture해 exit 5 (새 코드)로 매핑. `translate_command()`의 기존 except 체인에 `LLMConfigurationError` 추가:
```python
except LLMConfigurationError as exc:
    typer.echo(f"error: LLM configuration missing: {exc}", err=True)
    raise typer.Exit(code=5) from exc
```

### Smoke test 변경 (debate §3)
plan v1의 `--dry-run` smoke 폐지. 대신 subprocess integration test로 lock-in (Codex §5 #1).

## DoD checklist
| DoD item | Status | Evidence |
| -------- | ------ | -------- |
| CLI `.env` 자동 load (`ht-lens translate`) | planned | unit + integration test |
| CLI `.env` 자동 load (`python -m ht_lens.translate`) | planned | integration subprocess test |
| Silent mock fallback 차단 (.env 없을 때) | planned | factory fail-closed + integration test |
| `cli.py` import 시 env mutation 없음 | planned | unit test (regression) |
| 기존 `test_translate_pipeline_mock.py` 정상 동작 | planned | autouse fixture가 explicit `LLM_PROVIDER=mock` set → factory 정상 작동 |
| `override=False` 보존 | planned | unit test (precedence lock-in) |
| 회귀 0 | planned | full pytest + mypy strict + ruff |

## Risk register
| Risk | Likelihood | Impact | Mitigation |
| ---- | ---------- | ------ | ---------- |
| `_load_repo_dotenv` alias 누락으로 test_dotenv_load.py:64 break | Low | Low | alias 유지 + test 한 번 수동 재실행 |
| `LLMConfigurationError` raise가 기존 integration test (mock pinned) 깨뜨림 | Low | Mid | 기존 fixture가 explicit `LLM_PROVIDER=mock` set 사용 — fail-closed 검사가 통과. autouse fixture가 set 안 하면 fix 필요 |
| Function-internal loader 호출이 매 invocation마다 disk I/O | Negligible | Negligible | `Path.is_file()` 후 load — cold start 한 번. CLI는 무관 (단일 호출) |
| `LLMConfigurationError`가 Phase 6f-1 prod에 영향 (현 .env는 set 되어 있음) | Negligible | Negligible | 현 prod .env에는 모든 var 명시 → 영향 0 |
| Empty value (`LLM_PROVIDER=""`) edge case의 의도 모호 | Low | Low | unit test로 "empty == unset" 명문화 |

## Decision
- [x] PASS → proceed to code
- [ ] RE-PLAN

PASS 근거: Codex의 모든 비판 수용 + 구체적 file/exception/test 계획으로 변경. plan.md는 v1 그대로 두고 이 challenge.md가 실제 implementation 가이드 — 합치된 산출물. 코딩 진행.
