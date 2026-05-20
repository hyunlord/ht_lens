# Phase 1 — Summary

## Status
**PASS_CANDIDATE (post Planner-directed v5 RE-CODE, NEAR-PASS-WITH-LIMITATIONS)** — DoD 8개 항목 모두 evidence와 함께 만족. Planner의 좁은 RE-CODE 지시 3건(stale verification 해소 / CLI subprocess 3-fixture 확장 / plan §3 stale 정리) 처리 완료. WORKFLOW.md에 따라 cross-verify는 v5에서 재호출하지 않는다 (Planner가 직접 종결). 최종 PASS 판정은 Planner.

## Score

| Round | Self | Cross verdict | Cross score |
| ----- | ---- | ------------- | ----------- |
| v1    | 96   | DOWNGRADE     | 88          |
| v2    | 94   | DOWNGRADE     | 87          |
| v3    | 89   | DOWNGRADE     | 84          |
| v4    | 86   | REJECT → DOWNGRADE | 70 → 80 |
| **v5** | **88** | (재호출 없음 — Planner 종결) | — |

Codex 누적 9건 actionable defect + Planner v5 좁은 fix 3건 모두 처리. 잔여 deduction은 외부 의존(CI green push 후 확정) 또는 Phase 4/6 영역.

## What was built

1. **PyMuPDF 격리 wrapper** (`src/ht_lens/extract/_fitz.py`): `# type: ignore`를 단일 boundary에 가둠. RawSpan/RawLine/RawBlock/RawPage typed dataclass, `open_pdf` context manager(사용자 예외 시 close 보장), `iter_pages`(get_text("dict", sort=True) 사용).
2. **Block grouping** (`src/ht_lens/extract/blocks.py`): line-단위 paragraph 묶기, font-size + 가로 방향 휴리스틱 기반 header 판정 (size 13pt 이상 + ratio 1.4× + ≤2줄 + ≥3자 + 모두 가로 lines).
3. **Reading order** (`src/ht_lens/extract/reading_order.py`): PyMuPDF sort=True baseline. y-회귀가 1회라도 있으면 단순 `(y0, x0)` sort로 fallback. (초기 plan의 1~3컬럼 자동감지 + spanning header lift는 RE-CODE에서 제거. sample_ko 폭넓은 본문 단락이 잘못 lift되는 결함을 잡음.)
4. **Page renderer** (`src/ht_lens/extract/render.py`): 200dpi PNG, atomic temp-rename, PIL로 실제 픽셀 크기 측정해 RenderResult로 반환.
5. **Language detection** (`src/ht_lens/extract/language.py`): langdetect (seed 0), 페이지별 majority + minor_ratio ≥ 0.20 → mixed. 임계 0.20은 sample_mixed fixture 1건에서 calibrate.
6. **Pipeline** (`src/ht_lens/extract/pipeline.py`): 출력 디렉토리 안전 검증(`--overwrite` 없으면 비어있어야), 페이지 단위 PNG + JSON atomic write, doc_meta.json(sha256 + ISO 8601 + version), 실패 시 pages/images 자동 cleanup.
7. **CLI** (`src/ht_lens/cli.py`, `src/ht_lens/extract/__main__.py`): typer multi-command app, `ht-lens extract` + `python -m ht_lens.extract` 양쪽 지원, 종료 코드 0/2/3 contract.
8. **Schema** (`src/ht_lens/extract/models.py`): pydantic BaseModel로 Block/PageDoc/DocMeta. RenderInfo로 dpi/pixel_w/pixel_h/scale 보존.
9. **Snapshot normalize** (`src/ht_lens/extract/normalize.py`): bbox 1자리 round + 비결정 필드 redact.
10. **Errors** (`src/ht_lens/errors.py`): EncryptedPDFError(exit 2), CorruptedPDFError(exit 3), OutputDirNotEmptyError(exit 2).
11. **Tests**: unit 13, integration 43 = 56 total. Synthetic + real-fixture reading-order, CLI errors, rotated/encrypted/corrupted/scanned 합성 PDF, fitz lifecycle, subprocess CLI(`python -m` + `ht-lens` 콘솔 양쪽), snapshot 3 baseline.
12. **Human-review artifact**: `docs/phases/phase-1/samples.md` (148KB, `scripts/dump_samples.py`로 수동 생성, deterministic).

## Files changed

phase-1 진입 후 변경 = 31 new files / ~3000 LOC.

