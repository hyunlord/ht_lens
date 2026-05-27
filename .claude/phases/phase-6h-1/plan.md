# Phase 6h-1 — Pattern A Fix (V2, post Codex debate)

> **V1 → V2 changelog**: Codex critique 11 ACCEPT / 3 PARTIAL / 1 REJECT. Critical fixes:
> 1. `_should_concat_inline` 가 `RawLine.direction` 무시 → rotation 회귀 위험 (Codex §3.3 ACCEPT)
> 2. Header detection이 raw line count → 3-fragment header 누락 (Codex §2.4 ACCEPT)
> 3. Backfill partial commit → hybrid doc 위험 (Codex §3.4 ACCEPT)
> 4. KPI test 부재 (Codex §5 ACCEPT)
> 5. Embedding stale 보장 false claim → manual refresh 가이드 (Codex §2.3 ACCEPT)
> 6. Hot-fix A1 제거 본 phase에서 빼고 후속 작업 (Codex §1.3 ACCEPT)
> 7. Threshold 50% → 60% + height similarity (Codex §3.1 ACCEPT)
> 8. Backfill `--all` 제거, PDF path 명시 (Codex §1.2 PARTIAL)
> 9. Alembic 0005 명시적 거부 (스키마 변동 없음, Codex §2.1 ACCEPT)
> 10. ROADMAP audit reproducibility 추가 (Codex §2.2 ACCEPT)

## Goal
PDF extraction에서 같은 visual line의 텍스트가 두 PyMuPDF "lines"로 분리되는 경우 `blocks.py`가 `\n.join(...)`으로 합쳐 multi-line text + single-line bbox로 저장하던 문제 fix. 본 fix는 **stored text format** 정상화가 main effect; bbox는 `_union(...)` 이 이미 옳음 (y 동일이면 height 그대로). 사용자가 viewer에서 인지하던 줄바꿈 + 작은 폰트 + downstream RAG/chat의 잘못된 줄 분할 해소.

## Context (요약, V1 plan 참조)

### 확정된 mechanism (doc 7 page 862 PyMuPDF probe)
- PyMuPDF가 horizontal gap이 큰 텍스트를 두 "lines"로 split, 둘 다 같은 y range
- `blocks.py:108` `\n.join(...)`이 잘못 합쳐 multi-line text 생성
- 사용자가 viewer에서 본 page 862의 영어 누출은 **Pattern B (본문 추출 누락)**가 원인이지 Pattern A 아님 — 하지만 Pattern A도 별도 fix 가치 있음 (downstream contamination)

### 사용자 결정 (Stage 1)
- A: Y-overlap 감지 + space join
- B: Backfill script 따로 (auto 안 함)
- C: Unit + sample PDF smoke
- D: Hot-fix A1 제거는 **본 phase 외** (Codex §1.3 적용)

## Scope

**In**:

### Sub-goal 1 — `blocks.py` Y-overlap 감지 + space join (rotation-safe)

새 helper `_should_concat_inline(prev, cur) -> bool`:
```python
def _should_concat_inline(prev: RawLine, cur: RawLine) -> bool:
    """Detect two PyMuPDF "lines" that are actually one visual line.

    Y-overlap >= 60% AND height-similarity 30% AND both horizontal.
    """
    # Rotation safety (Codex §3.3): only join horizontal lines.
    if not _is_horizontal(prev) or not _is_horizontal(cur):
        return False
    py0, py1 = prev.bbox[1], prev.bbox[3]
    cy0, cy1 = cur.bbox[1], cur.bbox[3]
    prev_h = max(py1 - py0, 1e-6)
    cur_h = max(cy1 - cy0, 1e-6)
    # Height-similarity (Codex §3.1): exclude superscript/subscript.
    ratio = min(prev_h, cur_h) / max(prev_h, cur_h)
    if ratio < 0.7:  # >30% height diff
        return False
    overlap = max(0.0, min(py1, cy1) - max(py0, cy0))
    return overlap >= 0.6 * min(prev_h, cur_h)
```

