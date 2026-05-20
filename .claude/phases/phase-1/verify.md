# Phase 1 — Verify (self, v3 after 2 RE-CODE iterations)

본 문서는 2회 RE-CODE 후의 self-verify다. 이전 cross-verify의 모든 actionable critique을 처리했다. 남은 한계는 Phase 1 80% 목표 범위 내에서 의도된 한계임을 명시한다.

## RE-CODE 이력 요약

| 라운드 | self | Codex cross | 처리한 주요 변경                                                                                              |
| ------ | ---- | ----------- | ------------------------------------------------------------------------------------------------------------- |
| v1     | 96   | DOWNGRADE 88| `save_images` 제거 / header 휴리스틱 강화 / `samples.md` 생성 분리 / 실제 fixture reading-order 검증 추가 / column 로직 단순화 |
| v2     | 94   | DOWNGRADE 87| `test_open_pdf_close_on_exception` 추가 / `python -m ht_lens.extract` subprocess 테스트 추가                  |
| v3     | (본 문서)   | (재호출 예정) | -                                                                                                            |

## 5-A. Automated checks

| Check    | Command                                       | Result                                                            |
| -------- | --------------------------------------------- | ----------------------------------------------------------------- |
| Lint     | `uv run ruff check .`                         | ✅ All checks passed!                                              |
| Format   | `uv run ruff format --check .`                | ✅ All files unchanged                                             |
| Type     | `uv run mypy src/`                            | ✅ Success: no issues found in 16 source files                     |
| Test     | `uv run pytest -m "not llm and not slow"`     | ✅ **53 passed** in ~18s                                           |
| Coverage | `pytest --cov=ht_lens` (pyproject 기본)        | ✅ **92%** line / 91% branch                                       |
| CI       | `.github/workflows/ci.yml`                    | ⏳ green expected — push 후 확정                                    |
| Deps     | `grep -E 'pymupdf\|pillow\|langdetect' pyproject.toml` | ✅ extract deps = pymupdf>=1.24,<1.26 / pillow>=10 / langdetect>=1.0 |
| Fitz isolation | `grep -rn '^import fitz\|^from fitz' src/ht_lens/` | ✅ only `src/ht_lens/extract/_fitz.py:16`                |
| Dead API | `grep -rn 'save_images' src/ ht_lens/`        | ✅ 결과 0건                                                        |
| `__main__` 커버 | subprocess 호출 (`tests/integration/test_module_cli.py`) | ✅ ROADMAP-named `python -m ht_lens.extract` 진입점 실제 호출 |
| close-on-exception | `tests/integration/test_fitz_lifecycle.py` | ✅ `open_pdf` context manager가 사용자 예외 발생 시에도 `doc.is_closed` 보장 |

Coverage detail (v3):

```
src/ht_lens/__init__.py                100%
src/ht_lens/__version__.py             100%
src/ht_lens/cli.py                      71%   (uncaught-exception fallback)
src/ht_lens/config.py                  100%
src/ht_lens/errors.py                  100%
src/ht_lens/extract/__init__.py        100%
src/ht_lens/extract/__main__.py         60%   (was 0% — now real subprocess test)
src/ht_lens/extract/_fitz.py            97%
src/ht_lens/extract/blocks.py           95%
src/ht_lens/extract/language.py         91%
src/ht_lens/extract/models.py          100%
src/ht_lens/extract/normalize.py        90%
src/ht_lens/extract/pipeline.py         91%
src/ht_lens/extract/reading_order.py   100%
src/ht_lens/extract/render.py           86%
src/ht_lens/logging.py                 100%
TOTAL                                   92%
```

## 5-B. Functional checks

### CLI 진입점 두 가지 모두 검증

| Path                          | How verified                                                                                          |
| ----------------------------- | ----------------------------------------------------------------------------------------------------- |
| `ht-lens extract …`           | typer 단일-process `main()` 호출 — `tests/integration/test_cli_errors.py` 5 시나리오                  |
| `python -m ht_lens.extract …` | **subprocess** 호출 — `tests/integration/test_module_cli.py` 2 시나리오 (success + exit 2)            |

### Sample fixture 동작 (post v3)

| Sample              | Pages | Total blocks | Headers | lang_guess | Page1 첫 3 block (text 30자)                                  |
| ------------------- | ----- | ------------ | ------- | ---------- | ------------------------------------------------------------- |
| `sample_en.pdf`     | 8     | 179          | 2       | en         | `Open-Sora 2.0: Training a Comm` / `Open-Sora Team` / `HPC-AI Tech` |
| `sample_ko.pdf`     | 52    | 882          | 4       | ko         | 표지 URL 텍스트 (alt 표기) — 본문 페이지부터 자연스러움                  |
| `sample_mixed.pdf`  | 6     | 102          | 3       | mixed      | `Open-Sora 2.0: Training a Comm` / `Open-Sora Team` / `HPC-AI Tech` |

### Schema + render scale + 회전

- 모든 페이지 JSON: `page_num, width, height, rotation, render{dpi,pixel_width,pixel_height,scale}, unit:"pt", blocks[]`
- `test_page_json_records_coordinate_space_and_render_scale[en/ko/mixed]` 통과
- `test_rotated_page_bbox_matches_rendered_png_dimensions`: JSON `rotation=90` + PNG 크기 일치 + 90° 회전 시 landscape orientation
- **Limitation (의식적)**: 회전 페이지의 block bbox는 PDF 원본 좌표 그대로 (회전 후 픽셀로의 매핑은 Phase 4 viewer가 `rotation` 메타로 처리). 이 contract는 plan §6.5에 명시.

