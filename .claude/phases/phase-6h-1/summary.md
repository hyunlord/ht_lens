# Phase 6h-1 — Summary

## Status
**ESCALATE TO PLANNER** — Codex Round 2 verdict: DOWNGRADE (~70/100) with explicit guidance: *"not another hard REJECT, should go to Planner as not pass-ready on evidence rather than blind RE-CODE loop"*. CLAUDE.md Round 2 cap reached → push 보류, Planner directive 대기.

코드 product는 직접적인 root-cause fix:
- Pattern A (same-visual-line text joined with `\n`) 의 mechanism이 PyMuPDF probe로 확정, `blocks.py`의 Y-overlap detection + space-join + visual-line header count로 fix
- 3 sample PDF snapshot 직접 변화 확인 (`"1\nIntroduction"` → `"1 Introduction"` 등)
- Codex critical 5개 (debate) + R1 concrete 3개 (cross-verify) 모두 fix
- 549 tests pass (533 → 549, +16 new/updated), lint + format + mypy clean

잔여 항목 (Codex R2):
- Abort tests가 `(id, original_text)` 만 snapshot — `bbox_json` 변경도 무동작 보장하면 더 견고
- Apply test가 정확한 repaired payload (text/bbox 값) 검증 안 함
- CLI public surface (`_async_main` exit codes, stderr, stdout) 테스트 부재
- ROADMAP DoD direct evidence (real-PDF backfill로 6,912 → ?) 미측정
- runtime stale-candidate hole (`embedding/search.py`) 별도 phase scope

## Score

| | Self V1 → V2 | Codex R2 audit |
| --- | --- | --- |
| 독창성 | 13 → 12/15 | 12/15 confirm |
| 완결성 | 30 → 25/35 | 22/35 (ROADMAP DoD direct evidence + repair payload 미증명) |
| 안정성 | 27 → 24/30 | 21/30 (CLI surface untested + abort tests bbox_json 검증 부재) |
| 확장성 | 18 → 16/20 | 15/20 (stale-candidate coupling) |
| **Total** | **88 → 77/100** | **~70/100** |

Codex R2 verdict: DOWNGRADE (not REJECT). Round 2 cap.

## What was built

### Sub-goal 1 — `blocks.py` Y-overlap inline join ✅
`src/ht_lens/extract/blocks.py`:
- `_should_concat_inline(prev, cur)`: horizontal direction + 60% Y-overlap + 30% height-similarity 통과 시 same visual line 판정
- `_join_lines(lines)`: paragraph 내부에서 same-visual-line은 ` ` join, 다른 visual line은 `\n` join
- `_count_visual_lines(lines)`: header heuristic에서 raw line count 대신 visual line count
- `group_page`: text join + header check 두 곳 수정. `_union` bbox 그대로

### Sub-goal 2 — Tests (+16: 13 V1 + 3 R1)
- Unit (7): inline-join helpers (single-line, y-overlap, y-distinct, threshold 60%, rotation-safe, height-mismatch, 3-piece)
- Unit (2): header visual-line count regression
- Integration (2 KPI): 50 Pattern A collapse, 30 multi-line preserve `\n`
- Integration (1 smoke): in-memory PDF (PyMuPDF가 separate blocks 분리 시 skip-with-diagnostic)
- Integration (4 atomicity): count-mismatch abort, **R1**: PDF-missing-pages abort, bbox-drift abort, successful apply

### Sub-goal 3 — Backfill script ✅
`scripts/backfill_block_text.py`:
- `--doc-id N --pdf <path> [--dry-run]`
- per-doc atomic: 모든 page validate (block count + bbox center within 20pt + DB-only page check) 후 commit
- block_id 보존 (translation / embedding 무영향)
- 종료 시 `ht-lens embed --doc-id N` 가이드 출력

### Snapshot update (+ 부산물)
3개 sample PDF snapshot에서 `"1\nIntroduction"` → `"1 Introduction"` 등 inline-collapse 확인 (612 lines 변경, 121 insertion 491 deletion — stored text format 정상화 직접 증거).

## Files changed
```
.claude/phases/phase-6h-1/{plan,debate,challenge,verify,verify-cross,summary}.md
src/ht_lens/extract/blocks.py                              |  76 +/-
tests/integration/__snapshots__/test_extract_snapshot.ambr | 612 +/-
tests/unit/test_extract_blocks_inline_join.py              | 123 + (NEW)
tests/unit/test_extract_blocks_header_visual_lines.py      |  84 + (NEW)
tests/integration/test_phase_6h1_kpi.py                    |  90 + (NEW)
tests/integration/test_extract_inline_join_smoke.py        |  61 + (NEW)
tests/integration/test_backfill_atomicity.py               | 339 + (NEW)
scripts/backfill_block_text.py                             | 271 + (NEW)
```
Total: 14 files changed, 1768 insertions(+), 493 deletions(-).

## Deviations from plan

