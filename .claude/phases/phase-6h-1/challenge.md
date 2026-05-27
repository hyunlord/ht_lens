# Phase 6h-1 — Challenge (Worker response to Codex debate)

## Summary decision: **RE-PLAN**

Codex raised 15+ substantive points. 5개는 critical (rotation 무시, header raw-line count, backfill partial commit, KPI test 부재, edge case heuristic). 그 외는 substantive 개선 또는 scope 조정. plan V2 작성 필요.

11 ACCEPT / 3 PARTIAL / 1 REJECT.

## Debate responses

### 1. Over-engineering

#### §1.1 backfill scope too wide (mutates original_text + bbox) — **PARTIAL**
- Codex 주장: bbox만 update이면 충분. original_text 변경은 embedding source_hash 흔들기.
- 확인: 본 fix의 핵심은 stored text의 `\n` → space 변환. bbox는 부수적 (이미 정상 union). original_text 변경 자체가 본 phase의 산출물.
- **결론 V2**: bbox 변경은 사실상 거의 없다 (`_union`이 이미 옳음). original_text 변경이 main. Codex 우려 (embedding stale) 는 §2.3에서 별도 처리. backfill script 이름 `backfill_block_text.py` 권장.

#### §1.2 backfill PDF discovery / fleet iteration too much — **PARTIAL**
- Codex 주장: PDF path 결정 + `--all` 옵션 + fuzzy matching이 phase scope 초과.
- **결론 V2**: `scripts/backfill_block_text.py --doc-id N --pdf <path>` 형태. `--all` 제거. PDF path는 사용자가 명시. 단순화.

#### §1.3 Hot-fix A1 removal premature — **ACCEPT**
- Codex 주장: backfill이 optional → 옛 doc은 여전히 Phase 6h symptoms. A1 제거하면 사용자가 옛 doc에서 인지 못 함.
- **결론 V2**: A1 제거를 본 phase에서 **제외**. 별도 후속 작업 (backfill 완료 후 사용자 결정).

### 2. Hidden assumptions

#### §2.1 ROADMAP 재해석 (Alembic 0005 누락) — **ACCEPT (명시 필요)**
- ROADMAP.md를 사용자가 수정 중. Phase 6h-1 spec에 Alembic 0005가 명시되었는지 재확인 필요.
- **결론 V2**: plan V2에서 "본 phase는 스키마 변동 0이므로 Alembic 0005 불필요. ROADMAP §6h-1에 0005가 명시되어 있다면 ROADMAP 수정 권장 (사용자 직접)." 명시.

#### §2.2 단일 probe로 ROADMAP audit (6,912) 무효 가정 — **ACCEPT**
- Codex 주장: 단일 probe로 audit 무효화 못 함. KPI 측정 누락.
- **결론 V2**: 신규 `tests/integration/test_phase_6h1_kpi.py` — audit measurement. Backfill 안 한 상태에서 본 phase commit만으로는 audit 변화 0 (기존 doc은 그대로). KPI 변화는 backfill 후. DoD에 "신규 extract부터 적용, 기존 doc은 backfill 시 변화" 명시.

#### §2.3 Translation / embedding 보존 false claim — **ACCEPT (critical)**
- Codex 주장: `original_text` 변경 시 `text_source_hash` 변경 → stored block_embeddings stale. `search.py`는 source_hash 검증 안 함. RAG candidate에 stale 사용.
- **결론 V2**: backfill script 완료 시 **manual refresh 가이드**: `ht-lens embed --doc-id N` 호출 (embedding/backfill 자동 stale 감지 + refresh, Phase 7a 동작). plan V2의 Sub-goal 3 + summary에 명시.

#### §2.4 Header detection은 raw line count → 잘못 — **ACCEPT (critical)**
- Codex 주장: `len(para_lines) <= _HEADER_MAX_LINES=2`는 raw PyMuPDF line 수. 한 visual line이 3 fragments로 split되면 header eligibility 잃음.
- **결론 V2**: visual-line count 도입. `_count_visual_lines(para_lines)` helper:
  ```python
  def _count_visual_lines(lines: list[RawLine]) -> int:
      if not lines: return 0
      n = 1
      for prev, cur in pairwise(lines):
          if not _should_concat_inline(prev, cur):
              n += 1
      return n
  ```
- header check 변경: `_count_visual_lines(para_lines) <= _HEADER_MAX_LINES`.

### 3. Edge cases

#### §3.1 Superscript / subscript false-positive y-overlap — **ACCEPT (heuristic 강화)**
- **결론 V2**: threshold 50% → 60% + 추가 조건: height 차이 30% 이내 (대등한 line). superscript는 작고 위로 튀어남 → height 차이 큼.

