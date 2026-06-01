# Phase 8e-2 — Verify v2 (self, post verify-cross R1 RE-CODE)

7-doc 배치 마이그레이션(이번 라운드 5-doc). 8a~8e-1 CLI 실행 중심 + 코드 2건(`extract-mineru --timeout` R6, **R1 fix: --timeout을 MinerU 내부 timeout까지 전파**). 모든 값 실측, 최종 code commit `bbdc529` 이후 작성.

**v2 사유**: cross-verify R1(DOWNGRADE ~80-82, "no RE-CODE mandatory for batch data")이 (a) --timeout이 MinerU 내부 timeout 미커버(실 결함), (b) reflow "전체 읽기" 미실증, (c) format-check 누락, (d) 5-doc vs 7-doc DoD, (e) SHA prefix만 — 지적. (a)/(b) RE-CODE+실증, 나머지 wording.

## 5-A. Automated checks (R1 §1: format/coverage 추가)
| Check    | Command | Result |
| -------- | ------- | ------ |
| Lint     | `uv run ruff check .` | **All checks passed!** |
| Format   | `uv run ruff format --check .` | **197 files already formatted** |
| Type     | `uv run mypy src/` | **Success: no issues found in 84 source files** |
| Test     | `uv run pytest -m "not llm and not slow"` | **771 passed, 1 skipped, 8 deselected** (537.69s) |
| Coverage | extract_mineru/runner.py (변경 모듈) | **91%** (미달=binary-discovery 분기/timeout 미사용 라인) |
| CI       | GitHub Actions | N/A — main/PR만(`prototype-reflow` 트리거 없음). local 771은 동일 환경 증거이며 GitHub CI green과 동치 아님(8e-3 cutover서 첫 실행). |

- 771 = 8e-1 종료 768 + --timeout 1(8a) + R1 fix 내부-timeout 2 = 771. 회귀 0.

## 5-B. verify-cross R1 resolution
| R1 지적 | 판정 | 처리 (commit) | 증거 |
| ------- | ---- | ------------- | ---- |
| §4#1 `--timeout`이 MinerU 내부 `MINERU_TASK_RESULT_TIMEOUT_SECONDS`(3600s) 미커버 → Aggarwal 1h사망 | **real** | `run_mineru`가 `timeout_s`를 내부 env로 전파(`bbdc529`); operator env는 setdefault로 우선 | `test_run_mineru_threads_timeout_to_mineru_internal_env`, `..._respects_operator_env` |
| §2 reflow "전체 읽기" 미실증 | **real(evidence)** | TestClient로 5-doc 실측(아래 5-C) | doc1-5 HTTP 200; doc5 text 2330 중 **2321 한국어 본문 + 9 suppressed** |
| §1 format-check 누락 | wording | 5-A에 추가 | 197 formatted |
| §1 coverage 미보고 | wording | 5-A에 runner 91% | 91% |
| §2/§3 5-doc vs 7-doc DoD | wording | **subphase 완료**로 명시(7-doc=Planner가 papers+Aggarwal+sample+book2-ch28로 supersede; book2 full=cutover 후) | challenge §2, manifest |
| §4#4 SHA prefix만/in-DB NULL | 동의(disclosed) | in-DB sha 미주장(ingest 미변경) 결정대로; manifest sha(16)로 traceability | manifest |
| §1 "CI-equivalent" 과장 | wording | 위 CI 행 정정 | — |

## 5-C. Functional checks

### reflow "전체 읽기" 실증 (R1 §2 — TestClient, v2 DB)
```
GET /v2/documents/{id}/reflow:
  doc 1: HTTP 200, chunks=103
  doc 2: HTTP 200, chunks=40
  doc 3: HTTP 200, chunks=196
  doc 4: HTTP 200, chunks=162
  doc 5: HTTP 200, chunks=3338
doc5 text chunks=2330 → 한국어 translated 본문 2321 / empty(failed-suppressed) 9
sample translated: '교재…' (Korean 렌더 확인)
```
- 5-doc 전부 API 200 + 본문 렌더. 9 failed는 `get_reflow` status 게이팅으로 영어 원문 노출(완전성 지표 충족).
- (참고) page-image 404는 정상: `extract-mineru`는 chunk만 추출, page 배경이미지(compare 모드용)는 별도 `render_doc_pages` 단계 — reflow 읽기엔 불요.

