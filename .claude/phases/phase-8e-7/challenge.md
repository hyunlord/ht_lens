# Phase 8e-7 — Challenge

Codex가 핵심을 잡음: (1) **병렬 ingest 경로 신설 금지** → raw content_list를 offset+concat해 **단일 merged content_list + namespaced images** 만든 뒤 **기존 `ingest_mineru_output()` 재사용**(schema/overwrite/rollback/1.x 공존 invariant 그대로). (2) **이미지 part-namespace**(픽스처가 `fig1.jpg` — sha256 가정 틀림, 다른-bytes 동일-basename 덮어쓰기 위험). (3) **full book2.pdf provenance**(repair 도구가 절대 페이지 clip하도록 markdown_path가 part1 origin 가리키면 안 됨). 대부분 accept → **PASS with revisions**(목표 유지, 접근을 재사용 중심으로 대폭 안전화).

## Debate responses
### 1. Over-engineering
- **accept (병렬 pipeline 폐기 → merge-then-reuse)**: `ingest_mineru_multi` 신설 대신 **raw content_list JSON offset+concat → 임시 merged `content_list.json` + 임시 `images/` → 기존 `ingest_mineru_output(merged_cl, …)` 1회 호출**. schema head/filename-scoped overwrite/rollback/이미지 정리/1.x 공존 전부 재사용(8a 회귀 위험 제거).
- **accept (이미지 part-namespace)**: basename = sha256 가정 폐기(픽스처 `fig1.jpg`). 각 파트 이미지를 `partNNN__<basename>`로 **namespace** 후 merged content_list의 img_path도 동일하게 rewrite → 다른-content 동일-basename 덮어쓰기 불가.
- **accept (split-pdf CLI 폐기)**: 분할은 **ops 1회성 스크립트**(PyMuPDF select). 재사용 자산 = **merge**(이번 phase 산출). split CLI는 반복사용 입증 후로 defer.

### 2. Hidden assumptions
- **accept (CRITICAL: repair provenance)**: merged doc의 `markdown_path`가 part1 dir(`*_origin.pdf`=part1)을 가리키면 page 900 repair가 잘못된 origin 사용. → **merge가 full book2.pdf를 provenance origin으로** 배치: 출력 dir에 `<stem>_origin.pdf` = **full book2.pdf**(복사/링크) + markdown_path 그곳. merged page_idx=절대 book2 페이지라 full PDF clip이 정확. detect-repairs/repair-images는 full PDF에서 절대 페이지 clip → 정합.
- **accept (part 순서 계약)**: `merge`는 **CLI 인자 순서 = 파트 순서** 명시 계약 + 각 파트 page_idx ∈ [0, part page_count) **경계 검증**(위반 reject). 순서/page-base 불일치 → double-offset 방지.
- **accept (split 페이지 속성)**: repair는 **full book2.pdf**에서 clip(part PDF 아님)이라 rotation/cropbox가 절대 페이지 기준으로 일관. `clip_render_figure`는 rotated skip 이미 보유. bbox는 파트 내 1000-정규화(절대 무관) 유지.
- **accept (page-range 혼동)**: 물리 분할 PDF만 사용(각 content_list page_idx 0-base dense). mineru `-s/-e`는 Out → double-offset 불가. 검증으로 page-base=0 확인.

### 3. Edge cases
- **accept (빈 파트)**: 파트가 0 chunk(blank/chrome만)여도 offset 수학 유지(merged concat). **merged 전체가 0 chunk면** 기존 `ingest_mineru_output`이 reject(`IngestError zero chunks`). 빈 중간/말미 파트 허용 + all-empty reject 테스트.
- **accept (page_idx out-of-bounds)**: page_count=3인데 page_idx=3 → **offset 전 reject**(DB write 없음).
- **accept (dup basename diff bytes)**: namespace로 충돌 0; 테스트로 잠금(`fig1.jpg`×2 → `part000__fig1.jpg`/`part001__fig1.jpg`).
- **accept (overwrite 계약)**: 기존 `ingest_mineru_output` 재사용이라 `filename==X ∧ extractor=='mineru'`만 교체 + cascade(chunks/translations/embeddings) + 이미지 정리 + 1.x 무손상 — 자동 보존.

### 4. Alternative approaches
- **accept (merge raw → reuse ingest)** = 채택(§1). page_idx offset + raw concat + 이미지 namespace-copy → 임시 content_list → 기존 ingest.
- **reject (mineru -s/-e + --page-offset)**: Planner "검증경로(물리 분할)" 결정 유지. (단 provenance 이점은 full-PDF origin 배치로 동등 확보.)
- **accept (namespace > basename 추론)**: part prefix namespace.

