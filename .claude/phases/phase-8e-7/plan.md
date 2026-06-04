# Phase 8e-7 — Plan (split-extract 병합 ingest CLI) — F3 unblock

Versioning: v2.0-e7 · `phase-8e-7` 분기 → PR/머지(CI on main/PR). **GATE: 이 plan은 Planner 승인 전 구현 착수 금지.**

## Context
F3 STEP 1(book2 full 1370p 단일 extract-mineru)이 **12h `--timeout` cap에서 clean timeout**(rc=4, steady-slow=CPU-bound, crash/OOM/stall 아님, 부분산출 0, DB/1.x 무영향). Planner 결정 = **1안 분할추출**: book2.pdf를 0-684 / 685-1369 둘로 나눠 각각 extract-mineru(검증경로, 각 ~6h<cap) → **content_list 2개를 page_idx offset 병합해 단일 doc ingest**. `ingest-mineru`는 append 미지원이라 **커스텀 병합**이 필요 → 이를 **재사용 가능 CLI**로 만들어 향후 대용량 doc 분할 자산화.

## Goal
N개 MinerU content_list(분할 파트)를 **page_idx/order_idx offset을 정확히 적용**해 **단일 Document**로 병합 ingest하는 CLI + 병합 로직. 경계 연속성·단조성·자산(이미지) 정합 보장. 8e-7은 **도구 구축+검증**(합성 다중-파트로 hermetic 테스트); 실제 book2 split-extract 실행은 8e-7 머지 후 F3 재개.

## Stage 0 실측 (cap-kill 진단 + ingest 구조)
- **cap-kill**: `extract-mineru` rc=4 "MinerU timed out after 43200s". steady-slow(~13코어 풀가동, CPU-time 꾸준). 부분산출 0(MinerU 완료 시 일괄 기록). 2.0 DB 5-doc/3839 불변, 1.x mtime 2026-05-28 불변.
- **page-range**: `mineru -s/-e`(start/end page) **지원**. 단 `ht-lens extract-mineru`는 미노출 → Planner 채택대로 **PDF 2분할 후 각 extract-mineru**(검증경로 유지, mineru 직접호출 회피).
- **ingest 구조**(`ingest_mineru/`):
  - `content_list.py parse_content_list(raw) -> list[ParsedChunk]`: `page_idx`(item 값), `order_idx`(kept item 순차), `bbox_json`(verbatim), `img_path`(basename), `caption`, type 등.
  - `pipeline.py ingest_mineru_output(cl_path, session, *, filename, images_dir, markdown_path, overwrite)`: 한 content_list → Document + Chunks, `_copy_image(pc.img_path, images_dir, dest_dir)`로 이미지 → `data/extracts_v2/<doc>/images/`.
  - MinerU 이미지 basename = **cropped image의 sha256** → 동일 content면 동일 basename(파트 간 충돌=동일 이미지=병합 안전).
  - 각 파트 MinerU 출력에 `*_origin.pdf`(파트 PDF 사본) → 파트 **page_count** 도출 가능.

## 핵심 설계 — offset 병합
파트 k의 chunk에:
- **page_idx += page_offset_k**, `page_offset_k = Σ_{j<k} (파트 j 소스 PDF page_count)`. (book2: part1=685p → part2 offset 685 → part2 page_idx 0-684 → 685-1369 = **원본 book2 절대 페이지와 일치** → 비교모드 page 렌더 정합.)
  - **page_count는 파트 origin.pdf의 page_count** 사용(max(content_list page_idx)+1 **금지** — 말미 빈 페이지 누락 위험). 경계 정확성의 핵심.
- **order_idx += order_offset_k**, `order_offset_k = Σ_{j<k} len(파트 j ParsedChunks)`. → 전체 단조증가, reflow 순서 보존.
- **이미지**: 각 파트 images_dir에서 복사. basename 충돌 시 = 동일 content(sha256) → idempotent 복사(둘 다 같은 file 참조, 정합). 충돌 검증 테스트.
- **bbox/caption/text**: 파트 내 그대로(파트별 1000-정규화 동일 기준) — offset 무관, verbatim 유지.

## Scope
**In (8e-7)**
- **A. 분할 helper**: book2.pdf → 2 PDF(0-684 / 685-1369) PyMuPDF `select`. (재사용: `split-pdf` CLI 또는 ops 1회성 — 결정 D4.)
- **B. 병합 코어**(`ingest_mineru/`): `merge_parsed_parts(parts: list[(ParsedChunk목록, page_count)]) -> list[ParsedChunk]` 순수 함수(offset 적용). + 다중-content_list ingest 경로(`ingest_mineru_multi(...)` 또는 `ingest_mineru_output` 확장).
- **C. CLI**: `ingest-mineru-multi <cl1> <cl2> ... --filename --db`(또는 `ingest-mineru` 다중 positional). 파트별 images_dir·page_count 자동 발견(각 auto/ + origin.pdf). 단일 트랜잭션(파트 중 실패 시 롤백).
- **D. 정합성 테스트**(합성 hermetic): 경계(684/685) 연속, page_idx 단조증가, chunk 수=Σ파트, image basename 충돌 0(또는 동일-content 안전 병합), order_idx/bbox/caption offset 정확, 단일-파트=기존 ingest 동치(회귀).

**Out**
- 실제 book2 split-extract 실행(~12h ×2) — 8e-7 머지 후 **F3 재개**에서. plan/구현/cross-verify는 **합성 소형 다중-파트**로.
- mineru `-s/-e` 직접호출(PDF 분할로 검증경로 유지). GPU 경로(비채택). 1.x. 기존 단일 `ingest-mineru` 동작 변경(병합은 신규 경로, 기존 불변).