### 5-doc 2.0 DB
| doc | pages | chunks | translated | failed | emb |
| --- | ----- | ------ | ---------- | ------ | --- |
| 1 book2_ch28 | 11 | 103 | 103 | 0 | 56 |
| 2 sample_mixed | 6 | 40 | 40 | 0 | 22 |
| 3 2503.09642v2 | 21 | 196 | 196 | 0 | 123 |
| 4 2603.03482v1 | 27 | 162 | 162 | 0 | 96 |
| 5 aggarwal | 518 | 3338 | 3329 | 9 | 2543 |
| **합계** | | **3839** | **3830(99.77%)** | **9(0.27%)** | **2840** |

- docs 1–4 failed 0. doc5 failed 9 = 2 초대형(TOC/index > max_tokens 2048) + 7 수식밀집 math-loss. 전부 empty-text fail-preserve(무손상), 영어 원문 노출. challenge "일부 영어 잔존 허용, 수 명시"대로 수용.
- math byte-identical 표본: doc4 18/18, doc5 13/13.
- cross-doc 데이터: 5/5 임베딩(8d-2b 머신 가능; live=8e-3). short-only: doc2/3 단문 결함 없음 → 불필요(verification-driven, R2).

### 1.x 무손상 (prod `data/ht_lens.db`)
```
alembic=0004  blocks=49850  chunk_tables=0
```
- 모든 명령 `--db v2`. prod 미접근. 백업 `pre8e2.bak`.

## 5-D. 배치 실행 / 블로커 (둘 다 환경, 코드 아님; 해결)
1. MinerU venv transformers 5.9.0(`find_pruneable_heads_and_indices` 제거) → 격리 venv `~/mineru_venv`(transformers 4.57.6) 신설, 기존 venv 불변.
2. Aggarwal 518p: MinerU 내부 timeout 3600s → (R1 fix로) `--timeout`이 내부까지 전파; qwen docker OOM 반복 → concurrency 7→2 + `--retry-failed` idempotent drain(2392→…→9 수렴, cache로 성공분 보존).

## 5-E. Scoring (100, self v2)
| Item | Score / Max | Evidence |
| ---- | ----------- | -------- |
| 독창성 | 11 / 15 | 운영 마이그레이션(신규 알고리즘 적음): manifest traceability, go/no-go, idempotent drain, 격리 venv, **내부-timeout 전파 fix**. (−4: 본질이 배치) |
| 완결성 | 30 / 35 | 5-doc 3830/3839(99.77%) + emb 2840 + reflow 전체읽기 실증 + math 강건화 실 doc. (−5: 9 fallback 허용·문서화; book2 full·볼드 의도적 defer; 5-doc=subphase) |
| 안정성 | 27 / 30 | 771 green(회귀 0), fail-preserve 9 무손상, 1.x 0004/49850/0, 백업, byte-identical, **내부-timeout fix+test**. (−3: 대용량 qwen OOM=인프라, concurrency 완화·문서화) |
| 확장성 | 17 / 20 | `--timeout`이 이제 내부 timeout까지 커버(book2 full 1370p one-shot 경로) + concurrency 조절 + idempotent retry. cross-doc 데이터 8e-3 준비. (−3: 대용량 OOM 운영 튜닝 필요) |
| **Total** | **85 / 100** | R1 80-82 → 내부-timeout fix + reflow 실증 + format/coverage 보강 |

## 5-F. Self verdict
- [x] **PASS_CANDIDATE (85)** → cross-verify Round 2(마지막). R1 real 2건(내부-timeout fix+test, reflow 실증) 처리, wording 갭 폐쇄. 5-doc 99.77%, 회귀 0, 1.x 무손상.
- [ ] FAIL → RE-CODE
- [ ] FAIL → RE-PLAN

### 잔여 / 8e-3 이월
1. 9 영어 fallback(2 oversized max_tokens + 7 math-loss) — DoD 허용. oversized는 8e-3/후속 큰-chunk 정책 고려.
2. cross-doc RAG live 검증 = 8e-3(데이터 준비됨).
3. book2 full 1370p + 볼드 = cutover 후 follow-up.
4. qwen 27B OOM 취약(대용량) — 운영 노트(concurrency 낮게).
5. in-DB src_pdf_sha256 NULL(ingest 미변경 결정) — cutover auditability는 manifest로 보완; 8e-3/후속서 sha 기록 고려.