### V1 → V2 (after Codex debate, 11 ACCEPT / 3 PARTIAL / 1 REJECT)
1. Rotation safety: direction check in `_should_concat_inline`
2. Header detection: `_count_visual_lines` 도입
3. Backfill per-doc atomic (전 page validate 후 commit)
4. Threshold 50% → 60% + height-similarity 30%
5. KPI synthetic test 추가
6. Embedding stale: manual refresh 가이드 (가이드 only, runtime fix 별도)
7. Hot-fix A1 제거 본 phase 외
8. Backfill `--all` 제거, PDF path 사용자 명시
9. Alembic 0005 명시적 거부 (스키마 변동 없음)
10. ROADMAP audit reproducibility 추가 (KPI test)

### V2 → R1 RE-CODE (after Codex verify-cross R1 REJECT)
11. Backfill DB-only page-set 검증 추가 (`db_only` set check)
12. `test_backfill_aborts_when_pdf_missing_pages_db_has` 추가
13. `test_backfill_aborts_on_bbox_drift` 추가
14. `test_backfill_apply_succeeds_when_pdf_matches_db` 추가

## Codex Round 2 잔여 항목 (Planner 검토)

### A. Test rigor 향상 (R2 §4)
- A1. Abort tests가 `bbox_json` snapshot 누락 — 잠재 regression 못 catch. (Codex R2 §4 #2)
- A2. Apply test가 exact repaired payload (text/bbox values) 검증 안 함. status='ok' + ID 보존만 확인. (Codex R2 §4 #3)
- A3. CLI public surface (`_async_main`, `main`) 미테스트 — exit code, stderr, stdout contracts. (Codex R2 §4 #4)

### B. DoD direct evidence (R2 §2)
- B1. Real PDF backfill로 KPI metric (6,912 → ?) 측정 없음. doc 7 dry-run은 page coverage drift로 abort.
- B2. ROADMAP "Alembic 0005" 항목 미충족 (스키마 변동 0이지만 ROADMAP wording 그대로 — 사용자 ROADMAP 수정 필요).

### C. 별도 phase / 후속 작업 (R2 §4 #1 명시 acknowledge)
- C1. Runtime search stale-candidate hole: `embedding/search.py::load_all()`는 source_hash 검증 없이 모든 stored vector 사용. Backfill 후 `original_text` 변경된 block의 stored embedding은 stale. Phase 7a follow-up 영역.
- C2. Hot-fix A1 (warning border) 제거 — Phase 6h-1 fix는 새 extract / backfill 시점에만 적용되므로 옛 doc에서 A1는 여전히 유용. 별도 후속 작업.

## Recommended next (Planner 결정 항목)

### 옵션 1: Planner-directed micro-fix (Phase 7a-2 V3 Option B+ precedent)
- A1/A2/A3 fix: test rigor 강화 (3-4 시간 추가 작업)
- verify.md V3 + push + CI

### 옵션 2: 즉시 push + 별도 follow-up phase
- 현재 product는 직접 root-cause fix 완료, regression 0
- 추가 test rigor는 Phase 6h-1b 또는 별도 작업
- B1 (real backfill) 은 doc 별 manual ops 후 evidence 첨부

### 옵션 3: RE-CODE round 3 (CLAUDE.md 권장 안 함 — Codex 자체가 "not blind RE-CODE loop" 명시)

### Human/Planner 위임 (별도)
- ROADMAP §6h-1 "Alembic 0005" wording 수정 (스키마 변동 없음 명시) — 사용자 직접
- Pattern B (Phase 6h-2): body extraction missing — 별도 phase
- Gas C (figure caption): 별도 phase
- Phase 7a-3 시 발견된 runtime stale-candidate hole — 별도 phase

## Evidence index

- plan: `.claude/phases/phase-6h-1/plan.md` (V1 → V2)
- debate: `.claude/phases/phase-6h-1/debate.md` (Codex 15+ issues)
- challenge: `.claude/phases/phase-6h-1/challenge.md` (11 ACCEPT, 3 PARTIAL, 1 REJECT, decision RE-PLAN)
- verify: `.claude/phases/phase-6h-1/verify.md` (V1 88 → V2 77 honest, R1 fix lock evidence)
- verify-cross: `.claude/phases/phase-6h-1/verify-cross.md` (R1 REJECT → RE-CODE → R2 DOWNGRADE → escalate)
- git log: `d38a379 → 5e40c41` (10 commits in this phase)

## Known issues / debt

- abort tests `bbox_json` snapshot 부재 (R2 §4 #2, A1)
- apply test exact payload 검증 부재 (R2 §4 #3, A2)
- CLI public surface 테스트 부재 (R2 §4 #4, A3)
- Real PDF backfill direct evidence 없음 (B1)
- Runtime search stale-candidate hole (C1)
- A1 warning border 제거 후속 (C2)
- ROADMAP Alembic 0005 wording mismatch (B2)

## Push 정책

CLAUDE.md WORKFLOW: "Round 2 REJECT/DOWNGRADE → push 보류, Planner escalate". 본 phase는 **Codex R2 explicit "not blind RE-CODE loop"** 표현으로 Planner 결정 path 권장.

- Option A (보수): push 보류 → Planner directive 대기
- Option B+ (Planner-directed micro-fix, Phase 7a-2 precedent): A1/A2/A3 fix + verify V3 → push
- Option C: 사용자 직접 push override

Stage 6 push는 Planner directive 대기.
