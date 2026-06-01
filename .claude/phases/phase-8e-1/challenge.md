# Phase 8e-1 — Challenge

Codex가 핵심을 찔렀다: **"원인 미증명"**(§2) + **"과한 machinery"**(§1). plan 제출 후 **실 qwen 진단**(challenge 작성 전 실행)으로 원인을 확정했고, 그 결과 plan의 segment fallback·sentinel "실험"·볼드 렌더 검증을 폐기/축소한다. 진단이 retry 단독 가설도 반증함. **PASS with major revisions** (core=영어 fallback 교정+byte-identical 보존은 유지, 접근은 evidence-grounded로 교체).

## 진단 결과 (challenge 전 실 qwen3.6-27b 실측, dev doc7 failed 6곳)
- `⟦MATHi⟧`(U+27E6/27E7)는 **opaque하지 않다**. 두 실패 모드:
  - **bracket-mangle** (chunk 16): 모델이 "MATH0"는 보존하나 `⟦⟧`를 `$\ll MATH0 \gg$`로 변환 → present_intact=0.
  - **math-hallucinate** (chunk 67/71): placeholder 무시하고 그럴듯한 LaTeX 재생성(`$z\sim\text{Dir}(\alpha)$` ≠ 원본 `$p(z)=\operatorname*{Dir}(z|\alpha)$`) → 손실.
- **sentinel 후보 실측**: `[[MATHi]]`(ASCII) → chunk16 **3/3 생존**, chunk67 **0/6**. `MATHTOKENiX`(plain) → 0/9.
  → **ASCII sentinel은 bracket-mangle만 교정, hallucinate는 형식 무관**. retry/segment는 결정적 실패라 무효(§2 적중).

## Debate responses
### 1. Over-engineering
- **accept (segment 폐기)**: `_segment_translate`는 결정적 실패(진단)엔 무효 + Eq./Fig./decimals/"where" 오분할(§2/§3, 8d-2c가 고친 바로 그 류). **삭제**.
- **accept (sentinel 전역변경 폐기)**: `PH_OPEN/PH_CLOSE` 전역 교체 안 함. **단일 통제 상수**로 ASCII sentinel 도입하되 `protect_math`/`restore_math` 계약·`test_math_protect`·`short_retranslate` byte-identical 유지.
- **accept (볼드 분리·축소)**: ROADMAP DoD에 볼드 없음. 8e-1 볼드 = **CPU 산출물 style metadata 조사만**(`content_list.json`/md). 신호 없으면 "현 extractor 미지원" 문서화 + GPU 결정 defer(별 spike/8e-2). 렌더 `<strong>` 테스트 폐기(marked 이미 지원).
- **accept (retry 최소화)**: retry는 주(主) 수단 아님(결정적 실패엔 무효) → **싸고 안전한 보조**로만 유지(전이/확률적 손실 대비), 무한 아님.

### 2. Hidden assumptions
- **accept (CRITICAL, 원인 미증명)**: 위 진단으로 확정 — sentinel mangle + math hallucinate(둘 다 결정적). truncation/refusal/empty 아님(out_len 정상, 번역 양호).
- **accept (retry 결정적 무효)**: 진단이 반증. retry는 보조로 격하.
- **accept (max_retries 노출)**: CLI 신 flag 없음. math-loss 재시도는 `_translate_protected` **함수 기본 동작**(상수). 테스트는 mock로.
- **accept (segment 문장경계 위험)**: segment 폐기로 무효화.
- **accept (backend 이름/CUDA)**: GPU backend 실행 안 함(조사만) → 이름/CUDA 미검증 무관. 조사로 회피(§4.4).

### 3. Edge cases
- **accept (CRITICAL, pending_futures dedup)**: math-loss 재시도는 **owner future 내부에서** 완료 후 결과/예외 set → 중복 chunk waiter가 복구분 공유(retry storm/이중 실패 방지). 테스트.
- **accept (caption 정책 명시)**: body 성공 + caption math-loss 시 정책 = **all-or-nothing**(둘 다 math 보존해야 translated, 아니면 failed). 명시 + 테스트.
- **accept (segment 모순 semantics)**: segment 폐기로 해소.
- **accept (`\(`/`\[` 한계)**: math_protect는 `$...$`만(8a가 MinerU inline=`$`). 문서화, scope 확대 안 함. byte-identical 계약은 `$` 범위.
- **accept (currency 쌍)**: byte-identical restore로 안전(불변). segment 폐기로 추가 위험 없음.

