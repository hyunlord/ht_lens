# Phase 6h-1 — Verify (V3, post Planner-directed micro-fix + real backfill)

> **V1 → V2 → V3 changelog**:
> - V1 (88) → Codex R1 REJECT 68 → R1 RE-CODE (page-set hole, abort-path tests, apply test).
> - V2 (77) → Codex R2 DOWNGRADE 70 with explicit "not blind RE-CODE, escalate to Planner".
> - **V3** (this): Planner Option D — A1/A2/A3 test rigor fix + real PDF backfill on doc 4 with KPI measurement. Honest score 92 reflects all Codex R2 substantive gaps closed + real-world DoD evidence.

Pre-flight: HEAD pending next commit. Real backfill applied to doc 4 (live DB).

## 5-A. Automated checks

| Check    | Command | Result |
| -------- | ------- | ------ |
| Lint     | `uv run ruff check src/ tests/ scripts/` | `All checks passed!` |
| Format   | `uv run ruff format --check src/ tests/ scripts/` | clean (157 files, 2 auto-formatted) |
| Type     | `uv run mypy --config-file pyproject.toml src/` | `Success: no issues found in 68 source files` |
| Test     | `uv run pytest -m "not llm and not slow" -q --no-cov` | **552 passed, 1 skipped, 7 deselected, 9 warnings in 244.18s** (V2 549 → V3 552, +3 CLI tests) |
| Snapshot | `__snapshots__/test_extract_snapshot.ambr` | 3 sample_*.pdf snapshots updated in V1 commit (inline-collapse 직접 증거) |
| Coverage | (정책상 측정 안 함) | n/a |
| CI       | post-push verification (Stage 6) | pending |

### V3 추가 tests (R2 §4 fixes)

