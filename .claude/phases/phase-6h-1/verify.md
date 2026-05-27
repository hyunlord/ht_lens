# Phase 6h-1 — Verify (V2, post R1 RE-CODE)

> **V1 → V2 changelog**: V1 (88/100 PASS_LOW) → Codex R1 REJECT ~68/100 with 3 concrete gaps (backfill page-set hole, untested abort paths, no successful-apply test). V2: RE-CODE adds DB-only page validation in `backfill_doc` + 3 new atomicity tests (PDF-missing-pages, bbox-drift, successful-apply). Score honestly lowered to reflect the embedding-search scope hole that R1 surfaced.

Pre-flight: `git status` clean for tracked files ✅. HEAD = `5e96024 fix(phase-6h-1): R1 verify-cross issues`. `ROADMAP.md`는 사용자 WIP (touch 안 함).

## 5-A. Automated checks

| Check    | Command | Result |
| -------- | ------- | ------ |
| Lint     | `uv run ruff check src/ tests/ scripts/` | `All checks passed!` (0 errors) |
| Format   | `uv run ruff format --check src/ tests/ scripts/` | 156 files OK (after auto-format) |
| Type     | `uv run mypy --config-file pyproject.toml src/` | `Success: no issues found in 68 source files` |
| Test     | `uv run pytest -m "not llm and not slow" -q --no-cov` | **549 passed, 1 skipped, 7 deselected, 9 warnings in 244.00s** (baseline 533 → 549, +16 new/updated incl. 3 R1 RE-CODE tests) |
| Snapshot | `__snapshots__/test_extract_snapshot.ambr` | 3 sample_*.pdf snapshots updated (`"1\nIntroduction"` → `"1 Introduction"` 등) |
| Coverage | (정책상 측정 안 함) | n/a |
| CI       | post-push verification (Stage 6) | pending |

### 신규 tests (총 +11, snapshot update 3개 별도)

**Unit** (`tests/unit/test_extract_blocks_inline_join.py`, 7 tests):
1. `test_single_line_block_unchanged` — 1 RawLine paragraph → text/bbox 그대로.
2. `test_y_overlap_lines_joined_with_space` — 같은 y (61.5-72.4) → space join, bbox x-union.
3. `test_y_distinct_lines_joined_with_newline` — 다른 y → `\n` 보존.
4. `test_should_concat_inline_threshold_60pct` — 60% 경계 (49% False, 60% True).
5. `test_should_concat_inline_rejects_non_horizontal` — rotation safety (direction 체크).
6. `test_should_concat_inline_rejects_height_mismatch` — superscript guard (height ratio < 0.7 → False).
7. `test_join_lines_mixed_paragraph_three_pieces` — same-line 두 piece + 다른 y 한 piece 혼합.

**Header regression** (`tests/unit/test_extract_blocks_header_visual_lines.py`, 2 tests):
8. `test_header_split_into_3_horizontal_fragments_still_classified_as_header` — 3 same-y fragments → visual count 1 → header.
9. `test_multi_visual_line_title_above_max_is_text_not_header` — 3 distinct y → visual count 3 > 2 → text.

**KPI synthetic** (`tests/integration/test_phase_6h1_kpi.py`, 2 tests):
10. `test_pattern_a_fix_collapses_inline_split_lines` — 50개 합성 Pattern A paragraphs 모두 `\n`-free, "1.0 Section title 1" 형식.
11. `test_distinct_visual_lines_preserve_newline` — 30개 multi-line paragraph 모두 `\n` 2개 보존.

**Smoke** (`tests/integration/test_extract_inline_join_smoke.py`, 1 test):
12. `test_inline_join_smoke_pdf` — in-memory PDF로 두 text piece at same y → group_page 결과 space-join. PyMuPDF가 fragments를 별도 block으로 분리하는 경우 skip-with-diagnostic.

**Backfill atomicity** (`tests/integration/test_backfill_atomicity.py`, 4 tests — V2 추가):
13. `test_backfill_aborts_doc_on_block_count_mismatch` — DB(2 blocks/page) vs PDF(1 block/page) → dry-run + apply 모두 abort, DB 변동 0.
14. **(R1 fix)** `test_backfill_aborts_when_pdf_missing_pages_db_has` — PDF가 DB보다 짧을 때 (page 2-3 누락) abort, DB 변동 0. Codex R1 §4 #1 page-set hole 직접 lock.
15. **(R1 fix)** `test_backfill_aborts_on_bbox_drift` — block bbox 위치 mismatch → abort, DB 변동 0. R1 §4 untested abort branch.
16. **(R1 fix)** `test_backfill_apply_succeeds_when_pdf_matches_db` — DB와 PDF가 일치 → apply 성공, block_id 보존, `STALE\nTEXT` → 실제 텍스트로 update. R1 §2 successful apply path 직접 lock.

### Codex debate 5 critical items 검증

