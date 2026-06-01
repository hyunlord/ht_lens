# Phase 8e-2 — Summary (7-doc 배치 마이그레이션, 이번 5-doc) — 8e 시리즈 2/3

## Status
**PASS_CANDIDATE → PUSH** — cross-verify R2 **CONFIRM_PASS(85)**. R1(DOWNGRADE ~80-82, "no RE-CODE mandatory for batch data")의 실 결함 2건(내부-timeout 미커버, reflow 미실증) fix+실증, wording 갭(format/coverage/scope/CI) 폐쇄. R2: "concrete defects addressed … 85 appropriately conservative … no further RE-CODE." 2-round cap 준수. 정상 PASS → push.

## Score
- Self verify v1 `8a282ad`: 88 → verify v2 `f0051a0`(post RE-CODE): **85**
- Cross R1 `8b860f1`: **DOWNGRADE ~80-82**(내부-timeout 미커버, reflow 미실증, format 누락, 5/7-doc, SHA) → RE-CODE
- Cross R2 `f27b988`(최종/cap): **CONFIRM_PASS 85**(R1 처리, 새 결함 0)

## What was migrated (5-doc 2.0 DB `data/ht_lens_v2.db`)
| doc | pages | chunks | translated | failed | emb |
| --- | ----- | ------ | ---------- | ------ | --- |
| 1 book2_ch28 | 11 | 103 | 103 | 0 | 56 |
| 2 sample_mixed | 6 | 40 | 40 | 0 | 22 |
| 3 2503.09642v2 | 21 | 196 | 196 | 0 | 123 |
| 4 2603.03482v1 | 27 | 162 | 162 | 0 | 96 |
| 5 aggarwal | 518 | 3338 | 3329 | 9 | 2543 |
| **합계** | | **3839** | **3830 (99.77%)** | **9 (0.27%)** | **2840** |

- docs 1–4 **failed 0** (8e-1 math 강건화가 실 arxiv 논문서 입증). doc5 9 fallback = 2 초대형(TOC/index > max_tokens) + 7 수식밀집 math-loss. 전부 fail-preserve(무손상) → 영어 원문 노출. challenge "일부 영어 잔존 허용" 수용.
- reflow 전체읽기 실증: 5-doc 전부 `/v2/.../reflow` HTTP 200; doc5 text 2330 → 한국어 2321 + suppressed 9(`교재` 샘플 확인).
- math byte-identical: doc4 18/18, doc5 13/13. cross-doc 데이터 5/5 임베딩(live=8e-3).
- 1.x prod 무손상: alembic 0004 / blocks 49850 / chunk_tables 0. v2 DB 백업 `pre8e2.bak`.

## Code changes (challenge `161ac2d` → HEAD; +90/-1)
```
 cli.py                       9 ++  (extract-mineru --timeout, R6)
 extract_mineru/runner.py     8 ++  (--timeout → MinerU 내부 task/startup timeout 전파, R1 fix)
 test_cli_mineru.py          27 ++  (--timeout kwarg 잠금)
 test_mineru_runner.py       47 ++  (내부-timeout env 전파 + operator 우선)
```
테스트: 8e-1 종료 768 → **771**(+3) fast green. extract_mineru/runner.py cov 91%. 데이터(DB/mineru_out)는 gitignore → manifest가 traceability 아티팩트.

## Deviations from plan (challenge/실행)
- **5-doc scope = Planner supersede**(ROADMAP "7 docs" → papers2+Aggarwal+sample_mixed; book2=ch28; demos=소스없음; book2 full=cutover 후). ROADMAP 미수정, subphase 완료로 기재.
- cross-doc RAG **live → 8e-3**(challenge R1; 8e-2는 데이터 적재만).
- `--short-only` **verification-driven**(challenge R2; doc2/3 단문 결함 없어 미적용).
- 볼드 = defer(사용자, 8e-1 finding).

