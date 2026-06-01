# Phase 8b — Challenge (debate 대응)

**Decision: PASS** (정제 후 진행, RE-PLAN 아님). 핵심 접근(7a-2 머신 일반화 + placeholder 보호 + chunk-parallel embedding)은 건전. Codex 지적 다수 수용 — 특히 3개 contract fix.

## Debate responses

### 1. Over-engineering
- **chunk_store/chunk_backfill 중복** → **partial accept**. 별도 subsystem 아님. `vector_to_bytes/from_bytes/text_source_hash/EmbeddingClient` 재사용, table/PK만 다른 thin `upsert_chunk_embedding`(store.py에 추가) + `chunk_backfill`(candidate/needs/batch 로직 동형). 중복 최소화.
- **missing-placeholder append가 byte-identical 위반** → **accept (강)**. append-comment는 reading order 훼손. **변경: 복원 시 placeholder 누락이면 해당 chunk를 `status='failed'`로 마킹**(content 미변형), retry 대상. byte-identical = 성공 번역은 수식 byte-identical, 실패는 flag(손실/변형 0).
- **extract-mineru CLI 테스트가 8a cleanup** → **hold (사용자 결정 4)**. Planner가 8b에서 closure 지시. challenge에 명시.
- **caption_translated가 image-specific** → **clarify**. 실제로 generic("caption 보유 chunk 공통 번역 캡션"). image/chart/table 공용. 문서화.

### 2. Hidden assumptions
- **type 택소노미 text/heading vs title/header** → **accept (lock)**. 8a 파서 실제 출력 = `text/heading/equation/image/table/unknown` (1.x `header`는 block 전용, 무관). backfill 필터 `(text, heading)` 파서 출력과 일치. 테스트로 잠금.
- **cache_key=hash(content) 오류** → **accept (핵심 fix)**. 기존 `cache_key(text, src, tgt, model)` 4-튜플 그대로 사용 (model/lang 교차 재사용 방지). plan의 "hash(content)"는 약식 표기였음 — content가 text 인자.
- **이웃 context 8d 이동이 scope change** → **hold (Planner 승인됨)**. 결정 3에서 사용자가 단독 명시 승인 + 5.66x 근거. ROADMAP wording은 사용자가 정정 예정. challenge 기록.
- **Semaphore(7)가 긴 chunk에 부적합** → **partial**. 기본 7 유지(--concurrency 설정형), 긴 chunk 타임아웃 리스크 주석. 실 튜닝은 8e.
- **embed content vs translated_text** → **accept (결정 + 문서화)**. 1.x가 original_text(영어) 임베딩 → chunk도 `content`(소스) 임베딩으로 **parity 유지**(8d cross-doc search가 1.x 코퍼스와 비교 가능). 한국어측 retrieval 우위는 8d에서 재검토. source_hash=hash(content).

### 3. Edge cases
- **math regex edge (\$, \text{$5}, $5 to $10, \[ \(, bare LaTeX)** → **partial accept**. regex 유지 + 광범위 edge 테스트. 핵심 안전장치: **false-positive match도 byte-identical 복원**이라 손상 0 (해당 run이 미번역될 뿐). `\[\]`/`\(\)`는 MinerU가 본문에 거의 안 씀(equation은 passthrough). 풀 토크나이저(§4 alt)는 8b 과설계 → regex+byte-identical+테스트가 비례.
- **placeholder collision (소스에 ⟦MATH0⟧)** → **accept**. protect 전 소스에 `⟦MATH` 패턴 있으면 로그+보수 처리(내가 만든 정확한 ⟦MATHi⟧ 토큰만 인덱스로 복원). 테스트.
- **chart content 손실** → **accept (핵심 fix)**. image chunk에 content 있으면(chart) `translated_text=translate(content)`, caption→caption_translated. chart 텍스트 보존.
- **table HTML/LaTeX 손상** → **partial**. doc7 챕터 table 0개. text 동일 protect→번역, `|` 안전. HTML table 손상 테스트 추가(§5). 실검증 8e.
- **retry_failed/cancel/status 누락** → **accept (강)**. 7a-2 contract 보존: retry_failed, as_completed 예외 시 task cancel, doc status finalize. 충실 재사용.

### 4. Alternative approaches
- 엔진 추출 어댑터 → **partial**. chunk_pipeline은 7a-2 구조를 chunk로 일반화(어댑터 수준 재사용), 단일 테스트 지점 지향.
- caption 일반화 → accept (caption_translated generic).
- 토크나이저 → reject (8b 과설계).
- embedding 파라미터화 → accept (helper 재사용).

### 5. Missing tests — **전부 accept**
cache_key(src/tgt/model), peak-concurrency(병렬 증명, dedup만 아님), math escaped/text/currency, placeholder collision, chart content+caption, table HTML, FK cascade, CLI(schema mismatch/retry_failed/embed unavailable), model-change refresh.

## Plan revisions (after debate)
1. cache_key = `cache_key(content, src, tgt, model)` 4-튜플.
2. missing placeholder → chunk `status='failed'` (append-comment 폐기).
3. image/chart: content 있으면 translated_text 번역 + caption→caption_translated.
4. 7a-2 contract 보존: retry_failed, cancellation, doc status finalize.
5. embedding: store helper 재사용(thin upsert_chunk_embedding + chunk_backfill), 별도 subsystem 아님.
6. type 택소노미 파서출력 lock; backfill `(text, heading)`.
7. embed `content`(소스, 1.x parity); 8d 재검토 문서화.
8. placeholder collision 가드.

## DoD checklist
| DoD | Status | Evidence(계획) |
| --- | --- | --- |
| chunk 번역 + placeholder byte-identical | planned | test_math_protect byte-identical + placeholder 잔존 0 + missing→failed |
| embedding 생성 | planned | test_chunk_embed + COUNT |
| 7a-2 5.66x 적용 | planned | cache dedup + peak-concurrency 병렬 테스트 + Semaphore(7) + retry/cancel/status |

## Risk register
| Risk | L | I | Mitigation |
| --- | --- | --- | --- |
| 0006 1.x ALTER 실수 | 낮 | 높 | additive-only diff 테스트 |
| missing placeholder 손실 | 중 | 높 | status=failed + 테스트 |
| math regex false-positive | 중 | 낮 | byte-identical 복원으로 손상 0 + edge 테스트 |
| 긴 chunk 타임아웃 | 중 | 중 | --concurrency 설정형, 8e 튜닝 |
| 1.x embedding 깨짐 | 낮 | 높 | rename 안 함, ADD |

## Decision
- [x] **PASS → proceed to code** (8 plan revisions 반영)
- [ ] RE-PLAN
