# Phase 6e-2 — Plan

## Goal
CLI 진입점이 `.env`를 로드하지 않아 `ht-lens translate`가 silent하게 mock LLM을 사용하던 P0 버그를 fix하고, 재발 방지 회귀 테스트를 추가한다.

## Context (왜 새 phase?)
Phase 6e (LLMClient split) 완료 후 prod 사용 검증 중 발견:
- `src/ht_lens/api/app.py:135-147`의 `_load_repo_dotenv()`는 API 서버 시작 시에만 호출
- CLI 진입점 (`src/ht_lens/cli.py`)은 `.env` 로드 없음
- 결과: shell에서 env 미설정 상태로 `ht-lens translate`를 실행하면 `from_env_translate()`가 `LLM_PROVIDER` default `"mock"`로 폴백 → `MockLLMClient`가 `[KO] <english>` prefix 출력으로 DB를 오염
- 사용자 발견 시점: Phase 6f-1 swap 직후 `uv run ht-lens translate --doc-id 4` 실행 시 4.4s만에 363 "번역" 완료 → 모두 mock
- DB 정리 + env 명시 export 후 재실행으로 복구했지만 root cause 미수정

이 phase는 P0 fix 한 건에 집중. status 마킹 로직 (`_finalize_document_status`)이 mock도 'translated'로 마킹하는 부분은 분석 후 scope 결정.

## Scope
**In**:
- `_load_repo_dotenv()`를 공유 모듈로 추출 (api/app.py와 cli.py 양쪽에서 import)
- CLI 진입 시 `.env` 자동 로드 (api/app.py와 동일 패턴: `override=False`, repo-root만 검색)
- 단위 테스트: shared loader 동작 + CLI가 mock으로 silent 폴백 안 되는지
- (분석) `_finalize_document_status`의 status 마킹 로직 검토

**Out**:
- status 마킹 로직 변경 (분석 후 별도 phase 권장 — root cause는 .env load이고, 정상 운영 흐름에서 mock 우연 활성화 불가)
- Gemma 4 prompt 재튜닝 (Phase 6f-4 후보, 별도)
- 다른 환경 변수 변경
- DB schema 변경

## Approach
1. **공유 loader 모듈**: `src/ht_lens/_bootstrap.py`에 `load_repo_dotenv()` 추출. api/app.py의 docstring (Phase 6c debate §3의 CWD 안전성 근거 포함) 그대로 보존.
2. **api/app.py** 수정: 같은 함수를 import하도록 변경. 동작 변경 없음 (호출 위치도 동일).
3. **cli.py** 수정: 모듈 import 시점에 `load_repo_dotenv()` 호출. typer app 정의 위쪽에 한 줄. CLI 모든 subcommand (translate, ingest, extract, serve) 에 자동 적용.
4. **테스트**:
   - `tests/unit/test_dotenv_bootstrap.py`: loader 자체 동작
   - `tests/unit/test_cli_env_load.py`: cli 모듈 import 시 .env 적용 + override=False 보존
   - 기존 `tests/unit/test_factory_split.py`의 autouse fixture가 env 격리해주므로 cross-test 오염 없음
5. **status 분석**: `_finalize_document_status`는 `stats.failed > 0`만 확인. mock provider도 failed=0 → 'translated' 마킹. 이는 design ("don't know about provider" — pipeline은 provider-agnostic). 정상 운영에선 .env load fix로 mock 활성화 자체가 방지됨. status 로직 자체 변경은 scope-out.

## File-level changes
| Path | Action | Note |
| ---- | ------ | ---- |
| `src/ht_lens/_bootstrap.py` | NEW | `load_repo_dotenv()` 공유. api/app.py의 `_REPO_ROOT` 계산 + override=False docstring 보존 |
| `src/ht_lens/api/app.py` | MODIFY | 로컬 `_load_repo_dotenv` 제거, `_bootstrap.load_repo_dotenv` import + 호출. 동작 변경 없음 |
| `src/ht_lens/cli.py` | MODIFY | module-level `load_repo_dotenv()` 호출 추가. 위치: typer app 정의 직전 |
| `tests/unit/test_dotenv_bootstrap.py` | NEW | loader unit test (repo-root 검색, override=False, no file 시 noop) |
| `tests/unit/test_cli_env_load.py` | NEW | cli import 시 mock 폴백 방지 회귀 |

## Dependencies (new)
| Package | Why |
| ------- | --- |
| (none) | `python-dotenv>=1.0` 이미 존재 |

## Test strategy
- **Unit (new ~5-8 tests)**:
  - `load_repo_dotenv()` reads `.env` from `_REPO_ROOT`, not CWD
  - `override=False`: shell-exported env 우선
  - 파일 없으면 no-op (raise 없음)
  - cli.py import 시 `os.environ`에 .env 변수 반영
  - factory 가 mock으로 폴백 안 함 (env에 명시 provider 있을 때)
- **회귀**: 기존 unit + integration 모두 green 유지 (특히 `test_factory_split.py` autouse env 격리, `test_translate_pipeline_mock.py`의 의도된 mock 사용)
- **수동 smoke**:
  ```bash
  cd ~/github/ht_lens
  env -i bash -c '
    export PATH=/usr/bin:/bin
    cd /home/hyunlord/github/ht_lens
    uv run ht-lens translate --doc-id 4 --dry-run
  '  # 출력에 mock 흔적 없는지
  ```

## DoD mapping
| DoD item | How to satisfy | Evidence plan |
| -------- | -------------- | ------------- |
| CLI .env load 동작 | cli.py module-level loader 호출 | unit test + dry-run 출력 |
| Silent mock 방지 | factory가 명시 provider 사용 검증 | unit test |
| 기존 동작 호환 | override=False 보존, mock provider 명시 시 정상 동작 | 기존 `test_translate_pipeline_mock.py` 통과 |
| 회귀 0 | mypy strict / ruff / make test-fast | verify.md evidence |
| 공유 위치 | api/app.py와 cli.py 둘 다 같은 함수 사용 | grep 검증 |

## Risk / 주의
- **api/app.py의 `_REPO_ROOT = Path(__file__).resolve().parents[3]`** — 새 모듈 위치 (`src/ht_lens/_bootstrap.py`)는 parents가 다름 (`parents[2]`가 repo root). 새 함수에서 자기 위치 기준으로 다시 계산 필요. 단위 테스트로 확인.
- **`_REPO_ROOT` 명명**: api/app.py에 있던 `_REPO_ROOT` 사용처가 다른 데도 있는지 확인 — `_load_repo_dotenv` 내부에서만 쓰면 안전.
- **integration tests** 중 `LLM_PROVIDER=mock`를 환경 변수로 명시 설정하는 경우, override=False 덕에 .env가 mock를 덮어쓰지 않음. fixture가 명시 export 사용하면 OK.
- **테스트 격리 위험**: cli.py가 import 시점에 .env를 로드하면 pytest collection 중에도 호출됨. autouse fixture가 env를 정리하는지 + monkeypatch 사용 검토.
- **debate에서 다룰 질문**: 새 모듈 이름이 `_bootstrap`이 적절한가? 또는 `dotenv_loader.py`? 또는 그냥 함수만 `__init__.py`에?