## Approach
1. **split**: `split_pdf(src, boundaries) -> list[Path]` (PyMuPDF `doc.select(range)` → 파트 PDF 저장). book2 → [0..684], [685..1369].
2. **extract**(F3 재개 시): 각 파트 `ht-lens extract-mineru part_k.pdf -o out_k --timeout <충분>` 순차(CPU-bound, 병렬은 코어 경합 — worker가 코어수 보고 최종판단).
3. **merge ingest**: `ingest-mineru-multi out_1 out_2 --filename book2_full.pdf`:
   - 각 out_k에서 content_list + images_dir + origin.pdf(page_count) 발견.
   - 각 parse → `merge_parsed_parts`로 page_idx/order_idx offset → 단일 Document + Chunks, 파트별 이미지 복사.
   - overwrite/원자성: 한 세션 트랜잭션, 실패 시 rollback + 부분 이미지 정리(기존 ingest 패턴 재사용).

## File-level changes (예상 — 승인 후 확정)
| Path | Action | Note |
| ---- | ------ | ---- |
| `src/ht_lens/ingest_mineru/merge.py` (신규) | 신규 | `merge_parsed_parts`(순수 offset) + 파트 발견(page_count from origin.pdf) |
| `src/ht_lens/ingest_mineru/pipeline.py` | 수정 | `ingest_mineru_multi` (or 확장) — 다중 content_list → 단일 doc |
| `src/ht_lens/cli.py` | 수정 | `ingest-mineru-multi` 커맨드 (+ 선택 `split-pdf`) |
| `tests/...` | 신규 | 병합 단위(offset/경계/단조/충돌) + ingest 통합(다중→단일 doc, 단일=동치 회귀) |
| (스키마) | **없음** | additive 아님, 신규 ingest 경로만. DB 변경 0 |

## Dependencies (new)
| Package | Why |
| ------- | --- |
| (없음) | PyMuPDF(fitz) 기존, ingest 재사용 |

## Test strategy (합성 hermetic — 실 book2 불요)
- **merge 단위**: 2개 합성 ParsedChunk 목록 + page_count(예: part1 3p, part2 2p) → 병합 결과 page_idx [0,1,2]+[3,4](offset 3), order_idx 0..N-1 단조, **경계**(part1 max page 2 → part2 첫 page 3 연속), bbox/caption verbatim.
- **page_count 출처**: 말미 빈 페이지(part1 page_count 5인데 content 최대 page_idx 3) → offset=5(origin.pdf 기준), max+1(4) 아님 검증.
- **이미지 충돌**: 두 파트 동일 basename(동일 content) → 단일 file, 양 chunk 참조 안전; 서로 다른 basename → 둘 다 복사.
- **ingest 통합**: 합성 2-파트 출력 → `ingest-mineru-multi` → 단일 doc, chunk 수=Σ, page_idx 단조, 이미지 `/v2/chunks/{id}/image` 200.
- **회귀**: 단일 content_list를 multi 경로로(파트 1개) → 기존 `ingest-mineru`와 동치(chunk 수·page_idx·order_idx 동일).
- 전체 850+ green, mypy/ruff clean, 1.x·기존 ingest 불변.

## DoD mapping
| DoD | How | Evidence |
| --- | --- | --- |
| 병합 offset 정확 | `merge_parsed_parts` 순수 함수 | 단위(page/order offset, 경계, 단조) |
| 경계(684/685) 연속 | page_count(origin.pdf) 기반 offset | 단위 + 빈말미 페이지 케이스 |
| chunk 수=Σ파트 | 병합=concat | 통합 테스트 |
| image 충돌 0/안전 | sha256 basename, idempotent 복사 | 충돌 단위 |
| 단일=기존 동치(회귀) | 1-파트 multi 경로 | 회귀 테스트 |
| 재사용 CLI | `ingest-mineru-multi` | CLI 테스트 |
| DB schema 0 / 1.x 불변 | 신규 경로만 | diff/ mtime |
| CI green | pytest+mypy+ruff | push 후 |

## 위험 / 완화
- **page_offset 오류(빈 페이지)** → origin.pdf page_count 사용(max page_idx 금지) + 빈말미 테스트.
- **이미지 basename 충돌** → 동일 content면 안전(sha256); 테스트로 잠금. (만약 다른-content 동일-basename = MinerU 버그성 → 발생 시 namespace fallback, 테스트로 감지.)
- **경계 중복/누락**(분할 시 페이지 겹침/빠짐) → split은 disjoint 연속 범위([0..b-1],[b..end]) + 합=원본 page_count 검증.
- **부분 ingest 실패** → 단일 트랜잭션 rollback + 이미지 정리(기존 패턴).
- **단일 ingest 회귀** → 기존 `ingest-mineru` 경로 불변(병합은 신규 함수); 1-파트 동치 테스트.
- **1.x/2.0/prod** → DB 변경 0(신규 doc는 F3 재개 시 추가), schema 0, prod 무영향.

## 결정 필요 (debate/challenge·Planner — GATE)
1. **CLI 형태**: 신규 `ingest-mineru-multi` vs 기존 `ingest-mineru` 다중 positional 확장. (권장: 신규 — 기존 동작 명확히 불변.)
2. **page_offset 출처**: 파트 origin.pdf page_count(권장) vs 명시 `--page-offsets` 인자 vs max(page_idx)+1(비권장).
3. **이미지 충돌 정책**: 동일-content idempotent(권장) vs 파트 namespace prefix(안전하나 basename 안정성=8e-5 manifest 매칭과 충돌 주의).
4. **split helper**: 재사용 `split-pdf` CLI vs ops 1회성 스크립트.
5. **추출 순차/병렬**: 순차 권장(CPU-bound). 8e-7은 도구라 무관, F3 재개 시 worker가 코어수 보고 판단.
