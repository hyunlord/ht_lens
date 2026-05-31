# Phase 8e-1 — Plan (math 강건화 + 볼드 method) — 8e 시리즈 1/3

## 8e 전체 구조 (사용자 확정)
- **8e-1**(이 phase): math 강건화 + 볼드 추출 method — dev doc7로 검증.
- **8e-2**: papers 2 + Aggarwal + sample_mixed (book2는 ch28/선택챕터; full 1370p는 cutover 후 follow-up) **incremental smallest-first** 배치 재추출+번역+임베딩.
- **8e-3**: cutover(`HT_LENS_DB_URL` env 전환, 1.x 파일 불변=즉시 롤백) + jsdom CI provisioning + schema-head 가드(8d-2c debt) + cross-doc RAG live 검증.

각 sub-phase는 독립 plan→debate→challenge→verify→cross-verify cycle. 이 plan은 **8e-1만**.

## Goal
수식밀집 영어 fallback(doc7 6곳)을 한국어 번역으로 교정하되 **math byte-identical 보존(8b 계약)**. + MinerU 볼드 추출 가능성 규명 및 (가능 시) recipe + reflow 렌더 검증.

## Stage 0 실측 (근거)
- **failed 6곳 = type=text, len 348–702, inline `$...$` 1–6개**(chunk 16:3, 67:6, 71:4, 72:**1**, 76:2, 90:3). chunk 72가 **단일 span**으로도 실패 → 원인이 "다수 placeholder"만이 아니라 **sentinel 자체 취약성**도 포함.
- 현 sentinel `⟦MATHi⟧` = U+27E6/27E7(희귀 수학 괄호). qwen이 긴 번역 중 normalize/drop 가능.
- `_retry_translate`(chunk_pipeline.py:264)는 **`LLMTransientError`만 재시도** → math-loss(`missing` non-empty)는 `_MathLostError` 즉시 raise, **재번역 0회**(chunk_pipeline.py:257-260). ← 핵심 미사용 lever.
- `math_protect.protect_math/restore_math`는 display→inline 순, byte-identical restore, collision guard(`source_has_placeholder_collision`) 보유. 8b 테스트로 잠김.
- MinerU 3.2.1(`~/mineru_test/venv/bin/mineru`): **볼드 플래그 없음**(`-m/-b/-l/-f/-t`만). 현 `-b pipeline`(CPU) 출력 `**` **0개**(dev doc7 + raw mineru_md.md). 볼드는 보통 `vlm-*/hybrid-*` backend(GPU). reflow 렌더(render_markdown.js, marked gfm + DOMPurify)는 `**`→`<strong>` 이미 지원.

## Scope
**In (8e-1)**
- **A. math 강건화** (chunk_pipeline + math_protect, doc7 6곳 검증):
  1. **math-loss-aware retry**: `missing` 비었을 때까지 bounded 재번역(현재 transient만 재시도 → math-loss도 재시도 추가). 결정적 테스트(mock가 1회차 drop→2회차 보존→복구).
  2. **segment fallback**: retry 소진 후에도 실패 시 chunk를 문장경계로 분할, 세그먼트별 번역(placeholder 적음)→재조립. partial 복구. mock(큰 chunk drop, 작은 세그먼트 보존→복구).
  3. **sentinel 견고화**(보조, 경험적): `⟦MATHi⟧` → qwen이 더 잘 보존하는 형식 후보 doc7 6곳 실측 비교. **byte-identical restore + collision guard + display-before-inline 불변**. 손실률 최저 선택.
  4. **last-resort**: 1+2+3 후에도 실패하면 **영어 fallback 유지**(DoD 허용; status='failed' 계약 불변). 절대 math 깨서 끼워넣지 않음(8b 계약).
- **B. 볼드 method spike** (extract, doc7 검증, **decision gate**):
  - MinerU backend별 볼드 출력 규명: `pipeline`(현, CPU) vs `vlm/hybrid`(GPU 필요?) — doc7 챕터 PDF(`~/mineru_test/doc7_chapter_990-1000.pdf`, 11p)로 실측.
  - 볼드 추출 가능(현 가용 HW)하면: 추출 recipe 확정 + 재ingest로 `**` 포함 + reflow `<strong>` 렌더 검증.
  - GPU 필요(CPU 불가)하면: 실측 비용 보고 → **사용자 결정 gate**(1회성 GPU 볼드 추출 vs 볼드 defer). 8e-1은 math로 PASS, 볼드는 finding+recipe 문서화.

**Out**
- 7-doc 배치 적용 = 8e-2(이 phase는 doc7 method 검증만). cutover/CI/schema-head = 8e-3. cross-doc live = 8e-3. book2 full 1370p = cutover 후. 웹/논문 검색 = 8f.

