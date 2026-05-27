# Phase 6h-1 — Verify (self)

Pre-flight: `git status` clean for tracked production+test files ✅. HEAD = `53a3357 feat(phase-6h-1): Y-overlap inline join + visual-line header count`. `ROADMAP.md`는 사용자 WIP (touch 안 함).

## 5-A. Automated checks

| Check    | Command | Result |
| -------- | ------- | ------ |
| Lint     | `uv run ruff check src/ tests/ scripts/` | `All checks passed!` (0 errors) |
| Format   | `uv run ruff format --check src/ tests/ scripts/` | 156 files OK (after auto-format) |
| Type     | `uv run mypy --config-file pyproject.toml src/` | `Success: no issues found in 68 source files` |
| Test     | `uv run pytest -m "not llm and not slow" -q --no-cov` | **546 passed, 1 skipped, 7 deselected, 9 warnings in 242.20s** (baseline 533 → 546, +13 new/updated) |
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

**Backfill atomicity** (`tests/integration/test_backfill_atomicity.py`, 1 test):
13. `test_backfill_aborts_doc_on_block_count_mismatch` — DB(2 blocks/page) vs PDF(1 block/page) → dry-run + apply 모두 abort, DB 변동 0.

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

| Item       | Score / Max | Evidence |
| ---------- | ----------- | -------- |
| 독창성     | 13 / 15     | Y-overlap heuristic + height-similarity + direction은 결합이지만 standard PDF extraction tooling. visual line count for header는 작은 invention. -2. |
| 완결성     | 30 / 35     | Codex 5 critical 모두 fix + 11 tests + snapshot update + backfill script. -5: backfill ops 자동 실행 안 함 (사용자 결정), ROADMAP "Alembic 0005" 항목 미충족 (스키마 변동 0이지만 ROADMAP wording은 그대로), Hot-fix A1 제거 분리. |
| 안정성     | 27 / 30     | 회귀 0 (533→546), rotation regression locked, header heuristic 보존 locked, backfill atomicity locked. -3: doc 7 dry-run에서 page coverage drift 발견 (별도 ops issue), live PDF backfill smoke 부재 (mock + in-memory만). |
| 확장성     | 18 / 20     | helper들은 paragraph 내부 결합 일반 logic. 향후 span/word level 재설계 시 helper 재사용 가능. -2: span-level y-clustering으로 더 깊은 fix는 향후 phase (Codex §4.1 REJECT). |
| **Total**  | **88 / 100** | WORKFLOW.md §217-223 ≥95 미달. Phase 7a-2 V3에서 학습한 정직 라벨링 — PASS_CANDIDATE 라벨 X. |

V2 plan + Codex 5 critical fix 모두 적용. 본문 작업 견고. 단 점수 인플레이션 회피.

## 5-D. Self verdict

- [ ] PASS_CANDIDATE (≥95) — **불가**. self-score 88 < 95.
- [x] **PASS_LOW** — DoD 항목 거의 충족 + Codex critical 5개 모두 fix. Cross-verify Round 1 후 판단.
- [ ] FAIL → RE-PLAN

5-B Round 1 cross-verify (`bash scripts/run_verify_cross.sh 6h-1`) 실행.