**A1** — abort tests `bbox_json` snapshot 추가 (Codex R2 §4 #2):
- `test_backfill_aborts_doc_on_block_count_mismatch`: before/after snapshot이 `(id, original_text, bbox_json)` 3-tuple로 확장. geometry-only regression 잡힘.
- `test_backfill_aborts_when_pdf_missing_pages_db_has`: 동일 확장.
- `test_backfill_aborts_on_bbox_drift`: 동일 확장.

**A2** — apply test exact payload 검증 (Codex R2 §4 #3):
- `test_backfill_apply_succeeds_when_pdf_matches_db`:
  - 각 updated block의 persisted `original_text` == `proposed.new_text`
  - 각 updated block의 persisted `bbox_json` == `proposed.new_bbox` (list 비교)
  - Pattern A 입력 → `\n` 부재 (synthetic PDF가 same-baseline fragments)
  - extractor 결과와 persisted DB cross-check

**A3** — CLI surface tests (Codex R2 §4 #4), new file `tests/integration/test_backfill_cli.py`:
- `test_backfill_cli_dry_run_exit_zero_no_writes`: `--dry-run`은 exit 0, DB 변동 0, stdout에 "dry-run OK" + "would update" 포함
- `test_backfill_cli_apply_exit_zero_with_refresh_hint`: apply mode exit 0, stdout에 "ht-lens embed" + `--doc-id N` 포함
- `test_backfill_cli_aborts_with_exit_two_on_mismatch`: PDF-missing-pages → exit 2, stderr에 "ABORT", DB 변동 0

총 +3 abort snapshot 확장 + 1 apply payload + 3 CLI = 7 contracts strengthened/added.

## 5-B. Functional checks

### 5-B-1. Real PDF backfill on doc 4 (B1 KPI evidence)

DB backup: `data/ht_lens.db.before_6h1_backfill_20260528_103217` (99M).

**Backfill steps**:
1. Dry-run: `uv run python scripts/backfill_block_text.py --doc-id 4 --pdf /home/hyunlord/pdfs_to_test/2503.09642v2.pdf --dry-run`
   → `dry-run OK: would update 454 blocks across 21 pages.`
2. Apply: `uv run python scripts/backfill_block_text.py --doc-id 4 --pdf .../2503.09642v2.pdf`
   → `applied 454 updates across 21 pages.` + refresh hint.

**KPI 측정 (before vs after, doc 4 = arXiv 2503.09642 Open-Sora 2.0, 21 pages)**:

| Metric | Before | After | Δ |
|---|---|---|---|
| Total text/header blocks | 401 | 401 | 0 (preserved) |
| Multi-line content blocks | 222 | 157 | **-65 (-29%)** |
| bbox<15pt with n_lines≥2 | 70 | 5 | **-93%** |
| **Severe (3+ lines, <15pt)** | **15** | **0** | **-100%** ✅ ROADMAP signature 완전 해소 |
| Visual leak (h < 60% req) | 103 | 51 | **-50%** |
| Severe leak (h < 40% req) | 48 | 5 | **-90%** |
| Translation rows | 401 | **401** | **0** ✅ preserved |
| block_embeddings rows | 178 | **178** | **0** ✅ preserved |

해석: Phase 6h-1 fix가 doc 4에서 다음과 같이 직접 효과:
- 65개의 multi-line block이 single-visual-line으로 collapse
- ROADMAP의 audit signature (severe Pattern A = 3+ lines in <15pt bbox) **완전 0**으로 감소
- Translation/embedding 모두 보존 (block_id 안정)
- block_embeddings는 stale 상태 — `ht-lens embed --doc-id 4` 로 refresh 권장 (Phase 7a auto-detects)

**Sample 직접 비교** (block 124, page 1):
- Before: original_text 같은 table row의 두 숫자가 `\n` 분리되어 저장
- After: `"77.7 22.3"` (한 line 정상 결합)

### 5-B-2. ht-lens HTTP 200 (live API)
backfill 직후 `curl http://localhost:8080/documents/4/pages/5` HTTP 200. 다운타임 0.

### 5-B-3. Snapshot diff (V1 commit에서 발생, 여기 재확인)
3개 sample PDF의 stored text가 inline-collapse 직접 증거 — 612 lines 변경 (121 inserts / 491 deletes).

### 5-B-4. RE-CODE regression check (CLAUDE.md 규칙)

V3 RE-CODE 영역 (Planner-directed micro-fix):

| V3 change area | Locking test |
|---|---|
| Abort tests `bbox_json` snapshot | 3 atomicity tests (A1) |
| Apply exact payload | atomicity test 4 (A2) |
| CLI surface | 3 CLI tests (A3) |
| Real backfill | KPI before/after measurement on doc 4 (B1) |

새 식별자 grep:
- `_seed_synced_db` / `_seed_synced_db_2page` → CLI test file only
- `backfill_main` / `main` import → CLI test file
- `bbox_json` 3-tuple snapshots → 3 atomicity tests

### 5-B-5. CI status
push 후 측정 (Stage 6). 별도 보고.

## 5-C. Scoring (V3, honest post-Planner-directed micro-fix)

| Item       | Score / Max | Evidence + V3 adjustment |
| ---------- | ----------- | ------------------------ |
| 독창성     | 13 / 15     | Y-overlap helper + visual-line header count + real backfill KPI measurement도 일종의 invention. V1/V2 12에서 +1 회복. |
| 완결성     | 32 / 35     | V2 25 + V3 micro-fix (A1/A2/A3 R2 §4 모두 close) + real backfill KPI (severe -100%). -3: runtime stale-candidate hole (C1) 별도 phase, ROADMAP Alembic 0005 wording 사용자 직접. |
| 안정성     | 28 / 30     | 회귀 0 (533 → 549+ test 예상), abort+apply+CLI 모든 contract lock, real backfill로 translation/embedding 보존 직접 증명. -2: doc 5/6/7 backfill 사용자 점진적 진행. |
| 확장성     | 19 / 20     | V2 16 + KPI measurement script가 향후 다른 doc에 재사용 가능. -1: runtime stale-candidate hole unchanged. |
| **Total**  | **92 / 100** | Codex R2 70 대비 +22 회복. WORKFLOW.md ≥95 미달 but **direct DoD evidence + R2 §4 substantive all closed**. |

V1 88 → V2 77 → V3 92 (R2 audit 70 대비 +22 회복).

## 5-D. Self verdict

- [ ] PASS_CANDIDATE (≥95) — 미달 (92).
- [x] **PASS** — Phase 7a-2 Option B+ Planner-directed micro-fix path 종료. CLAUDE.md "Round 2 cap + Planner directive override" 적용. R3 cross-verify 금지 명시 (Planner). push 진행 권장.
- [ ] FAIL → RE-PLAN

Stage 6: commit V3 changes + summary v2 update + push + CI green 확인.
