# Phase 8d-2c — Summary (neighbor 재번역 + 사이드탭 resize) — 8d 시리즈 마지막

## Status
**PASS_CANDIDATE → PUSH** — cross-verify R2 **CONFIRM_PASS(93)**. R1(DOWNGRADE 86)이 잡은 CLI 안전 결함 2개 fix+lock, overclaim 1개 정정 → R2가 "Round 1's two real CLI safety defects were fixed and locked … remaining gaps are disclosed and do not justify another RE-CODE round" 확인. 2-round cap 준수(R3 없음). 정상 PASS → push.

## Score
- Self (verify v1 `87b2c13`): **92** → (verify v2 `8fadc38`, post RE-CODE): **93 / 100**
- Cross R1 (`80d2a20`): **DOWNGRADE 86** (실 결함: dry-run footgun, silent invalid chunk-id) → RE-CODE
- Cross R2 (`e5cc673`, 최종/cap): **CONFIRM_PASS 93** (새 회귀 없음, 잔여 전부 disclosed)

## What was built
### A. neighbor-context 짧은-chunk 재번역 (translate, 8b 재사용)
- `translate/short_retranslate.py`(신규): `select_short_retranslate`(<25자 text, ref-number/math 제외, **반복 카운트 제외 안 함** — 정당한 반복 'where' 보존), `retranslate_short`(이웃 all-type 라벨 context로 **target만** 재번역, math_protect 왕복).
- **cache poisoning 방지(R1, Codex CRITICAL)**: content-only 캐시 **우회** + 결과 row **`cache_key=NULL`** → 미래 동일-content chunk가 문맥특화 번역 오재사용 불가.
- **fail-preserve(R3)**: placeholder 누락/빈 출력 → 기존 row 불변(8b no-write).
- CLI `translate-chunks --short-only/--max-chars/--dry-run/--chunk-id`(R2/R8). dry-run=before/after 출력·무기록.

### B. 채팅 drawer 너비 resize + 본문 연동 (frontend, isolated)
- `static/js/resize.js`(신규): `clampWidth`([280, 60vw]), `applyChatWidth`(CSS `--chat-w` + **sessionStorage**, localStorage 금지), `syncPaneMargin`(본문 margin은 **single 읽기 모드 + open**일 때만 — compare는 overlay라 1fr|1fr 그리드 무squeeze, R9), `initResize`(복원 + pointer drag).
- chat.js(toggle)·reflow.js(mode radio)에서 호출 → close/compare는 margin clear, single-open/reopen은 복원.

migration 0건(translate/frontend만). 1.x block 번역/chat/RAG 무변경.

## Files changed (challenge `c89a272` → HEAD; +1199/-1)
```
 api/static/css/reflow.css            10 ++   (--chat-w, .chat-resizer)
 api/static/js/chat.js                 5 ++   (initResize + toggle margin)
 api/static/js/reflow.js               3 ++   (mode radio → syncPaneMargin)
 api/static/js/resize.js              96 ++   (신규)
 api/static/reflow.html                1 +    (.chat-resizer 핸들)
 cli.py                               67 ++   (--short-only/--max-chars/--dry-run/--chunk-id + 안전 guard)
 translate/short_retranslate.py      213 ++   (신규)
 tests/test_short_retranslate.py     356 ++   (신규, 10)
 tests/test_short_retranslate_cli.py 239 ++   (신규, 7)
 tests/test_resize_js.py             210 ++   (신규, 8)
```
테스트: 8d-2b 종료 736 → verify v1 758(+22) → RE-CODE **761**(+3) fast green.