`_join_lines(lines)` (new helper):
```python
def _join_lines(lines: list[RawLine]) -> str:
    if not lines:
        return ""
    parts = [_line_text(lines[0]).rstrip()]
    for prev, cur in pairwise(lines):
        sep = " " if _should_concat_inline(prev, cur) else "\n"
        parts.append(sep + _line_text(cur).rstrip())
    return "".join(parts).strip()
```

`_count_visual_lines(lines)` (Codex §2.4 — header semantic count):
```python
def _count_visual_lines(lines: list[RawLine]) -> int:
    if not lines:
        return 0
    n = 1
    for prev, cur in pairwise(lines):
        if not _should_concat_inline(prev, cur):
            n += 1
    return n
```

`group_page` 변경:
- text join: `text = _join_lines(para_lines)` (대신 `\n.join`)
- header check: `len(para_lines) <= _HEADER_MAX_LINES` → `_count_visual_lines(para_lines) <= _HEADER_MAX_LINES`
- bbox: `_union(...)` 그대로 (변경 없음)

### Sub-goal 2 — Tests (unit + smoke + KPI + header regression)

**Unit** (`tests/unit/test_extract_blocks_inline_join.py`, 6 tests):
1. `test_single_line_block_unchanged`
2. `test_y_overlap_lines_joined_with_space`
3. `test_y_distinct_lines_joined_with_newline`
4. `test_should_concat_inline_threshold_60pct` (49%/61% 경계)
5. `test_should_concat_inline_rejects_non_horizontal` (rotation safety, Codex §3.3)
6. `test_should_concat_inline_rejects_height_mismatch` (superscript-like 50% height ratio, Codex §3.1)

**Header regression** (`tests/unit/test_extract_blocks_header_visual_lines.py`, 2 tests):
7. `test_header_split_into_3_horizontal_fragments_still_classified_as_header` (visual count = 1)
8. `test_multi_line_real_title_above_HEADER_MAX_LINES_demoted_to_text` (visual count = 3 → text)

**KPI synthetic** (`tests/integration/test_phase_6h1_kpi.py`, 1 test):
9. `test_pattern_a_fix_collapses_inline_split_lines`: synthetic page with N pre-fix Pattern A patterns → after group_page, K of them collapse to space-joined visual lines. Demonstrate root-cause fix on logic level (ROADMAP audit metric requires real PDFs + backfill).

**Smoke** (`tests/integration/test_extract_inline_join_smoke.py`, 1 test):
10. `test_inline_join_smoke_pdf`: in-memory PDF, two text pieces at same y, different x → extract → block text is space-joined.

**Backfill atomicity** (`tests/integration/test_backfill_atomicity.py`, 1 test):
11. `test_backfill_aborts_doc_on_any_page_mismatch`: doc with one page block-count mismatch → no DB writes happen (transaction rollback).

총 11 new tests.

### Sub-goal 3 — Backfill script

`scripts/backfill_block_text.py`:
- CLI: `--doc-id N --pdf <path> [--dry-run]`
- `--all` **제거** (Codex §1.2)
- Per-doc atomic (Codex §3.4): 한 page라도 mismatch → 전체 abort (rollback), 사용자가 확인 후 재실행
- Block matching: page_num + order_idx + bbox center proximity (< 20pt drift)
- 매칭 성공 → `UPDATE blocks SET bbox_json=?, original_text=? WHERE id=?` (block_id 보존)
- 매칭 실패 → 전체 doc skip + summary 출력
- **사용자 가이드** (Codex §2.3): script 종료 시 다음 메시지 출력:
  > "Block text updated. Stored block_embeddings may be stale for affected blocks. Run `ht-lens embed --doc-id N` to refresh (Phase 7a auto-detects source_hash mismatch)."

### Sub-goal 4 — KPI documentation (Codex §2.2)

Plan V2의 DoD에 정직 명시:
- 본 phase commit만으로는 audit metric (6,912 → ?) 변화 0 — extraction logic 변경은 **새 doc upload + 기존 doc backfill** 시점에만 적용
- Backfill 후 audit 재실행 시 KPI 측정 가능
- KPI test (test 9)는 logic 정확성 증명 (synthetic), real metric은 backfill ops 후