| Critical issue | V2 fix | Test evidence |
|---|---|---|
| Rotation 무시 (§3.3) | `_should_concat_inline` direction check | unit test 5 |
| Header raw line count (§2.4) | `_count_visual_lines` + 그 결과로 `_HEADER_MAX_LINES` 체크 | header test 8 |
| Backfill partial commit (§3.4) | per-doc atomic — 전 page validate 후 commit | atomicity test 13 |
| KPI test 부재 (§5) | synthetic measurement | KPI tests 10, 11 |
| Threshold edge cases (§3.1) | 60% + height-similar 0.7 | unit tests 4, 6 |

## 5-B. Functional checks

### 5-B-1. Snapshot diff 의미
Snapshot diff (`tests/integration/__snapshots__/test_extract_snapshot.ambr`)는 Phase 6h-1 fix를 직접 보임:
- `"1\nIntroduction"` → `"1 Introduction"` (section number + title)
- `"60.9\n39.1"` → `"60.9 39.1"` (table row: 두 숫자 같은 line)
- `"77.7\n22.3"` → `"77.7 22.3"`
612 lines 변경 (121 insertions, 491 deletions). Phase 6h-1 fix가 새 extract에서 정확히 동작.

### 5-B-2. doc 7 dry-run (live PDF)
명령: `uv run python scripts/backfill_block_text.py --doc-id 7 --pdf /home/hyunlord/pdfs_to_test/book2.pdf --dry-run`

결과: `ABORT (no DB writes): DB has no row for page 5` (5 pages checked).
해석: 기존 doc 7의 DB Pages 테이블이 page 1-4까지만 존재하고 page 5는 없음 (이전 ingest 또는 page numbering 차이). atomic abort가 정상 동작 — DB 변동 0. 실제 backfill ops는 page coverage curation 필요 (별도 phase 또는 manual).

### 5-B-3. RE-CODE regression check (CLAUDE.md 규칙)
본 phase는 single implementation round (RE-CODE 없음). production code 변경 영역 모두 신규 테스트로 직접 lock:

| Production change | Locking test |
|---|---|
| `_should_concat_inline` (new) | unit tests 2, 3, 4, 5, 6 (모든 분기) |
| `_join_lines` (new) | unit tests 2, 3, 7 + smoke + KPI |
| `_count_visual_lines` (new) | header tests 8, 9 |
| `group_page` text 변경 | unit + snapshot update |
| `group_page` header check 변경 | header tests 8, 9 |
| `scripts/backfill_block_text.py` (new) | backfill atomicity test 13 |

새 식별자 grep:
- `_should_concat_inline` → 1 production module + 5 test references
- `_join_lines` / `_count_visual_lines` → production + 다수 test
- `backfill_doc` → 1 script + 1 test

### 5-B-4. CI status
push 후 측정 (Stage 6). 별도 보고.

## 5-C. Scoring (100, self-assessment, honest per WORKFLOW.md)

| Item       | Score / Max (V1 → V2) | Evidence + R1 adjustment |
| ---------- | --------------------- | ------------------------ |
| 독창성     | 13 → **12 / 15** | Codex R1 §3: pragmatic heuristic, not novel design. Y-overlap + height + direction 결합은 standard. -3. |
| 완결성     | 30 → **25 / 35** | Codex R1 §3: ROADMAP "Alembic 0005" 미충족 (스키마 변동 0이지만 ROADMAP wording 그대로), live backfill 성공 case 없음 (doc 7 dry-run page-coverage abort), embedding refresh manual reminder only. R1 RE-CODE에서 일부 회복 (page-set abort lock + apply-mode test). -10. |
| 안정성     | 27 → **24 / 30** | Codex R1 §3: V1에서 1 abort path만 test → R1에서 4 abort/apply path test로 확장. 단 runtime search stale-candidate hole (embedding/search.py)는 별도 phase. -6. |
| 확장성     | 18 → **16 / 20** | Codex R1 §3: helper extraction 재사용 가능하지만 phase의 manual-refresh dependency가 runtime search와의 hidden coupling. span-level 재설계는 별도 phase. -4. |
| **Total**  | **88 → 77 / 100** | WORKFLOW.md ≥95 미달. R1 audit 68 보다는 RE-CODE로 +9 회복했지만 honest score 77. Phase 7a-2 V3 정직 라벨링 적용. |

V2: V1의 critical 5개 + R1의 3개 추가 gap 모두 fix. 단 runtime stale-candidate hole (embedding/search.py freshness check)는 본 phase scope 밖 — 별도 phase / 후속 작업.

## 5-D. Self verdict

- [ ] PASS_CANDIDATE (≥95) — **불가**. self-score 77 < 95.
- [x] **PASS_LOW** — V1 critical 5 (Codex debate) + R1 concrete 3 (cross-verify) 모두 fix. 549 tests pass. Stage 5-B Round 2 cross-verify 실행 → CONFIRM_PASS / minor DOWNGRADE / 추가 RE-CODE 결정.
- [ ] FAIL → RE-PLAN

5-B Round 2 cross-verify (CLAUDE.md 상한) 실행.