## Deviations from plan
- plan의 CLI 경로 `translate/cli.py`는 오류 → challenge R2에서 `src/ht_lens/cli.py` translate-chunks로 정정(구현 일치).
- plan의 `is_repeated`(중복=보일러플레이트) **삭제**(challenge R4): 정당한 반복 'where'/'Proof.' 오제외 위험. 보일러플레이트는 <25자 길이로 이미 제외.
- 이웃 context = text-only(plan) → **all-type 라벨**(challenge R7): 'where'가 참조하는 수식/heading context 보존.
- 재번역 = 캐시 우회 + cache_key=NULL(challenge R1, plan에 없던 poisoning 방지).
- R1 RE-CODE 추가(plan 외, 안전): `--dry-run` misuse guard(exit 2) + 미존재 `--chunk-id` raise(exit 2). 작은 정합성 — Codex R1 실 결함.

## R1 → R2 resolution (escalate 불요, 정상 흐름)
| R1 지적 | 판정 | 처리 (`8771386`) | R2 |
| ------- | ---- | --------------- | -- |
| A. `--dry-run` w/o short·chunk-id → write fall-through | real defect | guard → exit 2 fail-fast(health 전) | "fixed" |
| B. 미존재 `--chunk-id` → silent exit 0 | real defect | `retranslate_short` missing-id → ValueError exit 2 | "fixed and locked" |
| C. "malformed" 테스트 overclaim | valid(명칭) | rename + R3 target-only 설계 근거 docstring(추출 없음→malform할 delimiter 없음) | "will not re-raise … verify v2 explicitly narrows it" |

## Evidence index
- plan `3af95eb` / debate `7d8b922`(Codex) / challenge `c89a272`(PASS R1–R10)
- feat `96eb729`(retranslate) + `ceae9fa`(resize) + test `faf8d13`
- verify v1 `87b2c13`(92) → **cross R1 `80d2a20`(DOWNGRADE 86)** → **RE-CODE `8771386`** → verify v2 `8fadc38`(93) → **cross R2 `e5cc673`(CONFIRM_PASS 93)**
- 실측: ruff/format/mypy(84) clean, **761 passed**(1 skip/8 deselect), short_retranslate.py cov **97%**, 1.x prod 0004/blocks=49850/chunk_tables=0, dev doc1 chunk2 `where→여기서` cache_key=NULL.

## Known issues / debt
1. **schema-head 체크(R2 #4 minor residual)**: short-retranslate 분기는 `translate_chunks`의 `SchemaVersionMismatch` 체크 미경유 → 구버전 1.x DB에 `--short-only` 시 clean exit 3 대신 raw DB error. Codex 명시: "not a new Round 2 regression … does not undermine 1.x non-mutation evidence". **8e** 7-doc 마이그레이션 시 schema-head 가드 통일 권장.
2. reflow.js mode-radio → `syncPaneMargin` wiring: 함수 단위(syncPaneMargin 양모드) 검증; reflow.js auto-init side-effect로 e2e jsdom 미작성(disclosed).
3. 자동 selector math 제외 → `_translate_with_context` placeholder-loss 분기는 `--chunk-id`로만 도달(설계, 테스트됨). 비어있지-않고 placeholder 살아있는 LLM 출력은 신뢰(설명문 판별=8e).
4. `(A.1)-(A.3)` 범위형 참조 단일 regex 미커버(단일 `(A.1)`은 커버); 8e 7-doc 분포 재검토.
5. jsdom CI provisioning(8e prereq, memory 기록): package.json + npm/jsdom install 후 8e cutover.

## Recommended next
- **8d 시리즈 완료**(8d-1/2a/2b/2c 전부 push). chat/pin/RAG/section/figure/cross-doc refs/neighbor 재번역/resize 완비.
- **8e**: 7-doc 마이그레이션 + 실 볼드(재추출) + 수식밀집 영어 fallback 6곳 math 강건화 + cross-doc RAG live(2-doc) + schema-head 가드 통일(#1) + jsdom CI provisioning + 1.x→2.0 cutover → v2.0.

## Push 정책
**Push 진행** — 정상 PASS_CANDIDATE + cross R2 **CONFIRM_PASS**(R1 실 결함 fix+lock, R3 없음, cap 준수). verify v2 self 93, 761 green, 1.x 무손상. escalate 불요(R2가 broad RE-CODE 명시 불요 판정).
