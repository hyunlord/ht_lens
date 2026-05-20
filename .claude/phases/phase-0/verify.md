# Phase 0 — Verify (self)

## 5-A. Automated checks

| Check    | Command                                       | Result                                              |
| -------- | --------------------------------------------- | --------------------------------------------------- |
| Lint     | `uv run ruff check .`                         | ✅ All checks passed!                               |
| Format   | `uv run ruff format --check .`                | ✅ 7 files unchanged (no diff)                      |
| Type     | `uv run mypy src/`                            | ✅ Success: no issues found in 4 source files       |
| Test     | `uv run pytest -m "not llm and not slow"`     | ✅ 3 passed in 0.10s                                |
| Coverage | (pytest --cov)                                | ✅ 100% on `src/ht_lens/` (19/19 stmts, 0 missing)  |
| CI       | `.github/workflows/ci.yml` 작성 완료          | ⏳ push 전 — 첫 push 시 검증 예정                   |

`make check` 한 번에 위 4단계가 모두 green.

## 5-B. Functional checks

Phase 0은 워크플로우 셋업 phase이므로 도메인 기능 검증은 N/A.
대신 다음 셋업 항목이 실제로 동작함을 확인:

- `make install`: uv sync로 40 패키지 + ht-lens(editable) 설치 OK
- `make fmt`, `make lint`, `make test-fast`, `make check`: 각각 의도대로 동작
- Package import 가능: `from ht_lens import __version__` → `"0.0.0"`
- `Settings()` 로드 OK (env 없이도 default 동작)
- `configure_logging()` + `get_logger()` 호출 시 예외 없음 — `test_smoke.py`로 검증
- pytest markers (`slow`, `llm`) 등록됨 — `pyproject.toml`의 `markers`로 명시, `--strict-markers`로 enforce
- pytest fixture (`tmp_workdir`, `sample_*_pdf`, `llm_mock`): conftest에 정의, sample PDF 없으면 자동 skip
- scripts 실행 권한: `scripts/check.sh`, `scripts/run_debate.sh`, `scripts/run_verify_cross.sh` 모두 `-rwxr-xr-x`
- `.gitignore`에 `.omc/` 포함 → 향후 OMC state 파일이 staging되지 않음
- 도메인 코드 부재 확인: `src/ht_lens/` 하위에 `__init__.py`, `__version__.py`, `config.py`, `logging.py` 4파일만 존재 (PDF/LLM/FastAPI/DB 일체 없음)

## 5-C. Scoring (100, self-assessment)

| Item       | Score / Max | Evidence                                                                                                                                                |
| ---------- | ----------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 독창성     | 13 / 15     | Phase 0은 "표준 Python skeleton"이라 차별화 여지 적음. Worker/Critic 이원 워크플로우용 하네스 디렉토리(`.claude/phases/_template/`)는 이 프로젝트 고유. |
| 완결성     | 34 / 35     | ROADMAP Phase 0 DoD 3항목 모두 만족: `make check` green, 도메인 코드 없음, CI 파일 존재. CI green은 push 후에야 확정 가능해 -1.                       |
| 안정성     | 28 / 30     | ruff/mypy strict/pytest 모두 0 error, coverage 100%. 실제 CI 실행 결과는 push 전이라 -2.                                                                |
| 확장성     | 20 / 20     | `_template/` 6종 + phase-0 디렉토리 구조 갖춤. Phase 1부터 풀 사이클(plan→debate→challenge→code→verify→verify-cross→summary) 그대로 적용 가능.        |
| **Total**  | **95 / 100**|                                                                                                                                                         |

## 5-D. Self verdict

- [x] **PASS_CANDIDATE (≥95)** — 최종 PASS는 Planner(web) 검토 후 확정.
- [ ] FAIL → RE-CODE
- [ ] FAIL → RE-PLAN

Cross-verify는 Phase 0에서 선택 (WORKFLOW.md 230~236행). 이번 phase에서는 셋업 단순함을 근거로 생략한다.
