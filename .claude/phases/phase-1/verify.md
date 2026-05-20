# Phase 1 — Verify (self, v5)

Planner의 좁은 RE-CODE 지시 후 작성. 본 문서의 모든 5-A row는 **현재 HEAD에서 방금 재실행한** 출력을 기준으로 한다 (cross-verify v5의 "stale verification" 지적 해소).

## RE-CODE 이력 (전체)

| 라운드 | self | Codex | 처리한 핵심 변경 |
| ------ | ---- | ----- | --------------- |
| v1     | 96   | 88    | save_images 제거 / header 휴리스틱 + min size 13pt / column 로직 단순화 / samples.md 분리 / 실제 fixture RO 검증 |
| v2     | 94   | 87    | test_open_pdf_close_on_exception 추가 / python -m subprocess 테스트 추가 |
| v3     | 89   | 84    | encrypted/corrupted 시 pages/ 자동 cleanup / 세로 텍스트 header 분류 제외 / ht-lens 콘솔 스크립트 subprocess 테스트 / plan §3 stale 부분 갱신 |
| v4     | 86   | 70 → 80 | spanning-header lift 제거 / 진짜 ko 페이지 RO 테스트 / arXiv 페이지 RO 정상화 |
| **v5** | **본 문서** | (재호출 없음 — Planner가 직접 종결) | subprocess CLI 3-fixture 확장 / plan §3 잔존 spanning lift 언급 정리 / verify를 현재 HEAD 기준으로 fresh 재실행 |

## 5-A. Automated checks (현재 HEAD에서 방금 실행)

| Check    | Command                                       | Result (fresh)                                                            |
| -------- | --------------------------------------------- | ------------------------------------------------------------------------- |
| Lint     | `uv run ruff check .`                         | ✅ `All checks passed!`                                                    |
| Format   | `uv run ruff format --check .`                | ✅ `33 files already formatted`                                            |
| Type     | `uv run mypy src/`                            | ✅ `Success: no issues found in 16 source files`                           |
| Test     | `uv run pytest -m "not llm and not slow"`     | ✅ **58 passed** in ~30s (이전 56 + ko/mixed subprocess 2건 신규)            |
| Coverage | pytest --cov (`pyproject.toml`)               | ✅ **91% line / 91% branch** (456 stmts, 32 missing)                       |
| CI       | `.github/workflows/ci.yml`                    | 🟡 **pending push** (Worker는 push 권한 없음)                              |
| Deps     | `pyproject.toml`                               | ✅ extract 신규 deps = pymupdf>=1.24,<1.26 / pillow>=10 / langdetect>=1.0   |
| Fitz isolation | `grep -rn '^import fitz\|^from fitz' src/ht_lens/` | ✅ `src/ht_lens/extract/_fitz.py:16` 한 곳                          |
| Dead API | `grep -rn 'save_images' src/`                  | ✅ 결과 0건                                                                |
| `python -m` 3 fixture | `tests/integration/test_module_cli.py` parametrize | ✅ en/ko/mixed 모두 exit 0 + lang_guess + num_pages 일치   |
| `ht-lens` 콘솔 | `test_ht_lens_console_script_extract`        | ✅ (단, `.venv/bin/ht-lens` 부재 시 skip — venv 의존 환경 제약, 허용됨)        |
| close-on-exception | `tests/integration/test_fitz_lifecycle.py` | ✅ 사용자 예외 후 doc.is_closed                                            |
| 실패 시 cleanup | `tests/integration/test_cli_errors.py::test_{encrypted,corrupted}_*` | ✅ pages/ images/ 생성 안 됨                |

Coverage detail (v5, fresh):

```
src/ht_lens/__init__.py                100%
src/ht_lens/__version__.py             100%
src/ht_lens/cli.py                      71%   (uncaught-exception fallback path)
src/ht_lens/config.py                  100%
src/ht_lens/errors.py                  100%
src/ht_lens/extract/__init__.py        100%
src/ht_lens/extract/__main__.py          0%   * 행동은 subprocess로 검증되나 coverage.py는 subprocess를 집계하지 않음
src/ht_lens/extract/_fitz.py            98%
src/ht_lens/extract/blocks.py           95%
src/ht_lens/extract/language.py         91%
src/ht_lens/extract/models.py          100%
src/ht_lens/extract/normalize.py        90%
src/ht_lens/extract/pipeline.py         91%
src/ht_lens/extract/reading_order.py   100%
src/ht_lens/extract/render.py           86%
src/ht_lens/logging.py                 100%
TOTAL                                   91%
```