## 배치 중 블로커 2건 (둘 다 환경, 코드 결함 아님; 해결)
1. **MinerU venv transformers 5.9.0**(`find_pruneable_heads_and_indices` 제거) → 추출 0. 격리 venv `~/mineru_venv`(transformers 4.57.6, mineru[all]) 신설. 기존 `~/mineru_test/venv` 불변(사용자 자산 보존).
2. **Aggarwal 518p**: (a) MinerU 내부 task-result timeout 3600s → R1 전엔 env로 우회 완주, **R1 fix로 `--timeout`이 내부까지 전파**(영구). (b) qwen docker(sglang-qwen-27b) 교과서 부하로 OOM 반복 crash → concurrency 7→2 + `--retry-failed` idempotent drain(2392→1804→1147→823→649→259→10→9 수렴, cache로 성공분 보존).

## R1 → R2 resolution
| R1 | 판정 | 처리 | R2 |
| -- | ---- | ---- | -- |
| §4#1 --timeout이 MinerU 내부 timeout 미커버 | real | `run_mineru` env 전파(`bbdc529`) + 2 test | "fixed, not merely reworded" |
| §2 reflow 전체읽기 미실증 | real(evidence) | TestClient 5-doc HTTP 200 + 본문 | "improved materially … evidence now exists" |
| §1 format/coverage 누락 | wording | 5-A 추가(197 formatted, runner 91%) | "now includes the R1-missing format check" |
| §2 5/7-doc DoD | wording | subphase 명시 | "resolves the R1 framing problem" |
| §4#4 SHA/in-DB NULL | disclosed | manifest sha; in-DB 미주장(결정) | (carry-forward) |

## Evidence index
- plan `e062b7e` / debate `35e1566`(Codex) / challenge `161ac2d`(PASS w/ revisions: manifest/timeout/completeness, cross-doc→8e-3)
- feat `3fda1a8`(--timeout) → BLOCKER `ce6d2da`(venv) → manifest `581c3df` → verify v1 `8a282ad`(88) → **cross R1 `8b860f1`(80-82)** → **RE-CODE `bbdc529`**(내부-timeout) → verify v2 `f0051a0`(85) → **cross R2 `f27b988`(CONFIRM_PASS 85)**
- 실측: ruff/format/mypy(84) clean, **771 passed**, runner cov 91%, 5-doc 3830/3839, reflow 5/5 HTTP 200, prod 0004/49850/0.

## Known issues / debt (8e-3 이월)
1. cross-doc RAG **live 검증 = 8e-3**(5-doc 임베딩 데이터 준비됨).
2. browser-level reflow smoke(R2 권고) = 8e-3 cutover 전.
3. GitHub CI 첫 main 실행 = 8e-3 cutover.
4. 9 영어 fallback(2 oversized max_tokens + 7 math-loss) — DoD 허용. oversized는 후속 큰-chunk 정책.
5. book2 full 1370p + 볼드 = cutover 후 follow-up(이제 `--timeout`이 내부까지 커버 → one-shot 경로 확보).
6. in-DB src_pdf_sha256 NULL(ingest 미변경) — manifest로 보완; 후속 sha 기록 고려.
7. qwen 27B OOM 취약(대용량) — 운영 노트(concurrency 낮게).
8. challenge embedding-ratio 지표는 raw count로 보고(carry-forward, 8e-3).

## Recommended next
- **8e-3 (cutover + CI + debt) — v2.0 마일스톤**: `HT_LENS_DB_URL` env 전환(1.x 파일 불변=즉시 롤백) + jsdom CI provisioning(package.json) + schema-head 가드(8d-2c debt) + cross-doc RAG live 검증 + browser reflow smoke + GitHub CI 첫 main green → **ht_lens 2.0**.

## Push 정책
**Push 진행** — 정상 PASS_CANDIDATE + cross R2 **CONFIRM_PASS(85)**(R1 실 결함 fix+lock, 증거 보강, R3 없음, cap 준수). verify v2 self 85, 771 green, 1.x 무손상, 5-doc 99.77% 마이그레이션.
