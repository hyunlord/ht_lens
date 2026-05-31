# Phase 8e-2 — Challenge

Codex가 "CLI만 돌리면 됨" 가정의 실 마이그레이션 견고성 갭(traceability/timeout/completeness/rerun)을 정확히 지적. 대부분 accept → scope 축소(cross-doc→8e-3) + 견고화(manifest, timeout, 완전성 지표) + go/no-go. **PASS with major revisions**.

## Debate responses
### 1. Over-engineering
- **accept (cross-doc → 8e-3)**: 8e-2는 데이터 적재+queryable 증명만. cross-doc RAG **live 검증은 8e-3**로 이동(8e-2는 ≥2 doc 임베딩으로 가능케만).
- **accept (short-only verification-driven)**: `--short-only`를 전 doc 일괄 X. 먼저 baseline full 번역 + failed 카운트 확립 → **단문 결함 보이는 doc에만** neighbor 재번역.
- **accept (Aggarwal go/no-go)**: small 3개(sample_mixed/2503/2603) 먼저 완수+verify로 워크플로 입증 → **그 후 Aggarwal go/no-go**(타이밍 probe 기반).

### 2. Hidden assumptions
- **accept, 명시 (5-doc scope)**: ROADMAP "7 docs"는 사용자 결정(papers2+Aggarwal+sample_mixed; book2=ch28; demos=소스없음 skip; book2 full=cutover 후)으로 **supersede**. ROADMAP은 사람 영역이라 미수정, **deviation 명시**. 이 phase 결과 = 5-doc 2.0 DB(doc7 포함).
- **accept (src_pdf_sha256 갭)**: `ingest_mineru_output`는 sha 미기록 → in-DB source 증명 불가. **migration manifest 아티팩트**(PDF path·sha256·filename·outdir·pagecount·cmd·exit·chunk/tr/failed/emb 카운트)로 traceability 확보. **in-DB sha 주장 안 함**(ingest 코드 미변경, §5.2 OR-분기의 "claim 제거" 채택). filename 충돌은 이번 4 doc 고유명이라 미발생; manifest sha로 구분, dedup 코드 fix는 필요시 후속.
- **accept (timeout)**: `extract-mineru`에 **`--timeout` 옵션 추가**(기본 3600 유지) → Aggarwal 518p one-shot 가능. 테스트 §5.1.
- **accept (완전성 지표)**: `tr=chunks` 폐기. 지표 = **status=='translated' 카운트 + failed 카운트 + reflow에 failed-text 미렌더**. raw row 아님.

### 3. Edge cases
- **accept (rerun 정책)**: doc별 **fresh outdir**(`out/<docid_or_name>/`), 재실행 시 `ingest-mineru --overwrite` 명시. 부분 실패는 해당 doc 폐기 후 재시작(checkpoint).
- **accept (다중 content_list)**: doc별 전용 outdir → `_discover_outputs` first-match 오적재 방지.
- **accept (scanned/encrypted/image-only)**: verify를 "chunks>0"에서 **translated text chunk ≥ 임계(doc 규모 대비)**로 강화 + math/이미지 비율 기록. 결함 doc 격리.
- **partial (--lang)**: 실 대상(papers/textbook)=영어 → `--lang en`. sample_mixed는 fixture(혼합) — verify에서 성격 확인, 필요시 lang 조정. 본 배치 주 대상은 en→ko.
- **accept (emb 임계)**: `chunk_backfill`은 translated text/heading len≥30만 임베딩 → "emb>0" 대신 **eligible 대비 임베딩 비율** 기록. cross-doc 증거는 8e-3.

### 4. Alternative approaches
- **accept (DB 스냅샷)**: 배치 전 `data/ht_lens_v2.db` **백업**(`ht_lens_v2.db.pre8e2.bak`) → 전 doc verify 통과 후 유지, 실패 시 복원. cutover 후보 in-place 변이 위험 완화.
- **accept (manifest)**: §2 traceability 아티팩트(`.claude/phases/phase-8e-2/manifest.md`). scripts/ 신규 아님.
- **accept (Aggarwal split 옵션)**: go/no-go에서 one-shot(--timeout) vs PyMuPDF page-range 분할 결정. 분할 시 단일 book 단편화 trade-off 기록(또는 대표 chapter, book2 ch28 선례).

### 5. Missing tests
- **accept §5.1**: `test_extract_mineru_cli_supports_timeout_option`(--timeout 전달).
- **accept→claim제거 §5.2**: in-DB sha 미주장 → 테스트 대신 manifest가 sha 기록. (sha 컬럼 fix는 후속.)
- **defer §5.3**: filename+sha dedup — 이번 미발생, 후속.
- **accept §5.4**: `test_reflow_doc_suppresses_failed_text_translations`(failed row는 본문 미노출 — 완전성 지표 잠금).
- **accept→8e-3 §5.5**: `test_cross_doc_rag_returns_ref_with_different_doc_id` — cross-doc live(8e-3).

## Plan revisions
- R1 cross-doc RAG **live 검증 → 8e-3**(8e-2=데이터 적재만).
- R2 `--short-only` = doc별 **verification-driven**(일괄 X).
- R3 small 3 완수+verify → **Aggarwal go/no-go**.
- R4 **5-doc scope = Planner 승인, ROADMAP "7 docs" supersede 명시**(ROADMAP 미수정).
- R5 **migration manifest 아티팩트**로 traceability(path/sha/docid/counts), in-DB sha 미주장.
- R6 `extract-mineru --timeout` 추가(+test) → 518p one-shot.
- R7 완전성 지표 = translated 카운트 + failed + failed-text 미렌더(+test).
- R8 doc별 fresh outdir + `--overwrite` rerun.
- R9 배치 전 v2 DB 백업.

## DoD checklist
| DoD item | Status | Evidence |
| -------- | ------ | -------- |
| 다중 doc 2.0 DB(5-doc) | 계획 | doc별 extract→ingest→translate→embed + manifest 카운트 |
| reflow 전체 읽기 | 계획 | doc별 API 200 + translated 렌더, failed 미노출 |
| math 강건화 실효 | 계획 | doc별 failed 카운트(8e-1 최소) + byte-identical 표본 |
| 1.x 무손상 | 계획 | prod 0004/49850/0, 모든 명령 --db v2 |
| (cross-doc live) | **8e-3** | 8e-2는 ≥2 doc 임베딩 적재만 |

## Risk register
| Risk | L | I | Mitigation |
| ---- | - | - | ---------- |
| Aggarwal 518p timeout | 중 | 중 | `--timeout` + go/no-go(분할 옵션) |
| 실 PDF extract/ingest 결함 | 중 | 중 | doc별 outdir+격리, 8a fail-fast, 결함 시 fix |
| source 미추적 | 중 | 중 | manifest(sha) |
| failed-text가 완전성 가장 | 중 | 중 | translated-status 지표 + failed-미렌더 test |
| cutover 후보 in-place 변이 | 저 | 중 | 배치 전 백업 |
| 1.x 오접근 | 저 | 고 | --db v2 명시 + prod 재확인 |

## Decision
- [x] **PASS → proceed to code** (R1–R9). cross-doc→8e-3 축소, manifest/timeout/완전성 견고화, go/no-go. core(배치 마이그레이션) 유지 → RE-PLAN 불요.
- [ ] RE-PLAN
