# Phase 8e-1 — Summary (math 강건화 + 볼드 method) — 8e 시리즈 1/3

## Status
**PASS_CANDIDATE → PUSH** — cross-verify R2 **CONFIRM_PASS(92)**. R1(DOWNGRADE 89)의 실 결함 1개(hashed sentinel 프롬프트 미포함) fix + 증거 갭 3개(byte-identical 전수/coverage/볼드 artifact) 폐쇄. R2: "materially addresses Round 1, no untested new code path … 92/100 credible." 2-round cap 준수. 정상 PASS → push.

## Score
- Self verify v1 `612a1af`: **93** → verify v2 `3ccd883`(post RE-CODE): **92**
- Cross R1 `9b2760f`: **DOWNGRADE 89**(byte-identical 3/6, hashed sentinel 미커버, coverage 부재, 볼드 artifact 부재) → RE-CODE
- Cross R2 `ea6c357`(최종/cap): **CONFIRM_PASS 92**(전부 처리, 새 결함 0; chunk_pipeline 독립측정 83%)

## 진단-주도 (핵심)
plan 제출 후 **실 qwen3.6-27b 진단**으로 6 failed의 원인 확정: `⟦MATHi⟧`(U+27E6/27E7)는 opaque 아님 — 모델이 brackets를 LaTeX로 mangle(chunk16) 또는 placeholder 무시하고 math hallucinate(chunk67). retry/segment는 결정적 실패라 무효(Codex debate §2 적중). → segment fallback·sentinel 실험 폐기, evidence-grounded 설계로 전환.

## What was built
- **R-A ASCII sentinel**: `math_protect` PH_OPEN/CLOSE `⟦⟧`→`[[`/`]]`(regex-escape collision guard). byte-identical restore + display-before-inline 불변.
- **R-B 보존 지시문**: `_translate_system` 양 branch에 "`[[MATH`로 시작·`]]`로 끝나는 모든 토큰 그대로 복사, LaTeX 생성 금지". hallucinate 교정의 결정타(chunk67 0/6→6/6). R1 후 hashed sentinel 커버하도록 **일반화**.
- **R-C math-loss retry**: `_translate_protected`에 bounded(`_MATH_LOSS_RETRIES=1`) 재시도, owner-future 내부(dedup-safe). provider nondeterminism 대비 net.
- **R-E caption all-or-nothing**: body 성공 + caption math-loss → 전체 failed(명시 + 테스트).
- **R-F 볼드 finding**: MinerU CPU `pipeline` span에 style/bold 키 0 → GPU vlm/hybrid 또는 PyMuPDF 폰트플래그 필요 → **8e-2 backend 결정으로 defer**(`bold_finding.md` 영속). 렌더는 marked가 `**`→`<strong>` 지원.

## live 결과 (실 qwen, dev DB doc1)
- **수식밀집 영어 fallback 6곳(16/67/71/72/76/90) → 0**, 전부 한국어 + math **byte-identical**(전수 검증: missing=[] + 원본 math run 보존). production 경로 `--retry-failed`: failed 6→0, translated 97→103.
- 1.x prod 무손상: alembic 0004 / blocks 49850 / chunk_tables 0.

## Files changed (challenge `fb28e33` → HEAD; +262/-28)
```
 llm/openai_compat.py            14 ++  (_translate_system 보존 지시 + 일반화)
 translate/chunk_pipeline.py     41 ++  (math-loss retry + caption 명시 + 상수)
 translate/math_protect.py       20 ++  (ASCII sentinel + escape collision)
 tests/test_chunk_translate.py  161 ++  (retry §5.1-5.3 + caption §5.4 + sentinel 갱신)
 tests/test_math_protect.py      24 ++  (ASCII sentinel lock + collision)
 tests/test_translate_prompt.py  28 ++  (보존 규칙 일반형 lock)
 tests/test_short_retranslate.py  2 +-  (comment)
```
테스트: 8d-2c 종료 761 → **768**(+7) fast green. coverage math_protect 100% / chunk_pipeline 80%(R2 독립 83%).

## Deviations from plan (debate/진단 반영)
- **segment fallback 폐기**(challenge R-D): 결정적 실패엔 무효 + Eq./Fig./"where" 오분할(8d-2c가 고친 류). Codex §1/§2.
- **sentinel "실험" → 단일 통제 상수**(R-A): PH_OPEN/CLOSE 전역 1회 변경, byte-identical·collision·8b 테스트 유지.
- **볼드 = 구현 아닌 finding**(R-F): CPU 미지원 확정, GPU 결정 8e-2 defer.
- **R-B 지시문은 translate Protocol param 대신 `_translate_system` 내장**: ~30 translate override mock churn 회피(Codex "machinery 최소화"), mock는 system prompt 무시라 단위테스트 영향 0.

## R1 → R2 resolution
| R1 지적 | 판정 | 처리 | R2 |
| ------- | ---- | ---- | -- |
| §4#2 hashed sentinel 프롬프트 미커버 | real | 프롬프트 일반화([[MATH…]]) + lock(`e30874f`) | "generalized … tested both branches" |
| §4#1 byte-identical 3/6 | evidence | 6곳 전수 재검증(신 프롬프트) | "closes the Round 1 gap … chunk72 포함" |
| §4#3 coverage 부재 | evidence | math_protect 100% / chunk_pipeline 80% | "independently read … 83%, conservative" |
| §4#4 볼드 artifact 비영속 | evidence | `bold_finding.md` commit | "committed … adequate" |

## Evidence index
- plan `e164ab2` / debate `2a8655f`(Codex) / challenge `fb28e33`(PASS w/ major revisions, 진단-주도)
- feat `d08904b` + test `bd3f166` → verify v1 `612a1af`(93) → **cross R1 `9b2760f`(DOWNGRADE 89)** → **RE-CODE `e30874f`** → verify v2 `3ccd883`(92) → **cross R2 `ea6c357`(CONFIRM_PASS 92)**
- 실측: ruff/format/mypy(84) clean, **768 passed**(1 skip/8 deselect), cov 100%/80%, live 6/6 byte-identical, prod 0004/49850/0.

## Known issues / debt
1. **볼드 GPU 결정(8e-2, 사용자)**: CPU pipeline 미지원 확정 → (a) 1회성 GPU vlm/hybrid (b) PyMuPDF 폰트플래그 재결합 (c) defer. `bold_finding.md` 참조.
2. retry는 temp=0 결정적 손실엔 무효(R-A/B가 실질 교정); provider nondeterminism 대비 net(bounded 2).
3. hashed collision sentinel은 rare-path(소스에 `[[MATHi]]`형 존재 시만); 프롬프트 일반형 커버 + 파이프라인 collision 테스트, 실 qwen hashed live 미측정(rare).
4. `\(`/`\[` 미보호(MinerU `$` emit) — 8b 한계 유지.

## Recommended next
- **8e-2 (7-doc 배치)**: papers 2 + Aggarwal + sample_mixed (book2=ch28/선택챕터) **incremental smallest-first** 재추출(신 math 강건화 적용)+번역+임베딩. **착수 전 볼드 backend 결정 필요.**
- **8e-3**: cutover(`HT_LENS_DB_URL` env 전환, 1.x 불변) + jsdom CI provisioning + schema-head 가드(8d-2c debt) + cross-doc RAG live + GitHub CI 첫 main 실행 → **v2.0**.

## Push 정책
**Push 진행** — 정상 PASS_CANDIDATE + cross R2 **CONFIRM_PASS(92)**(R1 실 결함 fix+lock, 증거 전수 보강, R3 없음, cap 준수). verify v2 self 92, 768 green, 1.x 무손상.
