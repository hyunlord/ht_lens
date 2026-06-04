# Phase 8e-7 — Summary (split-extract 병합 ingest CLI — F3 unblock)

## Status
**PASS_CANDIDATE — cross-verify R2 CONFIRM_PASS (95).** F3(book2 1370p) 12h cap
timeout을 분할추출로 풀기 위한 **재사용 병합 ingest 도구** 구축 완료. 머지 전 GATE(Planner 승인).

## Score
- Self: **95 / 100** (v2 + post-R2 polish)
- Cross-verdict: R1 **DOWNGRADE 91-92** → RE-CODE → R2 **CONFIRM_PASS 95**.

## What was built (0 DB schema, 기존 단일 ingest 불변)
GATE 승인 설계대로 — 병렬 ingest 경로 없이 **merge → 기존 `ingest_mineru_output` 재사용**:
1. **`merge.py`**: `offset_items`(page_idx += 누적 part page_count, OOB/non-int reject, 이미지
   `part<NNN>__base` namespace) + `build_merged_output`(N 파트 → 단일 MinerU-shaped dir:
   merged content_list + namespaced images + **full-PDF provenance origin** + page-count 검증).
2. **`ingest-mineru-multi` CLI**: 파트 발견(`discover_part`, page_count=origin.pdf) → merge →
   `ingest_mineru_output`(schema/overwrite/rollback/1.x/이미지정리 invariant 자동 승계).
3. **좌표/provenance**: merged page_idx = full PDF 절대 페이지; provenance = full book2.pdf →
   detect-repairs/repair-images가 절대 페이지 clip(part origin 오용 차단).
4. **split**: ops 1회성(PyMuPDF) — CLI 미신설(merge만 자산).

## Files changed (vs main, +743)
```
 src/ht_lens/ingest_mineru/merge.py  | 195 +  (offset/namespace/provenance/page-count·JSON·PDF 검증)
 src/ht_lens/cli.py                  |  95 +  (ingest-mineru-multi)
 tests/unit/test_merge.py            | 183 +  (10: offset/경계/dup/빈파트/provenance/mismatch/JSON/PDF)
 tests/integration/test_merge_cli.py | 270 +  (6: 2-part/single-equiv/provenance/all-chrome/overwrite/wrong-pdf)
```
**0** DB / migration / model 변경. 기존 `ingest-mineru` 동작·시그니처 불변.

## Verification evidence
- ruff/format/mypy(87) clean · `pytest -q`: **866 passed, 8 skipped, 0 failed**.
- 핵심 정합(합성 hermetic): 경계 연속(part1 page_count 직후 part2 시작), page_idx 단조, Σchunk,
  빈파트 offset 유지, all-empty reject, namespace 충돌 0+서빙, provenance=full PDF(detect-repairs
  exit 0), 단일=기존 동치, overwrite 교체, wrong/corrupt source-pdf reject.

## Cross-verify 잔여 (R1 해소 + R2 confirm)
- R1: full-PDF page_count 미검증 → Σpart==source 검증; overwrite 미테스트 → 추가; part JSON raw
  예외 → IngestError 래핑. 전부 테스트.
- R2 CONFIRM_PASS: minor #1(corrupt source-pdf) → IngestError 래핑+테스트(`d62c277`).

## Deviations from plan
- 원 plan의 병렬 `ingest_mineru_multi` → debate/challenge로 **merge→기존 ingest 재사용**(8a 회귀
  위험 회피). 이미지 sha256 가정 → part-namespace. split CLI → ops. (challenge R1~R6.)

## Known issues / debt
- **CI green**: push 후 확정.
- **실 book2 분할추출**: F3 재개에서(이 phase는 도구 — 합성 hermetic 검증).
- **source-pdf 동일성**: page_count만 검증 → 같은 page_count의 *다른* PDF는 미탐지(operator
  계약; Codex R2 "document rather than fix"). 향후 sha/내용 검증 여지.
- **part 순서**: CLI 인자 순서 = 계약(검증은 page-count 합만). operator 주의.

## Planner decision needed (merge GATE)
R2 = CONFIRM_PASS 95. challenge R1~R6 충실 구현, R1 3건+R2 polish 테스트 잠금, 0 DB·단일 ingest
불변. **권고: main merge 승인**(prod 무관 — 신규 CLI, 서빙 변경 0). 승인 시:
`merge --no-ff → CI green → (prod restart 불요)`. 그 다음 **F3 재개**(GATE 4 후속): book2.pdf
0-684/685-1369 분할 → 각 extract-mineru(<12h) → `ingest-mineru-multi` 병합 → 번역/임베딩/backfill
→ doc1 숨김 → 6-doc RAG. (각 단계 GATE 유지.)

## Recommended next
- 승인 시: merge + CI green (prod restart 불요).
- F3 재개: split(ops) → extract-mineru ×2(순차) → ingest-mineru-multi → translate(conc 3) →
  detect-repairs(repair 게이트) → backfill → doc1 숨김 → cross-doc RAG 검증. 단계별 GATE.