#### §3.2 Multi-line real text가 50% 미만 overlap이면 newline 유지 — **ACCEPT**
- PDF baseline 기준 grouping이면 same-line은 보통 100% overlap. 60% threshold 안전.

#### §3.3 RawLine.direction 무시 (rotated 회귀) — **ACCEPT (critical)**
- Codex 주장: 회전 페이지에선 horizontal 체크 필요. `tests/integration/test_rotated_page.py` 존재.
- **결론 V2**: `_should_concat_inline` 진입 시 두 line 모두 horizontal 확인 → 비-horizontal이면 `\n` 유지 (기존 동작 보존).

#### §3.4 Backfill partial commit (hybrid doc) — **ACCEPT (critical)**
- Codex 주장: 일부 page mismatch 시 이전 page 이미 update queued → hybrid doc.
- **결론 V2**: backfill 도구를 **per-doc all-or-nothing** 으로. 한 page mismatch면 그 doc 전체 abort. atomic transaction.

### 4. Alternative approaches

#### §4.1 Span/word level y-clustering — **REJECT (사용자 결정 A 우선)**
- 사용자 결정 A "Y-overlap 감지 + space join (Recommended)" 선택. 본 작업은 string-join level 최소 변경. span/word level 재설계는 향후 phase.

#### §4.2 Document-level all-or-nothing — **ACCEPT** (§3.4와 결합)

#### §4.3 Frontend fitFontSize fix — **REJECT (root cause 위치 다름)**
- Root cause는 stored text format. Frontend는 받은 데이터 정확히 렌더. backend fix 유지.

### 5. Missing tests (모두 ACCEPT 5개 중 4개)

| Codex 제안 | V2 채택 |
| --------- | ------- |
| KPI script test (`6,912 → <500`) | ✅ 신규 `test_phase_6h1_kpi.py` — synthetic input으로 logic 측정 |
| Header regression (3 fragments → header) | ✅ `test_header_split_into_3_horizontal_fragments_still_classified_as_header` |
| Backfill atomicity | ✅ `test_backfill_aborts_doc_on_any_page_mismatch` |
| Embedding consistency | ✅ summary 가이드 + manual refresh |
| Alembic 0005 migration | ❌ (스키마 변동 없음) |

## Plan revisions (V1 → V2)

1. **CRITICAL fix `_should_concat_inline`**: direction (horizontal) + threshold 60% + height similarity 추가.
2. **CRITICAL header detection**: `_count_visual_lines(para_lines)` → header check 적용.
3. **CRITICAL backfill atomicity**: per-doc all-or-nothing transaction.
4. **Embedding stale 정책**: backfill 후 manual `ht-lens embed --doc-id N` 가이드.
5. **Hot-fix A1 제거 → 본 phase 외**로 분리.
6. **Backfill script 단순화**: `--all` 제거, PDF path 명시.
7. **신규 KPI test**: audit-style measurement.
8. **추가 tests**: header preservation, backfill atomicity.
9. **ROADMAP Alembic 0005 issue 명시**: V2에서 "스키마 변동 없음, 0005 불필요" 기록.
10. **Original_text 변경 명시**: backfill main change는 text format. bbox는 대부분 동일.

## DoD checklist (V2)

| DoD item | Status | Evidence |
| -------- | ------ | -------- |
| Same-visual-line text는 space join | Open | unit + smoke |
| Distinct-visual-line text는 `\n` join | Open | unit |
| Single-line block 무영향 | Open | unit |
| Header 보존 (visual line count) | Open | header regression |
| Direction (rotation) 안전 | Open | rotation existing tests |
| Backfill per-doc atomic | Open | atomicity test |
| KPI measurable | Open | KPI script |
| 533 → 540+ tests | Open | full pytest |
| Original_text 변경 인지 (embed refresh) | Open | summary 가이드 |

## Risk register (V2)

| Risk | Likelihood | Impact | Mitigation |
| ---- | ---------- | ------ | ---------- |
| Rotation 회귀 (V1 hazard) | Eliminated | Medium | direction check |
| Superscript false positive | Low | Low | threshold 60% + height similarity |
| Header miscount | Eliminated | High | `_count_visual_lines` |
| Backfill hybrid doc | Eliminated | High | per-doc atomic |
| Embedding stale post-backfill | Known | Medium | manual refresh guide |
| ROADMAP §6h-1 spec mismatch | Known | Low | ROADMAP 수정 권장 |
| KPI metric drift untested | Eliminated | Medium | KPI script test |

## Decision
- [x] PASS → proceed to RE-PLAN (V2) → code
- [ ] PASS → directly code
- [ ] RE-PLAN (reason: ) — 선택

다음: plan V2 작성 → commit → Stage 4.