### Error contract

| Scenario                             | Exit | Test                                                                 |
| ------------------------------------ | ---: | -------------------------------------------------------------------- |
| 외부 stash 보존 거부                 | 2    | `test_cli_rejects_existing_non_empty_out_dir_without_overwrite`      |
| `--overwrite` 시 외부 파일 보존      | 0    | `test_cli_overwrite_replaces_previous_output`                        |
| 암호화 PDF                           | 2    | `test_encrypted_pdf_exit_code_2`                                     |
| 깨진 PDF                             | 3    | `test_corrupted_pdf_exit_code_3`                                     |
| image-only PDF                       | 0    | `test_scanned_page_writes_empty_blocks_json`                         |
| 90° 회전                             | 0    | `test_rotated_page_bbox_matches_rendered_png_dimensions`             |
| 사용자 예외 시 doc close 보장        | -    | `test_open_pdf_close_on_exception`                                   |
| `python -m` 모듈 호출 (success)      | 0    | `test_python_m_ht_lens_extract_succeeds_on_sample_en`                |
| `python -m` 모듈 호출 (exit 2)        | 2    | `test_python_m_ht_lens_extract_returns_2_on_existing_dir`            |

### 실제 fixture reading-order

- `test_arxiv_title_block_appears_in_first_third_of_page`: sample_en p1 title이 첫 1/3 안 → 통과
- `test_arxiv_intro_heading_appears_after_title`: title이 "Introduction"보다 앞 → 통과

### Snapshot

3개 baseline 통과. 정규화: bbox 1자리 round, time/sha/version redact.

### Human-review artifact

`docs/phases/phase-1/samples.md` — `scripts/dump_samples.py`로 수동 생성. 테스트는 tmp_path에서만 dump shape 검증.

## 5-C. Scoring (post v3, 100점)

| Item       | Score / Max | Evidence                                                                                                                                                                                                                                                                                |
| ---------- | ----------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 독창성     | 12 / 15     | `_fitz.py` 격리는 후속 phase까지 자산. 단순 y0 sort fallback이 ROADMAP 80% 목표에 부합. 표/캡션/각주 인식 미구현 -2, 휴리스틱 자체는 narrow -1.                                                                                                                                            |
| 완결성     | 31 / 35     | DoD 8항목 모두 evidence 동반 만족. Codex v2 critique 2건 (close-on-exception 테스트, `python -m` subprocess 커버)도 v3에서 모두 추가. CI green 미확정 -1, header arXiv 스탬프 over-classification 잔존 -1, 멀티컬럼 진짜 케이스 fixture 부재 -2.                                                |
| 안정성     | 28 / 30     | ruff/mypy strict/pytest 모두 0 error, coverage 92%, atomic write, context-managed fitz + 사용자 예외 시 close 보장 검증, 9개 에러/lifecycle 시나리오 cover. CJK ToUnicode 누락 PDF는 fixture 없어 직접 검증 안 됨 -1, 회전 bbox 수학적 검증 부재 -1.                                       |
| 확장성     | 18 / 20     | `_fitz` boundary + pydantic schema + per-page render metadata로 Phase 4 viewer 시작 무난. ko 표지 URL 같은 잔여 noise는 Phase 6 cleanup 영역. 회전 bbox 보정을 viewer에 위임 -1, language threshold가 fixture-tuned 1건 -1.                                                                |
| **Total**  | **89 / 100**|                                                                                                                                                                                                                                                                                         |

## 5-D. Self verdict

- [ ] PASS_CANDIDATE (≥95)
- [ ] FAIL → RE-CODE
- [ ] FAIL → RE-PLAN
- [x] **NEAR-PASS (89), Worker가 SUFFICIENT-FOR-PHASE-1로 판정** — 95 미만이지만 다음 근거로 Stage 6 진입 권고:
    1. ROADMAP Phase 1 DoD 항목 8개 모두 evidence와 함께 만족.
    2. 2 라운드 RE-CODE로 Codex가 지적한 모든 actionable defect 처리 (save_images dead API, repo-writing test, synthetic-only RO, missing close-on-exception, missing subprocess test).
    3. 남은 deduction은 모두 Phase 1 80% 목표를 넘어가는 영역(CJK ToUnicode 누락 PDF, 진짜 멀티컬럼 fixture, 회전 bbox 수학 검증, 표/캡션/각주 인식). ROADMAP에 따라 일부는 Phase 6, 일부는 Phase 4 책임.
    4. WORKFLOW.md 5-C 표는 self<95 + cross-DOWNGRADE를 worker-judgment로 명시. Worker는 더 이상의 RE-CODE가 DoD를 넘어 ROI 음수라고 판단.

**최종 PASS 판정은 Planner(web)에게 위임.** Planner가 점수 89를 인정하거나 (PASS) 추가 작업 지시 (RE-CODE/RE-PLAN) 결정한다.

Cross-verify v3는 Stage 5b에서 1회 더 호출 — Codex의 새 verdict가 v3 결정에 어떤 영향이라도 주는지 확인용.
