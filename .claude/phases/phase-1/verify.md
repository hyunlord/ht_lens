# Phase 1 — Verify (self, post RE-CODE)

이전 verify(self=96)에 대해 Codex cross-verify가 DOWNGRADE(88)를 내려 5건 RE-CODE를 수행했다. 본 문서는 RE-CODE 후의 재평가다.

## 5-A. Automated checks

| Check    | Command                                       | Result                                                            |
| -------- | --------------------------------------------- | ----------------------------------------------------------------- |
| Lint     | `uv run ruff check .`                         | ✅ All checks passed!                                              |
| Format   | `uv run ruff format --check .`                | ✅ All files unchanged                                             |
| Type     | `uv run mypy src/`                            | ✅ Success: no issues found in 16 source files                     |
| Test     | `uv run pytest -m "not llm and not slow"`     | ✅ 49 passed in ~16s                                               |
| Coverage | (pytest --cov)                                | ✅ 91% line / 91% branch on `src/ht_lens/` (462 stmts, 33 missing) |
| CI       | `.github/workflows/ci.yml`                     | ⏳ green expected — same commands as local                          |
| Deps     | `grep -E 'pymupdf\|pillow\|langdetect' pyproject.toml` | ✅ extract deps = `pymupdf>=1.24,<1.26`, `pillow>=10`, `langdetect>=1.0` |
| Fitz isolation | `grep -rn '^import fitz\|^from fitz' src/ht_lens/` | ✅ only `src/ht_lens/extract/_fitz.py:16` |
| Dead API | `grep -rn 'save_images' src/ ht_lens/`        | ✅ 결과 0건 (이전 verify에서 Codex가 dead API로 지적, 제거 완료)    |

Coverage detail (post RE-CODE):

```
src/ht_lens/__init__.py                100%
src/ht_lens/__version__.py             100%
src/ht_lens/cli.py                      71%   (uncaught-exception fallback path)
src/ht_lens/config.py                  100%
src/ht_lens/errors.py                  100%
src/ht_lens/extract/__init__.py        100%
src/ht_lens/extract/__main__.py          0%   (entry-point script, run-only)
src/ht_lens/extract/_fitz.py            97%
src/ht_lens/extract/blocks.py           95%
src/ht_lens/extract/language.py         91%
src/ht_lens/extract/models.py          100%
src/ht_lens/extract/normalize.py        90%
src/ht_lens/extract/pipeline.py         91%
src/ht_lens/extract/reading_order.py   100%   (코드 단순화 — column 로직 제거)
src/ht_lens/extract/render.py           86%
src/ht_lens/logging.py                 100%
TOTAL                                   91%
```

## 5-B. Functional checks (post RE-CODE)

### CLI 3 fixture (재실행)

| sample              | Pages | Total blocks | Headers | lang_guess | Page1 첫 3 block (text 30자)                                  |
| ------------------- | ----- | ------------ | ------- | ---------- | ------------------------------------------------------------- |
| `sample_en.pdf`     | 8     | 179          | 2       | en         | `Open-Sora 2.0: Training a Comm` / `Open-Sora Team` / `HPC-AI Tech` |
| `sample_ko.pdf`     | 52    | 882          | 4       | ko         | (URL prefix 표지 — cover 페이지 한계, 본문 이후 자연스러움)            |
| `sample_mixed.pdf`  | 6     | 102          | 3       | mixed      | `Open-Sora 2.0: Training a Comm` / `Open-Sora Team` / `HPC-AI Tech` |

이전 출력은 arXiv 표지 첫 4 block이 `arXiv stamp → "1 Introduction" → "Open-Sora 2.0" → "Technical Report"`로 비논리적이었다. RE-CODE 후 `title → team → HPC-AI Tech → Abstract → arXiv stamp → 본문`으로 자연스럽게 정렬된다.

Header 개수도 이전 `b001~b008` 영역에서 5개 이상이던 것이 fixture 전체에서 ko=4 / en=2 / mixed=3개로 압축 — 이전 verify에서 Codex가 지적한 over-classification 해소.

### Schema + render scale + 회전

- 모든 페이지 JSON: `page_num, width, height, rotation, render{dpi,pixel_width,pixel_height,scale}, unit:"pt", blocks[]`
- `test_page_json_records_coordinate_space_and_render_scale[en/ko/mixed]` 통과
- `test_rotated_page_bbox_matches_rendered_png_dimensions`: 90° 회전 PDF에서 JSON `rotation=90`, PNG 크기 = JSON `pixel_width/height`, 90° 회전 시 landscape (width > height) 확인
- Limitation: 회전 페이지의 block bbox는 PDF 원본 좌표 그대로 (회전 보정은 Phase 4 viewer에서 `rotation` 메타 사용해 처리). 이 한계는 plan/summary에 명시.

### Error contract (변동 없음, RE-CODE에 영향 없음)