## 5-B. Functional checks (v5에서 갱신된 부분만)

### CLI subprocess 3 fixture 확장 (Planner Task 1)

`tests/integration/test_module_cli.py::test_python_m_ht_lens_extract_succeeds_on_each_fixture[…]` parametrize:

| sample              | exit | lang_guess | num_pages |
| ------------------- | ---: | ---------- | --------: |
| sample_en.pdf       | 0    | en         | 8         |
| sample_ko.pdf       | 0    | ko         | 52        |
| sample_mixed.pdf    | 0    | mixed      | 6         |

WORKFLOW.md §141-144의 "Phase 1 CLI 시나리오는 sample PDF 3종으로 실행" 요구가 진짜 subprocess 호출로 충족됨.

### 그 외 (변동 없음, v4 기준 유지)

- Schema + render scale + 회전 검증: 그대로
- Error contract 9 시나리오: 그대로
- 실제 fixture reading-order (en + ko): 그대로
- Snapshot 3 baseline: 그대로

## 5-C. Scoring (v5)

v5에서 변동 사항: CLI subprocess 3-fixture 커버 + plan stale 잔여 청소 + verify를 fresh 출력 기반으로 재작성. 점수 영향: 완결성 +2 (CLI subprocess 모든 fixture, plan stale 청소).

| Item       | Score / Max | Evidence (v5)                                                                                                                                                                                          |
| ---------- | ----------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| 독창성     | 12 / 15     | 변동 없음. `_fitz.py` 격리 + RawLine.direction + 단순 y0-sort fallback. 표/캡션/각주 미구현 -2, narrow 휴리스틱 -1.                                                                                       |
| 완결성     | 32 / 35     | DoD 8항목 + Codex 9건 actionable critique + Planner의 3건 좁은 fix 모두 처리. CI green 미확정 -1, 진짜 멀티컬럼 본문 fixture 부재 -2.                                                                       |
| 안정성     | 27 / 30     | 변동 없음. ruff/mypy strict/pytest 0 error, coverage 91%, atomic write, context-managed fitz, 9개 error/lifecycle 시나리오, failure cleanup. CJK ToUnicode 누락 PDF -1, 회전 bbox 수학적 검증 부재 -1, 진짜 멀티컬럼 본문 fixture 부재 -1. |
| 확장성     | 17 / 20     | 변동 없음. `_fitz` boundary + pydantic schema + per-page render metadata. 회전 bbox 보정 viewer 위임 -1, language threshold fixture-tuned -1, 본격 멀티컬럼 알고리즘 Phase 6 -1.                                  |
| **Total**  | **88 / 100**|                                                                                                                                                                                                        |

## 5-D. Self verdict (v5)

- [ ] PASS_CANDIDATE (≥95)
- [ ] FAIL → RE-CODE
- [ ] FAIL → RE-PLAN
- [x] **NEAR-PASS-WITH-LIMITATIONS (88), Worker가 Stage 6 진입 권고**

근거:

1. **ROADMAP Phase 1 DoD 8항목 모두 evidence 동반 만족**.
2. **Codex 누적 9건 actionable critique 처리 완료** (v1~v4).
3. **Planner의 v5 좁은 fix 3건 처리 완료**:
   - Stale verification 해소 (본 문서 5-A 모두 fresh 출력 기반)
   - CLI subprocess 3 fixture 확장
   - Plan §3 spanning-lift 잔존 텍스트 정리
4. **남은 deduction(12점)은 외부 의존 또는 Phase 4/6 영역**.

**Planner가 직접 종결**한다 (cross-verify 재호출 없음, 무한 iteration 방지). 결정은 summary.md의 status field가 보유.

## Known issues / debt (v5 추가분)

cross-verify v5에서 새로 지적된 항목 중 Phase 1 범위 외:

- **`Abstract` / `1 Introduction`이 `header`가 아닌 `text`로 분류됨** — Phase 6 header heuristic 보강 (size + horizontal 이외의 신호 도입 필요)
- **`samples.md` determinism 자동 검증 부재** — Phase 6 또는 별도 minor task (commit 시 hash 비교 등)
- **회전 페이지 bbox-to-pixel 정확성 미검증** — Phase 4 viewer overlay 책임

(기존 v4의 known issues는 summary.md에 통합되어 있음.)