## Approach
### A. math 강건화 (chunk_pipeline.py + math_protect.py)
- `_translate_protected`: `restore_math`→`missing` 있으면 raise 대신 **재시도 루프**로 이동. N회(기본 2) 재번역 후에도 missing이면 **segment fallback** 호출.
- `_segment_translate(text, ...)`: 문장경계(정규식 또는 기존 util) 분할 → 각 세그먼트 protect/translate/restore → missing 0인 세그먼트만 결합. 전 세그먼트 성공 시 translated, 일부 실패 시 status='failed'(영어 fallback) — **부분 한국어로 math 깨는 것 금지**.
- sentinel: `math_protect.protect_math(token_prefix=...)`는 이미 prefix 파라미터화. 후보 형식(예: `⟦MATHi⟧` vs ASCII-robust)을 prefix/brackets 상수로 분기, doc7 실측으로 선택. 변경 시 `restore_math`/collision/8b 테스트 전부 green 유지.
- **byte-identical 불변**: 성공 경로의 math run은 store에서 그대로 복원(현 계약). retry/segment는 *복구 여부*만 바꾸고 복원 바이트는 불변.

### B. 볼드 method spike (extract_mineru)
- `run_mineru`로 doc7 챕터를 backend별 추출, 출력 md의 `**` 유무/정확도 비교(CPU에서 vlm/hybrid 동작 여부 포함 — 안 되면 그 자체가 finding).
- 가능 시: ingest→chunks content에 `**`→reflow 렌더(jsdom 또는 수동) `<strong>` 확인. enrich_inline/참조점프(8d-1)와 볼드 공존 확인.

## File-level changes (예상)
| Path | Action | Note |
| ---- | ------ | ---- |
| `src/ht_lens/translate/chunk_pipeline.py` | 수정 | math-loss-aware retry + `_segment_translate` fallback |
| `src/ht_lens/translate/math_protect.py` | 수정(보조) | sentinel 형식 견고화(파라미터/상수), byte-identical·collision 불변 |
| `tests/integration/test_chunk_translate.py` 등 | 수정/신규 | retry-recovers / segment-recovers / still-fails→영어 / byte-identical 회귀 / sentinel |
| (B 가능 시) `extract_mineru/runner.py` | 수정 | backend/볼드 recipe (또는 finding만 문서화) |
| (B 가능 시) reflow 렌더 테스트 | 신규 | `**`→`<strong>` jsdom |

## Dependencies (new)
| Package | Why |
| ------- | --- |
| (없음) | qwen/MinerU/marked 기존. 신규 0. |

## Test strategy
- **math retry**: mock LLM이 attempt 0에서 placeholder drop, attempt 1에서 보존 → status=translated, missing 복구. (결정적)
- **segment fallback**: mock가 큰 chunk(다중 $)에서는 drop, 작은 세그먼트에서는 보존 → 재조립 translated. 전 세그먼트 실패 → status='failed'(영어 보존).
- **byte-identical 회귀**: 기존 8b `test_text_translated_with_math_preserved` 등 green 유지 + 새 경로도 math run 바이트 동일.
- **sentinel**: protect/restore round-trip byte-identical(신 형식), collision guard 유지, display-before-inline.
- **last-resort**: 모든 lever 실패 시 status='failed' + content 미변경(8b no-write 계약).
- **live(doc7)**: 실 qwen으로 6 failed chunk 재처리 → 한국어 전환 수(목표: 대폭 감소, 잔존 영어는 명시). dev DB만, prod 불변.
- 회귀 761→761+신규. ruff/format/mypy clean. 1.x prod 0004/blocks=49850/chunk_tables=0.

## DoD mapping
| DoD item | How to satisfy | Evidence plan |
| -------- | -------------- | ------------- |
| 수식밀집 영어 fallback 교정 | retry + segment fallback (+sentinel) | doc7 6곳 live 한국어 전환 + 단위 테스트 |
| math byte-identical 보존 | 복원 경로 불변, 성공만 변경 | byte-identical 회귀 테스트 green |
| 볼드 method | backend spike + (가능시)recipe·렌더 / (GPU시)finding+gate | doc7 추출 비교 + 결정 문서화 |
| 1.x 무손상 | translate/extract만, migration 0 | prod 0004/49850/0 |

## 위험 / 완화
- **byte-identical 깨기(절대 금지)** → 복원은 store 원본만, retry/segment는 복구여부만. 회귀 테스트 + last-resort 영어 fallback.
- retry 무한/비용 → bounded(기본 2) + segment 1회 + 영어 fallback. 결정적 테스트.
- sentinel 변경이 8b 회귀 → protect/restore/collision/display-inline 전 테스트 + byte-identical.
- **볼드 CPU 불가(GPU 필요)** → spike로 실측, GPU면 사용자 gate(1회성 vs defer); math는 독립 PASS. (모호하면 사용자 결정 — prompt 명시)
- segment 분할이 문맥 끊어 번역 품질↓ → 세그먼트는 fallback 전용(정상은 whole-chunk), 문장경계 보존.
- live 일부 영어 잔존 → DoD 허용("안 되면 일부 영어 잔존"); summary에 잔존 수 명시.

## 결정 필요 (challenge/구현 중 surface)
- 볼드: CPU backend로 추출 불가 시 — (a) 1회성 GPU vlm/hybrid 추출 허용? (b) 볼드 defer(8e-2/follow-up)? — spike 실측 후 사용자에게.
- sentinel 형식: doc7 실측 손실률로 결정(경험적, plan 단계 추측 금지).
