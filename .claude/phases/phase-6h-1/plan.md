# Phase 6h-1 — Pattern A Fix (Same-visual-line text joined with `\n`)

## Goal
PDF extraction에서 같은 visual line의 텍스트를 두 PyMuPDF "lines"로 받는 경우 `blocks.py`가 `\n.join(...)`으로 합쳐 multi-line text + single-line bbox로 저장하던 문제 fix. 사용자가 viewer에서 PDF 영어 누출 (Pattern A) 로 인지하던 6,912 blocks (15.5%) 의 root cause 해소.

## Context

### 2026-05-27 진단 + 2026-05-28 PyMuPDF 직접 probe로 root cause 확정

**확정된 mechanism** (doc 7 page 862 block 2 사례):
- PyMuPDF `get_text("dict", sort=True)` 결과:
  - line 0: bbox=[77.0, 61.5, 108.8, 72.4] text="22.4.3"
  - line 1: bbox=[121.3, 61.5, 222.2, **72.4**] text="Other applications"
  - **두 line의 y 범위가 동일** (y=61.5-72.4)
- 즉 PDF에서 "22.4.3 ... Other applications" 가 한 visual line인데 PyMuPDF가 horizontal gap을 기준으로 2개의 line으로 split
- `blocks.py:108` 의 `text = "\n".join(...)` 가 두 piece를 `\n`로 연결 → stored text = `"22.4.3\nOther applications"`
- `_union(...)` 의 y는 단일 line range → stored bbox height ~11pt (single-line)
- Frontend `fitFontSize`가 stored text의 `\n`을 두 visual line으로 해석 → 1줄 bbox에 2줄 squeeze → 작은 font + 좁은 overlay
- 다행히 bbox의 x-union은 visual line 전체를 cover → PDF underneath 그대로 가려짐. **실제 visual leak은 발생 안 함** (audit이 측정한 6,912는 _potential_ leak)
- 단 사용자가 viewer에서 인지하는 "이상한 줄바꿈" + 작은 폰트 + 다른 page의 진짜 Pattern B 와 혼동 가능

**Real-world impact**:
- 본 문제 자체는 visual leak 보다 **stored text가 잘못된 format** (의미상 단일 line인데 `\n` 포함). 이는 RAG embedding, search, chat context 등 downstream에서 "두 줄"로 처리되는 contamination.
- 또한 frontend fitFontSize의 잘못된 줄수 계산 → 작은 폰트로 가독성 저하.
- 사용자 보고한 "page 862 영어 누출" 의 직접 원인은 Pattern B (body extraction missing) 임. Pattern A는 별도 issue지만 함께 처리.

### 사용자 결정 (Stage 1)
- **A**: Y-overlap 감지 후 space로 join (root cause 정확 fix, 최소 변경)
- **B**: Backfill script 따로 제공 (자동 실행 안 함)
- **C**: Unit + sample PDF smoke
- **D**: Hot-fix A1 (warning border) — Phase 6h-1 fix 후 제거

## Scope

**In**:

### Sub-goal 1 — `blocks.py` Y-overlap join
- `_group_lines_into_paragraphs` 그대로 (line 그룹화는 정상), `group_page` 안 text 결합만 fix
- 새 helper `_should_concat_inline(prev_line, cur_line) -> bool`:
  - 두 RawLine bbox의 Y 범위가 50%+ 겹치면 same visual line → True
  - 50% 미만이면 multi-line content → False
- text 결합 로직 변경:
  ```python
  # 기존:
  text = "\n".join(_line_text(ln).rstrip() for ln in para_lines).strip()
  # 신규:
  text = _join_lines(para_lines)  # space if y-overlap, else "\n"
  ```
- 결과: `"22.4.3\nOther applications"` → `"22.4.3 Other applications"` (한 줄로 통합).

### Sub-goal 2 — Tests (unit + sample PDF smoke)
- 새 `tests/unit/test_extract_blocks_inline_join.py`:
  - `test_single_line_block_unchanged`: 한 RawLine paragraph → text/bbox 동일
  - `test_y_overlap_lines_joined_with_space`: 두 RawLine y 동일 → text는 space, bbox는 x-union (height 동일)
  - `test_y_distinct_lines_joined_with_newline`: 두 RawLine y 다른 줄 → `\n` join (기존 동작 보존)
  - `test_should_concat_inline_threshold`: y-overlap 49%/51% 경계 검증
- `tests/integration/test_extract_inline_join_smoke.py`:
  - `fitz.open()` in-memory PDF에 같은 y의 두 text piece 삽입
  - `iter_pages` → `group_page` 끝까지 → 결과 GroupedBlock 검증