**Out** (V1과 동일 + 추가):
- Hot-fix A1 제거 (별도 후속, Codex §1.3)
- Pattern B (Phase 6h-2)
- Gas C (Phase 6h-3)
- DB schema 변경 / Alembic 0005 (스키마 변동 없음 — Codex §2.1, ROADMAP 수정 권장)
- API contract 변경
- Frontend `fitFontSize` 변경 (root cause는 backend extraction)
- 자동 backfill (사용자 manual 호출)
- 자동 embedding refresh (사용자 manual `ht-lens embed`)
- Span/word level y-clustering (Codex §4.1 REJECT, 사용자 결정 A 우선)

## Approach

### 1. blocks.py 변경 (3 helpers + group_page)

Helper functions: `_should_concat_inline`, `_join_lines`, `_count_visual_lines` (위 코드 참조).

`group_page` 변경 2곳:
- 기존 `text = "\n".join(_line_text(ln).rstrip() for ln in para_lines).strip()` → `text = _join_lines(para_lines)`
- 기존 `len(para_lines) <= _HEADER_MAX_LINES` → `_count_visual_lines(para_lines) <= _HEADER_MAX_LINES`

`_union(...)` 그대로 (y 동일이면 height 동일, x-union으로 너비 확장 — 이미 옳음).

### 2. Backfill script (per-doc atomic)

```python
async def backfill_doc(
    factory: async_sessionmaker[AsyncSession],
    doc_id: int,
    pdf_path: Path,
    dry_run: bool,
) -> dict:
    # 1. Load doc + existing blocks per page
    async with factory() as session:
        doc = await session.get(Document, doc_id)
        if doc is None:
            raise ValueError(f"doc {doc_id} not found")
        # ... load blocks ...

    # 2. Re-extract with new logic
    new_pages = list(_extract_grouped_pages(pdf_path))

    # 3. Pre-validate (no writes yet): all pages must have matching block count + bbox proximity
    proposed_updates: list[tuple[int, list[float], str]] = []
    for new_page in new_pages:
        old = db_pages_by_num.get(new_page.page_num)
        if old is None:
            return {"status": "abort", "reason": f"DB missing page {new_page.page_num}"}
        if len(old) != len(new_page.blocks):
            return {"status": "abort", "reason": f"block count mismatch at page {new_page.page_num}"}
        old_sorted = sorted(old, key=lambda b: b.order_idx)
        new_sorted = list(enumerate(new_page.blocks))  # provisional order
        for (ob, (_, nb)) in zip(old_sorted, new_sorted):
            ocx, ocy = _center(ob.bbox)
            ncx, ncy = _center(nb.bbox)
            if abs(ocx - ncx) > 20 or abs(ocy - ncy) > 20:
                return {"status": "abort", "reason": f"bbox drift at page {new_page.page_num} block {ob.id}"}
            proposed_updates.append((ob.id, list(nb.bbox), nb.text))

    if dry_run:
        return {"status": "dry_run", "would_update": len(proposed_updates)}

    # 4. Single transaction: all-or-nothing
    async with factory() as session:
        for blk_id, bbox, text in proposed_updates:
            await session.execute(
                update(Block).where(Block.id == blk_id)
                .values(bbox_json=json.dumps(bbox), original_text=text)
            )
        await session.commit()
    print("[backfill] Block text updated. Stored block_embeddings may be stale.")
    print(f"[backfill] Run 'ht-lens embed --doc-id {doc_id}' to refresh (auto source_hash detect).")
    return {"status": "ok", "updated": len(proposed_updates)}
```

### 3. Embedding refresh 가이드 (Codex §2.3)

Backfill script print 외에:
- summary.md에 "Backfill 후 embed refresh" section
- ROADMAP 또는 README 가이드 (사용자 영역, 본 phase 외)

### 4. Hot-fix A1 제거 (본 phase 외)

V2 plan에서 명시: 본 phase에 미포함. 별도 후속 작업.