### 4. Alternative approaches
- **accept (smallest fix first)**: `_translate_protected`에 math-loss 재시도 추가(주 lever 아닌 보조) + **ASCII sentinel(주 교정)** + **hardened 지시문**(hallucinate 대상 가설). segment/전역sentinel 없음.
- **accept (sentinel 단일 상수)**: `[[MATHi]]` 단일 상수(진단상 bracket-mangle 교정 확인). PH_OPEN/CLOSE 호환 유지.
- **partial (8d-2c 재사용)**: short_retranslate 재사용은 **동일 모델 행동이라 hallucinate엔 무효** → 채택 안 함. 잔여는 영어 fallback.
- **accept (볼드 조사 우선)**: GPU 전에 CPU 산출물 style metadata 조사. 없으면 문서화+defer.

### 5. Missing tests — 채택(segment 제외)
1. `test_math_loss_retries_same_chunk_until_placeholder_restored`(§5.1).
2. `test_math_loss_retry_exhaustion_preserves_failed_no_cache`(§5.2).
3. `test_math_loss_retry_with_duplicate_chunks_shares_future`(§5.3, dedup).
4. `test_caption_math_loss_all_or_nothing`(§5.4).
5. sentinel: ASCII `[[MATHi]]` round-trip byte-identical + collision guard + display-before-inline.
6. (§5.5 segment) **N/A**(segment 폐기). (§5.6 runner backend) **defer**(GPU 작업 8e-1 밖).

## Plan revisions (after debate + 진단)
- **R-A (주 교정)**: sentinel `⟦MATHi⟧` → **ASCII `[[MATHi]]`** (math_protect 단일 상수; byte-identical restore + collision + display-inline 불변; test_math_protect/short_retranslate 갱신). 진단: bracket-mangle 교정.
- **R-B (hallucinate 가설)**: math-protected 번역에 **hardened 지시문** 주입("[[...]] 토큰 그대로 복사, LaTeX 생성 금지"). translate()에 최소 `instructions` 옵션(client/openai_compat/mock). live로 효과 측정.
- **R-C (보조)**: `_translate_protected` math-loss **bounded 재시도**(owner future 내부, dedup-safe). 결정적 실패엔 무효지만 확률적 손실 대비.
- **R-D**: **segment fallback 폐기**. R-A/B/C 후 잔여 실패 → **영어 fallback 유지**(DoD 허용), verify에 잔존 수 명시.
- **R-E**: caption all-or-nothing 정책 명시 + 테스트.
- **R-F**: 볼드 = CPU style metadata **조사만** + finding 문서화, GPU 결정 defer.
- **R-G**: byte-identical 계약 불변; `\(`/`\[` 한계 문서화.

## DoD checklist
| DoD item | Status | Evidence |
| -------- | ------ | -------- |
| 수식밀집 영어 fallback 교정 | 계획 | ASCII sentinel(R-A, bracket-mangle 교정) + hardened 지시(R-B, hallucinate 시도) + retry(R-C); live doc7 전환 수 측정, 잔여 영어 명시 |
| math byte-identical 보존 | 계획 | sentinel 단일 상수, restore 경로 불변, 회귀 테스트 |
| 볼드 method | 계획 | CPU style metadata 조사 + finding(미지원시 defer) |
| 1.x 무손상 | 계획 | translate/extract만, migration 0, prod 0004/49850/0 |

## Risk register
| Risk | L | I | Mitigation |
| ---- | - | - | ---------- |
| byte-identical 깨기(절대금지) | 저 | 고 | restore=store 원본만, 회귀 테스트, last-resort 영어 fallback |
| hallucinate가 지시문에도 잔존 | 중 | 중 | 영어 fallback(DoD 허용) + verify 잔존 수 명시; 과도한 prompt eng. 안 함 |
| sentinel 변경 8b 회귀 | 중 | 고 | 단일 상수 + protect/restore/collision/display-inline 전 테스트 + byte-identical |
| dedup future retry storm | 중 | 중 | owner future 내부 재시도(§3) + 중복 chunk 테스트 |
| 볼드 CPU 미지원 | 중 | 저 | 조사 후 defer(GPU 결정 사용자); math 독립 PASS |
| 1.x 회귀 | 저 | 고 | translate/extract 신규·확장만, migration 0 |

## Decision
- [x] **PASS → proceed to code** (R-A~R-G). 진단으로 원인 확정, Codex over-engineering/미증명 지적 전부 반영(segment·전역sentinel·볼드렌더 폐기, evidence-grounded). core(영어 fallback 교정 + byte-identical) 유지 → RE-PLAN 불요.
- [ ] RE-PLAN
