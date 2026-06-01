# Phase 8e-2 — Verify (self)

7-doc 배치 마이그레이션(이번 라운드 5-doc: book2_ch28 + sample_mixed + 2 papers + Aggarwal 518p). 기존 8a~8e-1 CLI 실행 중심 + 코드 1건(`extract-mineru --timeout`, R6). 모든 값 실측. 코드 commit `3fda1a8`(--timeout) 이후 git status는 phase 산출물만(코드/test drift 0).

## 5-A. Automated checks
| Check    | Command | Result |
| -------- | ------- | ------ |
| Lint     | `uv run ruff check .` | **All checks passed!** |
| Type     | `uv run mypy src/` | **Success: no issues found in 84 source files** |
| Test     | `uv run pytest -m "not llm and not slow"` | **769 passed, 1 skipped, 8 deselected** (555.10s) |
| New test | `test_extract_mineru_cli_supports_timeout_option` | passed (R6 --timeout 잠금) |
| CI       | GitHub Actions | N/A (main/PR만; 8e-3 cutover서 첫 실행). local 769 = CI-equivalent 증거. |

- 769 = 8e-1 종료 768 + 신규 1(--timeout). 코드 변경 최소(challenge: CLI 실행 중심) → 회귀 0.

## 5-B. Functional checks (배치 데이터 검증 — 실측)

### 5-doc 2.0 DB (`data/ht_lens_v2.db`, alembic 0007)
| doc | pages | chunks | translated | failed | emb |
| --- | ----- | ------ | ---------- | ------ | --- |
| 1 book2_ch28 | 11 | 103 | 103 | 0 | 56 |
| 2 sample_mixed | 6 | 40 | 40 | 0 | 22 |
| 3 2503.09642v2 | 21 | 196 | 196 | 0 | 123 |
| 4 2603.03482v1 | 27 | 162 | 162 | 0 | 96 |
| 5 aggarwal_textbook | 518 | 3338 | 3329 | 9 | 2543 |
| **합계** | | **3839** | **3830 (99.77%)** | **9 (0.27%)** | **2840** |

- doc 1–4: **failed 0**. 8e-1 math 강건화가 실 arxiv 논문(수식 다수)에서 0 실패 입증.
- doc 5(518p 교과서): failed 9 = **2 초대형**(TOC 17210자/index 7890자 > `max_tokens=2048` 출력 한계, navigation cruft) + **7 수식밀집 math-loss**(qwen이 다수 placeholder 중 1개 결정적 drop). 전부 empty text **fail-preserve**(무손상), reflow에서 영어 원문 노출. challenge "일부 영어 잔존 허용, 수 명시"대로 수용.

### 완전성 지표(R7: status='translated', failed-text 미렌더)
- failed-text 9개 전원 doc5(reflow `get_reflow`가 status!='translated' 억제 → 영어 원문). docs 1–4 failed-text 0.

### math byte-identical 표본(실 doc)
- doc4 18/18, doc5 13/13 sampled math runs가 번역문에 byte-identical. (doc3 표본은 prose `$` 뿐, paired math 0.)

### cross-doc 데이터(R1: 8e-2는 적재만, live=8e-3)
- 임베딩 보유 doc = **5/5**. 8d-2b cross-doc RAG 머신에 multi-doc 데이터 준비됨. live 검증은 8e-3.

### short-only(R2: verification-driven)
- doc2/3 단문 chunk 표본 = 고유명사/이미-한국어(team명, 종교/기타, 핵심 기여자) → 결함 없음 → **--short-only 불필요**(일괄 적용 안 함).

### 1.x 무손상 (prod `data/ht_lens.db`)
```
alembic=0004  blocks=49850  chunk_tables=0
```
- 모든 명령 `--db data/ht_lens_v2.db`. prod 미접근. v2 DB 백업 `pre8e2.bak` 보관.

## 5-C. 배치 실행 / 블로커 (challenge R3/R6/R8/R9)
- **R6 --timeout**: `extract-mineru --timeout` 추가(+test) → Aggarwal 518p one-shot 가능케.
- **R3 go/no-go**: small 3개(sample/2503/2603) 완수+verify(워크플로 입증) → Aggarwal GO.
- **R8 rerun**: doc별 fresh outdir(`data/mineru_out/<doc>/`), 부분 실패는 폐기 후 재시작. `--retry-failed` idempotent(cache로 성공분 보존).
- **R9 백업**: 배치 전 `data/ht_lens_v2.db.pre8e2.bak`.
- **블로커 2건(환경, 코드 아님; 해결)**:
  1. MinerU venv transformers 5.9.0(`find_pruneable_heads_and_indices` 제거) → 격리 venv `~/mineru_venv`(transformers 4.57.6) 신설(기존 venv 불변).
  2. Aggarwal 518p: MinerU 내부 timeout 3600s → `MINERU_TASK_RESULT_TIMEOUT_SECONDS=14400` 완주; qwen docker OOM 반복 → concurrency 7→2 + `--retry-failed` drain(2392→…→9 수렴).

## 5-D. Scoring (100, self)
| Item | Score / Max | Evidence |
| ---- | ----------- | -------- |
| 독창성 | 11 / 15 | 마이그레이션 phase(신규 알고리즘 적음). go/no-go·idempotent drain·격리 venv·manifest traceability 운영 설계. (−4: 본질이 배치 실행) |
| 완결성 | 31 / 35 | 5-doc 3830/3839(99.77%) + emb 2840 + math 강건화 실 doc 0~소수 실패 입증 + manifest. (−4: 9 영어 fallback(허용·문서화); book2 full·볼드는 의도적 defer) |
| 안정성 | 28 / 30 | 769 green(회귀 0), fail-preserve(9 무손상), 1.x 0004/49850/0, 백업, byte-identical 표본. (−2: qwen 서버 OOM 취약성은 인프라 — concurrency 2 완화·문서화) |
| 확장성 | 18 / 20 | --timeout + concurrency 조절 + idempotent retry로 book2 full/7-doc 확장 경로 확보. cross-doc 데이터 8e-3 준비. (−2: 대용량 OOM은 운영 튜닝 필요) |
| **Total** | **88 / 100** | |

## 5-E. Self verdict
- [x] **PASS_CANDIDATE (88)** → cross-verify Round 1. 5-doc 99.77% 마이그레이션, 코드 회귀 0, 1.x 무손상, 블로커 2건 진단·해결·문서화, 잔여 9 fallback 명시.
- [ ] FAIL → RE-CODE
- [ ] FAIL → RE-PLAN

### 잔여 / 8e-3 이월
1. 9 영어 fallback(2 oversized + 7 math-loss) — DoD 허용. oversized는 max_tokens 한계(8e-3/후속서 청크 분할 또는 큰-chunk 정책 고려), math-loss는 8e-1 잔여.
2. cross-doc RAG **live 검증 = 8e-3**(데이터는 준비됨).
3. book2 full 1370p + 볼드 = cutover 후 follow-up(사용자 확정).
4. qwen 27B 서버 OOM 취약(518p 부하) — 운영 노트(대용량은 concurrency 낮게).