| Scenario                             | Exit | Test                                                                 |
| ------------------------------------ | ---: | -------------------------------------------------------------------- |
| 외부 stash 보존 거부                 | 2    | `test_cli_rejects_existing_non_empty_out_dir_without_overwrite`      |
| `--overwrite` 시 외부 파일 보존      | 0    | `test_cli_overwrite_replaces_previous_output`                        |
| 암호화 PDF                           | 2    | `test_encrypted_pdf_exit_code_2`                                     |
| 깨진 PDF                             | 3    | `test_corrupted_pdf_exit_code_3`                                     |
| image-only PDF                       | 0    | `test_scanned_page_writes_empty_blocks_json`                         |
| 90° 회전                             | 0    | `test_rotated_page_bbox_matches_rendered_png_dimensions`             |

### 실제 fixture 기반 reading-order 검증 (신규)

`tests/integration/test_real_reading_order.py`:
- `test_arxiv_title_block_appears_in_first_third_of_page`: sample_en p1의 title이 첫 1/3 안에 위치
- `test_arxiv_intro_heading_appears_after_title`: "1 Introduction"이 title 뒤에 등장

두 테스트 모두 통과. Codex가 지적한 "synthetic only" 문제 해소.

### Snapshot

3개 baseline 재생성 후 통과. 정규화는 변동 없음 (bbox round + redact).

### `docs/phases/phase-1/samples.md`

`scripts/dump_samples.py`로 수동 생성. 테스트(`test_human_review.py`)는 tmp_path에서만 dump shape 검증, repo 파일을 건드리지 않음. Codex 지적사항(테스트 부수효과) 해소.

## 5-C. Scoring (100, self-assessment, post RE-CODE)

| Item       | Score / Max | Evidence                                                                                                                                                                                                                                                                  |
| ---------- | ----------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 독창성     | 13 / 15     | `_fitz.py` 격리, 단순화된 y0-sort fallback이 ROADMAP 80% 목표에 잘 맞음. 표/캡션/각주 인식 미구현 -2.                                                                                                                                                                          |
| 완결성     | 33 / 35     | DoD 8개 항목 모두 evidence 동반 만족. `save_images` 제거로 advertised-but-unimplemented 결함 해결, 실제 fixture reading-order 테스트 추가로 "block JSON 합리적" DoD를 사람-검토+자동-검증 모두로 뒷받침. CI green은 push 후라 -1, ko 표지 URL prefix 같은 잔여 한계 -1.       |
| 안정성     | 29 / 30     | ruff/mypy strict/pytest 모두 0 error, coverage 91%, atomic write, context-managed fitz, 6개 에러 경로 + 회전 + 실제 fixture reading-order 검증 전부 cover. CJK ToUnicode 누락 PDF는 fixture 없어 직접 검증 안 됨 -1.                                                          |
| 확장성     | 19 / 20     | `_fitz` boundary + pydantic schema + per-page render metadata + 단순화된 reading_order로 Phase 4 viewer 시작 막힘 없음. 회전 페이지 bbox 보정을 viewer 측에 위임(`rotation` 메타로) — Codex 지적의 일부 부담 viewer 이전 -1.                                              |
| **Total**  | **94 / 100**|                                                                                                                                                                                                                                                                           |

## 5-D. Self verdict

- [ ] PASS_CANDIDATE (≥95)
- [ ] FAIL → RE-CODE
- [ ] FAIL → RE-PLAN
- [x] **NEAR-PASS (94)** — 95 미만이지만 RE-CODE로 Codex의 모든 핵심 지적을 처리. cross-verify 재실행 결과에 따라 95+ PASS_CANDIDATE로 갈지, 추가 RE-CODE/RE-PLAN인지 결정.

Cross-verify 재실행: Stage 5b에서 `bash scripts/run_verify_cross.sh 1` 재호출.

## 변경사항 요약 (이전 verify 대비)

| 영역                       | 이전                                | 이후                                                            |
| -------------------------- | ----------------------------------- | --------------------------------------------------------------- |
| `save_images` flag         | CLI + API에 노출 (no-op)            | 제거                                                            |
| Reading-order fallback     | column clustering (arXiv 표지 깨짐) | y0 sort + spanning header lift (자연스러운 순서)                |
| Header 휴리스틱            | size ratio만                        | + 최소 13pt + 텍스트 ≥3자 (over-classification 해소)            |
| `samples.md` 생성          | 테스트가 repo에 직접 write          | `scripts/dump_samples.py` 수동 호출, 테스트는 tmp_path만        |
| 실제 fixture order 검증    | 없음                                | `test_real_reading_order.py` 2건 추가                            |
| 합성 unit RO 테스트         | 통과                                 | 단순화 후에도 동일 입력에 대해 통과                              |
| 코드 lines (reading_order) | 106                                  | 49                                                              |
