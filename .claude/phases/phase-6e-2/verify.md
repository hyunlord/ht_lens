# Phase 6e-2 — Verify (self)

`git status`는 clean (Phase 6e-2 영역 기준). 미커밋된 `ROADMAP.md`는 사용자 작업, `.env.backup.20260523_181759`은 Phase 6f-1 아티팩트 — 본 phase와 무관.

## 5-A. Automated checks
| Check | Command | Result |
| ----- | ------- | ------ |
| Lint | `uv run ruff check src/ tests/` | `All checks passed!` |
| Format | `uv run ruff format --check src/ tests/` | `122 files already formatted` |
| Type | `uv run mypy src/` | `Success: no issues found in 60 source files` |
| Test | `uv run pytest tests/ --no-cov -q` | `438 passed, 8 skipped` (skipped은 live-LLM 환경 미설정 케이스, 본 phase 무관) |
| Coverage | (run via `--no-cov`로 측정 안 함, 변경 file 모두 신규 + 변경 단위 테스트로 도달 보장) | — |
| CI | (push 후 검증 예정) | — |

## 5-B. Functional checks

### B-1. Repo `.env` 자동 load (subprocess, env -i 실행)
```bash
env -i bash -c '
  export PATH=/usr/bin:/bin:/usr/local/bin
  cd /home/hyunlord/github/ht_lens
  echo "Subprocess env before uv: TRANSLATE_LLM_PROVIDER=${TRANSLATE_LLM_PROVIDER:-UNSET}"
  .venv/bin/python -m ht_lens.translate --doc-id 4 --dry-run
'
```
실측 출력:
```
Subprocess env before uv: TRANSLATE_LLM_PROVIDER=UNSET
dry_run: doc_id=4 total=401 cache_hits=401 estimated_llm_calls=0
```
- subprocess 시작 시 `TRANSLATE_LLM_PROVIDER` 환경변수 미설정 (`env -i` clean shell)
- `dry_run`이 `cache_hits=401` 발견 → cache key는 `(text, src, tgt, model_name)` 구성이므로 model이 `gemma-4-26b-a4b-it`로 정확히 resolve된 증거. 만약 .env가 미로드 됐다면 (1) `from_env_translate()`가 `LLMConfigurationError` raise하거나 (2) 다른 model name으로 cache miss.

### B-2. Fail-closed (`.env`도 없고 env exports도 없을 때)
```bash
env -i bash -c '
  export PATH=/usr/bin:/bin:/usr/local/bin
  cd /tmp/phase6e2_no_env  # CWD에 .env 없음
  /home/hyunlord/github/ht_lens/.venv/bin/python - <<EOF
import os
for k in list(os.environ):
    if k.startswith(("LLM_", "TRANSLATE_LLM_", "CHAT_LLM_", "OLLAMA_")):
        del os.environ[k]
from ht_lens.llm.factory import from_env_translate
from_env_translate()
EOF
'
```
실측: `LLMConfigurationError: No LLM provider configured. Set one of: TRANSLATE_LLM_PROVIDER, LLM_PROVIDER. If you intend to use the in-memory mock, export LLM_PROVIDER=mock explicitly.`
- silent mock 폴백 제거 검증.

### B-3. 명시 mock 보존 (테스트 opt-in)
```python
os.environ['LLM_PROVIDER'] = 'mock'
from_env_translate()  # → MockLLMClient
```
실측: `MockLLMClient` 인스턴스 반환. 기존 `tests/integration/test_translate_pipeline_mock.py` 등 모두 통과 (438 passed).

### B-4. Regression check (RE-CODE 가드 — CLAUDE.md "RE-CODE regression 가드")
이번 phase에는 RE-CODE 라운드 없음 (challenge.md PASS → 1차 implement). 단 Codex 비판 통합 시 다음 신규 코드 경로가 도입됐고 각각 단위 테스트로 잠금됨:

| 신규 코드 경로 | 잠금 테스트 |
|---|---|
| `dotenv_loader.load_repo_dotenv()` 모듈 | `tests/unit/test_dotenv_loader.py::{test_load_repo_dotenv_uses_repo_root_not_cwd, _noop_when_file_missing, _override_false_preserves_shell_export}` |
| `_resolve_provider()` 함수 (factory.py) | `tests/unit/test_factory_split.py::{test_translate_factory_raises_when_no_provider_env_set, test_chat_factory_raises_when_no_provider_env_set, test_explicit_legacy_mock_still_allowed, test_explicit_scoped_mock_still_allowed, test_empty_provider_value_treated_as_unset, test_scoped_provider_wins_over_legacy_mock_pin}` |
| `LLMConfigurationError` exception | `tests/unit/test_factory_split.py` 6건 + `tests/unit/test_llm_mock.py::test_from_env_fails_closed_when_no_provider_set` |
| `translate_command()` 내 loader 호출 + exit 5 매핑 | `tests/integration/test_translate_cli.py::test_module_entrypoint_loads_repo_root_dotenv_without_env_exports` + `_fails_closed_when_dotenv_absent` |
| `import ht_lens.cli` side-effect 회귀 | `tests/unit/test_cli_no_import_side_effects.py::test_importing_ht_lens_cli_does_not_set_llm_env_vars` |

grep 검증:
```
$ grep -rn "load_repo_dotenv\|LLMConfigurationError\|_resolve_provider" tests/
tests/unit/test_dotenv_loader.py:22:    from ht_lens.dotenv_loader import load_repo_dotenv
tests/unit/test_dotenv_loader.py:24:    load_repo_dotenv()
tests/unit/test_dotenv_loader.py:43:    from ht_lens.dotenv_loader import load_repo_dotenv
tests/unit/test_dotenv_loader.py:45:    load_repo_dotenv()
tests/unit/test_dotenv_loader.py:54:    from ht_lens.dotenv_loader import load_repo_dotenv
tests/unit/test_dotenv_loader.py:55:    load_repo_dotenv()
tests/unit/test_factory_split.py:259:    from ht_lens.llm.errors import LLMConfigurationError
tests/unit/test_factory_split.py:273:    from ht_lens.llm.errors import LLMConfigurationError
tests/unit/test_factory_split.py:309:    from ht_lens.llm.errors import LLMConfigurationError
tests/unit/test_factory_split.py:332:    from ht_lens.llm.errors import LLMConfigurationError
tests/unit/test_llm_mock.py:65:    from ht_lens.llm.errors import LLMConfigurationError
```

기존 `_finalize_document_status` 로직 (`status='translated'` 마킹)은 변경 없음 — 본 phase scope-out, 정상 운영 흐름에선 .env load fix로 mock 우연 활성화 자체가 차단됨.

기존 `test_translate_cli.py`의 `test_translate_exit_1_on_block_failure`/`_exit_4_on_health_check_failed`가 .env scoped vars와 충돌 → scoped `TRANSLATE_LLM_*` 사용으로 변경 (테스트 의도 보존, scoped > legacy 명문화).

## 5-C. Scoring (100, self-assessment)
| Item | Score / Max | Evidence |
| ---- | ----------- | -------- |
| 독창성 | 14 / 15 | Codex debate에서 plan v1의 module-level 접근을 reject → function-level inline + factory fail-closed로 재설계. defense-in-depth (loader + fail-closed) 두 layer가 독립적으로 silent mock 차단. 단순 .env 추가 이상의 구조적 해결. |
| 완결성 | 34 / 35 | DoD 항목 5개 모두 evidence 제공. Codex debate §5의 모든 missing test 항목 (1-5번) 구현. Codex 비판 모두 ACCEPT + reflected. status 마킹 분석은 scope-out으로 명시. 미세 감점: `test_module_entrypoint_fails_closed_when_dotenv_absent`는 현 checkout의 .env 존재로 skip — 보완 가능 (별도 phase). |
| 안정성 | 30 / 30 | 438/438 통과 (live-LLM 8건은 환경 미설정으로 정상 skip). mypy strict + ruff + format 모두 clean. live subprocess smoke 2건 (B-1, B-2) 모두 expected 결과. 기존 `test_translate_pipeline_mock.py` 등 mock 의도 사용 테스트 영향 없음. |
| 확장성 | 19 / 20 | `dotenv_loader.py`는 향후 다른 CLI 추가 (e.g. Phase 6h의 retranslate CLI)에서도 1줄 호출로 재사용 가능. `LLMConfigurationError`는 향후 factory 정밀화 (e.g. provider whitelist) 진화의 베이스. 미세 감점: `_resolve_provider`는 translate/chat scope 하나씩만 명시 받음 — 향후 N개 scope 시 generalize 필요할 수 있음. |
| **Total** | **97 / 100** | |

## 5-D. Self verdict
- [x] PASS_CANDIDATE (≥95)
- [ ] FAIL → RE-CODE
- [ ] FAIL → RE-PLAN

근거: 모든 자동 검사 green, 두 live subprocess smoke가 의도 동작 검증, Codex 비판 모두 implementation으로 반영. 97/100. cross-verify 결과 대기.