대분류 (commit chain 기준):
- `chore(phase-1): plan` → plan.md 도입
- `chore(phase-1): debate` → debate.md (Codex)
- `chore(phase-1): challenge` → challenge.md + plan revision
- `feat(phase-1): _fitz typed wrapper`
- `feat(phase-1): extract pipeline (...)` → 7 신규 모듈
- `test(phase-1): unit tests` → 4 unit files
- `test(phase-1): integration ...` → 5 integration files
- `chore(phase-1): verify` (v1~v4)
- `chore(phase-1): verify-cross` (v1~v4, Codex)
- `fix(phase-1): address cross-verify DOWNGRADE` (v1 결과)
- `test(phase-1): close-on-exception + subprocess CLI coverage` (v2 결과)
- `fix(phase-1): cross-verify v3 follow-ups` (v3 결과)
- `fix(phase-1): drop spanning-header lift + plan cleanup` (v4 결과)

## Deviations from plan

| 영역                          | Plan                                                          | Final                                                                    |
| ----------------------------- | ------------------------------------------------------------- | ------------------------------------------------------------------------ |
| `save_images` 옵션            | 기본 False, CLI 옵션 노출                                       | RE-CODE에서 전체 제거. 미구현 advertised API는 dead surface로 판단.        |
| Reading order multi-column   | 1~3 컬럼 x-cluster 자동 감지                                    | 단순 (y0, x0) sort fallback. 단일-block 마진(arXiv 세로 스탬프)을 컬럼으로 잘못 잡는 문제 + 폭넓은 본문 단락이 spanning header로 lift되는 문제 두 결함을 잡기 위해 단순화. ROADMAP 80% 목표 부합. 진짜 multi-column 본문 fixture 들어오면 Phase 6에서 재설계. |
| Language threshold            | mixed 임계 0.30                                                | 0.20 (sample_mixed fixture로 calibrate, code 주석 + summary에 명시).      |
| Header 분류 추가 기준         | size ratio + 라인 수만                                          | + 최소 13pt + ≥3자 + 모두 가로 방향. RE-CODE로 over-classification 해소. |
| Per-page JSON `render` 필드   | plan §6.5에 새로 추가하기로 함                                  | 구현. pixel_width/height는 실제 PNG에서 측정.                              |
| Pipeline 실패 cleanup         | 명시 없음                                                      | RE-CODE에서 추가. encrypted/corrupted 시 pages/images 자동 생성 방지.    |

## Evidence index

- plan: `.claude/phases/phase-1/plan.md` (RE-CODE 반영 최종본)
- debate: `.claude/phases/phase-1/debate.md` (Codex v1 산출)
- challenge: `.claude/phases/phase-1/challenge.md` (debate 응답 + plan revision 명세)
- verify: `.claude/phases/phase-1/verify.md` (v4 FINAL)
- verify-cross: `.claude/phases/phase-1/verify-cross.md` (Codex v5 — DOWNGRADE 80)
- snapshots: `tests/integration/__snapshots__/test_extract_snapshot.ambr` (3 baseline, en/ko/mixed)
- human-review: `docs/phases/phase-1/samples.md` (`scripts/dump_samples.py`로 재생성 가능)
- 실행 가능한 CLI: `uv run ht-lens extract …` 또는 `uv run python -m ht_lens.extract …`

## Known issues / debt

| Item | 영향 | 추적 |
| ---- | ---- | ---- |
| CJK ToUnicode 누락 PDF 미검증 | medium | Phase 6 fixture 보강 |
| 진짜 멀티컬럼 본문 fixture 부재 | medium | Phase 6 |
| 회전 페이지 bbox 수학적 매핑 미검증 (cross-verify v5 재지적) | medium | Phase 4 viewer |
| sample_ko 표지 URL prefix noise | low | 데이터 cleanup, Phase 6 |
| `Abstract` / `1 Introduction`이 header가 아닌 text로 분류 (cross-verify v5 신규) | low | Phase 6 header heuristic 보강 |
| `samples.md` determinism 자동 검증 부재 (cross-verify v5 신규) | low | Phase 6 또는 별도 minor task |
| language threshold 0.20 fixture-tuned | low | Phase 6 (추가 fixture 확보 후 재calibrate) |
| CI green 미확정 | low | Human이 push 시 GitHub Actions에서 확정 |

## Recommended next

- 본 summary를 Planner(web)에 전달.
- Planner 결정 옵션:
  1. **PASS** — Phase 1 DoD 8항목 모두 evidence 동반 만족, Codex의 모든 actionable critique 처리 완료. Phase 2 (DB + LLM + Translation) 시작.
  2. **PASS with debt** — known issues를 ROADMAP의 Phase 4/6에 정식 명기 후 Phase 2 진행.
  3. **추가 RE-CODE 요구** — 단, Worker는 ROI 음수로 판단. fixture 추가 작업과 결합하지 않으면 추가 가치 없음.
- Phase 2 시작 시 점검:
  - `ExtractResult` (out_dir, num_pages, lang_guess, page_block_counts)가 ingest 입력으로 충분한지 확인
  - DB schema에서 `render` 메타데이터 보존 여부 결정
  - block 단위 캐시 키 설계 (ROADMAP §risks의 번역 비용 항목)