### Sub-goal 3 — Backfill script
- 새 `scripts/backfill_block_bbox.py`:
  - `--doc-id N` 또는 `--all`
  - `--dry-run` 옵션 (실 update 없이 매칭 결과만 출력)
  - PDF path: `--pdf-base-dir <path>` (default `/home/hyunlord/pdfs_to_test`)
  - 각 doc:
    1. `Document.src_pdf_sha256` 또는 `filename`으로 PDF path 결정
    2. 새 extract logic으로 GroupedBlock 재계산
    3. 기존 DB block과 매칭: page_num + order_idx + bbox center proximity
    4. 매칭 성공 → `UPDATE blocks SET bbox_json=?, original_text=? WHERE id=?`
    5. 매칭 실패 (block 수 변동) → 보고 + 해당 doc skip
  - block_id 보존 → translation rows, block_embeddings 무영향
  - bbox / original_text만 update (block_local_id, type, order_idx, page_id 유지)

### Sub-goal 4 — Hot-fix A1 제거 (별도 commit, Phase 6h-1 fix 후)
- `block.js`의 `hasBboxOverflow` 호출 + helper 제거
- `viewer.css`의 `.block--overflow-warning` rule 제거
- 회귀 0 (cosmetic만)

**Out**:
- Pattern B (body extraction missing) — Phase 6h-2
- Gas C (figure caption) — Phase 6h-3
- DB schema 변경 (bbox_json/original_text만 update, schema 변동 없음)
- API contract 변경
- Frontend rendering 변경 (block.js fitFontSize 그대로)
- 새 PyMuPDF API 도입
- Alembic migration (스키마 변동 없음)

## Approach

### 1. blocks.py 핵심 변경

`_should_concat_inline(prev, cur)` (new helper):
```python
def _should_concat_inline(prev: RawLine, cur: RawLine) -> bool:
    """Return True iff two consecutive lines share the same visual line.

    PyMuPDF returns multiple ``lines`` for text that is visually on the
    same row when there is a horizontal gap (e.g., section number and
    section title separated by a tab). Both lines then have the same
    Y range, so the paragraph grouper accepts them but the naive
    ``\\n``-join produces multi-line text from single-line content.
    We treat any pair with >=50% Y-overlap as the same visual line and
    join their text with a single space instead.
    """
    py0, py1 = prev.bbox[1], prev.bbox[3]
    cy0, cy1 = cur.bbox[1], cur.bbox[3]
    overlap = max(0.0, min(py1, cy1) - max(py0, cy0))
    prev_h = max(py1 - py0, 1e-6)
    cur_h = max(cy1 - cy0, 1e-6)
    return overlap >= 0.5 * min(prev_h, cur_h)
```

`group_page` 안 text join 부분 (line 107-128 영역):
```python
# OLD:
text = "\n".join(_line_text(ln).rstrip() for ln in para_lines).strip()

# NEW:
def _join_lines(lines: list[RawLine]) -> str:
    if not lines:
        return ""
    out = [_line_text(lines[0]).rstrip()]
    for prev, cur in pairwise(lines):
        sep = " " if _should_concat_inline(prev, cur) else "\n"
        out.append(sep + _line_text(cur).rstrip())
    return "".join(out).strip()

text = _join_lines(para_lines)
```

`bbox` 계산은 그대로 `_union(...)` — same-visual-line case에서 x-union 옳음 (Y 동일이라 height 그대로 유지).

Header detection (`is_header`)의 `len(para_lines) <= _HEADER_MAX_LINES` 체크는 그대로 (PyMuPDF raw line 수). 동일 동작.

### 2. Backfill block matching

```python
async def backfill_doc(doc_id: int, pdf_path: Path, dry_run: bool) -> dict:
    # 1. Re-extract
    new_groups_per_page = list(iter_grouped_pages(pdf_path))
    # 2. Load DB blocks
    db_pages = await load_doc_blocks_by_page(doc_id)

    updates = []
    skipped = []
    for new_page in new_groups_per_page:
        old_blocks = db_pages.get(new_page.page_num, [])
        new_blocks = new_page.blocks
        if len(old_blocks) != len(new_blocks):
            skipped.append((new_page.page_num, len(old_blocks), len(new_blocks)))
            continue
        # Match by order_idx
        old_sorted = sorted(old_blocks, key=lambda b: b.order_idx)
        new_sorted = sorted(new_blocks, key=lambda b: b.order_idx_provisional)
        for old, new in zip(old_sorted, new_sorted):
            # Sanity: bbox center within 20pt drift
            old_cx, old_cy = _center(old.bbox)
            new_cx, new_cy = _center(new.bbox)
            if abs(old_cx - new_cx) > 20 or abs(old_cy - new_cy) > 20:
                skipped.append((new_page.page_num, 'bbox drift', old.id))
                break
            updates.append((old.id, new.bbox, new.text))

    if dry_run:
        return {"would_update": len(updates), "skipped_pages": skipped[:20]}
    async with factory() as session:
        for blk_id, bbox, text in updates:
            await session.execute(
                update(Block)
                .where(Block.id == blk_id)
                .values(bbox_json=json.dumps(list(bbox)), original_text=text)
            )
        await session.commit()
    return {"updated": len(updates), "skipped_pages": skipped[:20]}
```

매칭 안전성:
- block 개수 동일 시 order_idx 기반 (PyMuPDF `sort=True` 보장)
- bbox center drift > 20pt면 skip (의심)
- skip은 보고만, exception 없음 → 사용자 결정