### 5. Missing tests — 채택
1. `test_multi_ingest_full_origin_pdf_for_repair`: merged doc provenance가 **full PDF** → detect-repairs/repair-images가 part1 origin 안 씀(절대 페이지 clip).
2. `test_merge_rejects_part_page_idx_out_of_bounds`: page_count=3 + page_idx=3 → DB write 전 실패.
3. `test_multi_ingest_allows_empty_part_rejects_all_empty`: 빈 파트 offset 유지 + all-chrome reject.
4. `test_multi_ingest_dup_basename_diff_bytes_namespaced`: 두 `fig1.jpg`(다른 bytes) 덮어쓰기 0(namespace).
5. `test_multi_ingest_overwrite_only_mineru_and_cleanup`: `test_mineru_ingest.py` 1x/mineru 공존 패턴 미러 + 구 이미지 dir 정리.
6. `test_multi_single_part_equiv_to_ingest_mineru`(회귀): 1-파트 merge = 기존 단일 ingest 동치.

## Plan revisions (after debate)
- **R1** 병렬 ingest 폐기 → **merge(offset+concat raw content_list + namespace images) → 기존 `ingest_mineru_output` 1회**. `merge.py`는 **전처리만**(ingest 로직 복제 없음).
- **R2** 이미지 **part-namespace**(`partNNN__basename`), merged content_list img_path도 rewrite.
- **R3** **full book2.pdf를 provenance origin**으로 배치(markdown_path) → repair 도구 절대 페이지 clip.
- **R4** part 순서 = CLI 인자 순서 계약 + page_idx ∈ [0,page_count) 검증 + page_count는 **part origin.pdf** 기준.
- **R5** split = **ops 스크립트**(CLI 아님). 재사용 자산 = merge.
- **R6** 빈 파트 허용 / all-empty reject / OOB reject / overwrite·cleanup = 기존 ingest 재사용으로 자동.

## DoD checklist
| DoD | Status | Evidence |
| --- | ------ | -------- |
| merge offset 정확 + 경계 연속 | 계획 | 단위(page/order offset, 빈말미 page_count) |
| 단일 content_list로 기존 ingest 재사용 | 계획 | merge→ingest_mineru_output 통합 |
| 이미지 namespace 충돌 0 | 계획 | dup basename diff bytes 테스트 |
| repair provenance=full PDF | 계획 | provenance 테스트(절대 페이지) |
| OOB/빈파트/all-empty/overwrite | 계획 | 4 edge 테스트 |
| 단일=기존 동치(회귀) | 계획 | 1-파트 동치 |
| DB schema 0 / 1.x 불변 | 계획 | 기존 ingest 경로, diff/mtime |
| CI green | 계획 | pytest+mypy+ruff |

## Risk register
| Risk | L | I | Mitigation |
| ---- | - | - | ---------- |
| 병렬 ingest 8a 회귀 | (해소) | 고 | 기존 `ingest_mineru_output` 재사용 |
| 이미지 덮어쓰기(다른 bytes) | (해소) | 고 | part-namespace |
| repair 잘못된 origin | (해소) | 고 | full PDF provenance + 절대 page_idx |
| 빈/OOB page | 중 | 중 | 경계 검증 + reject 테스트 |
| 분할 페이지 속성 | 저 | 중 | repair=full PDF clip(일관), rotated skip 보유 |
| 단일 ingest 회귀 | 저 | 고 | 1-파트 동치 + 기존 경로 불변 |
| 1.x/2.0/prod | 저 | 고 | DB 변경 0, prod 무영향 |

## Decision
- [x] **PASS → proceed to code (단, GATE: Planner 승인 후)**. R1~R6로 접근을 "merge→기존 ingest 재사용 + namespace + full-PDF provenance"로 안전화. 목표(분할 병합 ingest, F3 unblock) 유지. RE-PLAN 불요.
- [ ] RE-PLAN

## Planner 결정 (GATE)
debate가 plan의 5개 open decision을 수렴 — 승인 요청:
1. **CLI**: `ingest-mineru-multi <part_dir...> --filename --source-pdf <full.pdf> --db` (merge→기존 ingest). OK?
2. **page_offset**: part origin.pdf page_count (권장). OK?
3. **이미지**: part-namespace(`partNNN__basename`) ← sha256 가정 폐기. OK?
4. **split**: ops 1회성 스크립트(CLI 아님). OK?
5. **provenance**: full book2.pdf를 origin으로 → repair 절대 페이지. OK?