## File-level changes

| Path | Action | Note |
| ---- | ------ | ---- |
| `src/ht_lens/extract/blocks.py` | MODIFY | `_should_concat_inline`, `_join_lines`, `_count_visual_lines` 추가. text join + header check 변경 |
| `tests/unit/test_extract_blocks_inline_join.py` | NEW | 6 unit tests |
| `tests/unit/test_extract_blocks_header_visual_lines.py` | NEW | 2 header regression tests |
| `tests/integration/test_phase_6h1_kpi.py` | NEW | 1 KPI logic test (synthetic) |
| `tests/integration/test_extract_inline_join_smoke.py` | NEW | 1 smoke test (in-memory PDF) |
| `tests/integration/test_backfill_atomicity.py` | NEW | 1 backfill atomicity test |
| `scripts/backfill_block_text.py` | NEW | Backfill 도구 (atomic per-doc, dry-run) |

## Dependencies (new)
없음.

## Test strategy

총 11 new tests (위 Sub-goal 2 참조). 회귀 0 — 기존 533 tests 통과 (특히 `test_rotated_page.py`, `test_extract_*.py`).

## DoD mapping

| DoD item | How to satisfy | Evidence plan |
| -------- | -------------- | ------------- |
| Same-visual-line text는 space join | `_should_concat_inline` + `_join_lines` | unit test 2 |
| Distinct-visual-line text는 `\n` join | 동일 helper | unit test 3 |
| Single-line block 무영향 | 그대로 | unit test 1 |
| Threshold 60% + height-similarity | conditional | unit tests 4, 6 |
| Rotation safety | direction check | unit test 5 + 기존 rotation tests |
| Header 보존 (visual count) | `_count_visual_lines` | header tests 7, 8 |
| KPI demonstrable (logic level) | synthetic input fix → expected output | KPI test 9 |
| Backfill per-doc atomic | pre-validate before commit | atomicity test 11 |
| Embedding refresh manual guide | backfill script print | summary.md |
| 533 → 544+ tests | 11 new | full pytest |
| ROADMAP §6h-1 Alembic 0005 거부 명시 | 스키마 변동 없음 | summary.md 권장 |
| Hot-fix A1 제거 → 별도 후속 | 본 phase 외 | summary.md |

## Risk / 주의

### Critical (V1 hazards resolved)
1. ~~Rotation 무시~~ → direction check (Codex §3.3 ACCEPT)
2. ~~Header miscount~~ → `_count_visual_lines` (Codex §2.4 ACCEPT)
3. ~~Backfill hybrid doc~~ → pre-validate + atomic (Codex §3.4 ACCEPT)
4. ~~Embedding stale claim 거짓~~ → manual refresh 가이드 (Codex §2.3 ACCEPT)
5. ~~KPI 측정 부재~~ → KPI test 추가 (Codex §2.2 ACCEPT)
6. ~~Threshold edge cases~~ → 60% + height similarity (Codex §3.1 ACCEPT)

### Medium
7. **PyMuPDF version 의존**: `get_text("dict")` schema 안정성. 현재 dependency 확인.
8. **Block count 변경 가능성**: 새 vs 기존 logic block 수 다를 수 있음. Atomic abort 보장.
9. **Backfill 후 embed refresh 의무**: 사용자가 잊으면 RAG 일부 stale. 명시적 가이드 + script print.

### Low
10. **Multi-column 같은 y 다른 paragraph**: `_group_lines_into_paragraphs`가 vertical gap 기준이라 다른 paragraph로 분리. Join은 paragraph 내부만 → 영향 없음.
11. **공백 정규화**: line `.rstrip()` 호출되므로 space join 시 1개만.

### Debate 후 잔여 (verify-cross에서 다시 검토)
- Threshold 60% / height similarity 30% 값 적정성 (실 PDF에서 false positive/negative 측정 가능?)
- Backfill 매칭 실패 시 사용자 가이드 (skip vs manual fix vs re-ingest)
- KPI test (test 9)가 real-world audit과 어떻게 mapping되는지