### 3. Hot-fix A1 제거 (별도 commit)

Phase 6h-1 main commit + (optional) backfill 후 별도 commit:
- `src/ht_lens/api/static/js/components/block.js`: `hasBboxOverflow` 호출 + helper 제거
- `src/ht_lens/api/static/css/viewer.css`: `.block--overflow-warning` rule 제거
- 회귀 0 (cosmetic만)

## File-level changes

| Path | Action | Note |
| ---- | ------ | ---- |
| `src/ht_lens/extract/blocks.py` | MODIFY | `_should_concat_inline` helper 추가, `_join_lines` 도입, text join 로직 변경 |
| `tests/unit/test_extract_blocks_inline_join.py` | NEW | 4 unit tests |
| `tests/integration/test_extract_inline_join_smoke.py` | NEW | 1 smoke test (in-memory PDF) |
| `scripts/backfill_block_bbox.py` | NEW | Backfill 도구 (dry-run + apply) |
| (별도 commit) `src/ht_lens/api/static/js/components/block.js` | MODIFY | A1 warning helper 제거 |
| (별도 commit) `src/ht_lens/api/static/css/viewer.css` | MODIFY | A1 CSS rule 제거 |

## Dependencies (new)
없음.

## Test strategy

### Unit (`test_extract_blocks_inline_join.py`, 4 tests)
1. `test_single_line_block_unchanged`: 1 RawLine → text/bbox unchanged.
2. `test_y_overlap_lines_joined_with_space`: 2 RawLine y=10-20 → text=" " join, bbox y=10-20 (height unchanged).
3. `test_y_distinct_lines_joined_with_newline`: 2 RawLine y=10-20 / y=25-35 → text="\n" join, bbox y=10-35.
4. `test_should_concat_inline_threshold`: edge case 49% overlap False, 51% True.

### Integration (`test_extract_inline_join_smoke.py`, 1 test)
5. `test_inline_join_smoke_pdf`: in-memory PDF with two text piece at same y → iter_pages → group_page → block text has space, bbox single-line.

### 회귀 (existing 533)
- `tests/unit/test_extract_*.py` 가 있다면 모두 통과 유지.
- Multi-line content (y 다른) 케이스의 stored text format 동일.

## DoD mapping

| DoD item | How to satisfy | Evidence plan |
| -------- | -------------- | ------------- |
| Y-overlap text는 space join | `_should_concat_inline` + `_join_lines` | unit test 2 |
| Y-distinct text는 `\n` join (보존) | 동일 helper | unit test 3 |
| Single-line block 무영향 | 그대로 | unit test 1 |
| Bbox 정확 | `_union` 변경 없음 | tests 1/2/3 |
| Backfill script 동작 | `--dry-run` | manual smoke |
| Translation / embedding 보존 | block_id 유지 | backfill dry-run + manual check |
| 533 → 538+ tests | 5 new tests | `uv run pytest -m "not llm and not slow" -q --no-cov | tail -3` |
| Hot-fix A1 제거 (별도 commit) | block.js + viewer.css 정리 | 별도 commit |

## Risk / 주의

### Medium
1. **PyMuPDF version 의존**: `get_text("dict")` schema 변화 가능 (드물지만 major version). 현재 pyproject.toml에 pin 확인 필요.
2. **Block count 변경 가능성**: 이전 vs 새 logic block 수 동일하다는 보장 없음 (paragraph 그룹화 결과 동일하므로 합리적 기대). Backfill 매칭 실패 시 skip.
3. **Header heuristic 영향**: `len(para_lines) <= 2` 체크가 y-overlap lines 수로 판정. 예: "22.4.3 Other applications"는 2 PyMuPDF lines → header 후보 (현재 동작 일관).

### Low
4. **공백 정규화**: y-overlap join에서 space 1개 추가. line 별 `.rstrip()` 호출되므로 안전.
5. **Multi-column page**: 2-column 본문이 같은 y 범위에 다른 paragraph로 있어도 paragraph 그룹화가 vertical gap 기준이라 다른 paragraph → 같은 paragraph 내 join만 적용. 안전.
6. **RAG embedding 영향**: stored text 변경 (`\n` → ` `). `text_source_hash` 변경 → 일부 stored embedding stale. `embedding/backfill.py`가 source_hash mismatch 시 자동 refresh (Phase 7a 동작). 또는 backfill 후 `ht-lens embed --doc-id N` 강제 refresh 가능.

### Debate에서 다룰 질문
- 50% y-overlap 임계값 적정성 (superscript / subscript false positive?)
- `_should_concat_inline`이 PyMuPDF "lines" 정의와 일치하는지
- Backfill 시 block 개수 변동 정책 (skip vs partial vs reject doc)
- Header heuristic `len(para_lines) <= 2`가 y-overlap join 후에도 의미 일관한지
- Hot-fix A1 제거 타이밍 — Phase 6h-1 main commit 직후 vs backfill 완료 후
