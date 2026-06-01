# Phase 8d-1 — Challenge

Codex debate는 정밀했고 실 결함을 다수 잡음. 대부분 accept. 단 1건(backend section 모델)은 Planner의 frontend-only split을 지키되 coupling 우려는 secNo 이벤트로 해소(8d-2 server-side resolve).

## Debate responses
### 1. Over-engineering
- **partial**. "frontend domain model 조기화" → backend section 모델은 **8d-2로 이연**(chat이 server-side 경계 필요할 때 canonical 구현). 8d-1은 frontend TOC/jump/select만. **단 coupling 방지**: `sectionselect` 이벤트가 opaque chunkIds가 아니라 **secNo(원문 기반 안정 식별자)** 를 1차로 실음 → 8d-2 chat이 secNo→chunk를 server-side 재계산.
- **accept**: 합성 missing-prefix 노드(28.3 부재 시 가짜 노드) **제거**. 관측 heading만으로 트리, 부모는 **가장 가까운 관측 조상**(prefix)에 연결, 없으면 root. 가짜 노드 0.
- **reject(부분)**: nested 트리 자체는 사용자가 명시 요청한 "28 > 28.3 > 28.3.5 계층"이라 유지(flat 대안 §4 비채택). 단 합성 없이.

### 2. Hidden assumptions
- **accept (중요)**: 섹션 식별은 `chunk.translated`가 아니라 **`chunk.original`** 에서 파싱. `renderChunk`가 heading의 `original`로 `data-sec`를 부여 → 번역 artifact 무관. sectionNums 집합도 original 기반.
- **accept (실 결함)**: 인용 정규식이 `[KO]` 매칭. **≥1 digit 필수**로 수정: `\[[A-Za-z][\w.'+-]*\d[\w.'+-]*\]` 류 → `[KO]/[EN]/[Note]` 제외, `[BJ05]/[CDS02]/[Kha+10]/[Hot36]` 포함. 테스트로 잠금.
- **accept**: "innerHTML 미사용 = XSS 무관"은 과한 일반화. `renderToc`/스타일러는 **createElement+textContent only**. 기존 `load()`의 `innerHTML=e.message`(에러 경로)는 8d-1 신규 아님(불변). 보안 증명으로 주장 안 함.
- **partial**: cross-doc/챕터 외 참조는 8d-1 범위 밖(단일 doc). 집합 외 참조는 **plain text 유지(미링크, 미파손)**. cross-doc 참조 해소는 8d-2 RAG.

### 3. Edge cases
- **accept (실 결함)**: `.rf-ref` 클릭이 chunk click(`reflow.js:157`→syncToChunk)으로 버블 → **`stopPropagation()`+`preventDefault()`**. 테스트로 잠금.
- **accept**: 섹션 선택 경계 정의 — 선택 섹션 heading부터 **다음 동급-또는-상위 깊이 heading 직전까지**(부모 선택 시 자식 서브섹션 포함). 테스트로 잠금.
- **accept**: KaTeX skip은 **`closest('.katex')`** (nested `.katex-html`/`.katex-mathml` 포함). 직접 부모 클래스만 보지 않음.
- **accept**: `parseSectionNo` 방어 — 선두 `§`/공백 허용, 후행 점 허용(`28.4.2.`), `Appendix A.1`/`§28.4`/전각문장부호는 미파싱 시 **번호없는 섹션**으로 TOC에 title만 표시(안 깨짐). 테스트로 잠금.
- **accept (중요)**: TOC 레이아웃이 compare grid(`1fr 1fr`, `reflow.css:38`) 파손 위험 → TOC를 **그리드 밖 collapsible drawer/overlay(토글)** 로 배치. compare 2-pane 불변. 레이아웃 테스트 추가.

### 4. Alternative approaches
- **defer**: `/v2/reflow`에 `sections[]` 추가(§4) → **8d-2에서 채택**(chat context의 canonical source). 8d-1은 frontend-only(Planner split) 유지. coupling은 secNo 이벤트로 해소(위 §1).
- **accept**: 인라인 enrich는 **TreeWalker로 텍스트노드 수집 → 노드별 DocumentFragment 1회 치환**(인용+참조 동시). 반복 `splitText`(인접/다중 매칭 취약) 대신. 테스트로 잠금.
- **accept(부분)**: `data-sec`는 rendered DOM 재파싱이 아니라 **renderChunk 시 `chunk.original`로 부여**. select/jump은 `.chunk[data-sec]`/order 기반(텍스트 의존 X).

### 5. Missing tests — 전부 accept (추가)
1. `test_citation_regex_excludes_digitless_markers` — `[KO]/[EN]/[Note]` 비스타일, `[BJ05]/[Kha+10]` 스타일.
2. `test_section_id_from_original_when_translation_changes_prefix` — original `28.4.2 …` + translated `[KO] 다항 PCA` → secNo `28.4.2` 존재.
3. `test_ref_click_does_not_trigger_chunk_sync` — `.rf-ref` 클릭 시 source chunk `.active` 미부여·PDF pane 미스크롤.
4. `test_select_parent_includes_children_until_next_sibling` — `28.4` 선택 → `28.4.1`/`28.4.2` 포함, `28.5` 직전 정지.
5. `test_enrich_multiple_adjacent_matches_one_node` — `[BJ05][CDS02] see 28.3.5 and 28.4.2` 모든 wrap, 텍스트 무손실.
6. `test_toc_compare_layout_keeps_both_panes` — `data-mode="compare"` + `#toc` 시 두 pane 가시(jsdom 클래스/구조 검증).

## Plan revisions (after debate)
- R1 인용 정규식 ≥1 digit 필수.
- R2 섹션 식별 `chunk.original` 기반, `data-sec`는 renderChunk가 부여.
- R3 backend `sections[]`는 8d-2로 이연; `sectionselect`는 **secNo** 1차 탑재(opaque chunkId coupling 회피).
- R4 `.rf-ref` 클릭 stopPropagation+preventDefault.
- R5 KaTeX skip = `closest('.katex')`.
- R6 TOC = grid 밖 collapsible drawer/overlay; compare 2-pane 불변 + 레이아웃 테스트.
- R7 섹션 선택 경계 = 다음 동급/상위 heading 직전(부모는 자식 포함), 테스트.
- R8 enrich = TreeWalker + 노드별 DocumentFragment 1회 치환.
- R9 트리: 합성 노드 없음, 부모는 가장 가까운 관측 조상.
- R10 renderToc/스타일러 = createElement+textContent only.
- R11 집합 외/cross-doc 참조 = plain text 유지(미파손).
- R12 parseSectionNo 방어 + 6 신규 테스트 전부 추가.

## DoD checklist
| DoD item | Status | Evidence |
| -------- | ------ | -------- |
| 인용/참조 스타일 (A) | 계획 | enrich 테스트(≥1digit, 다중매칭, KaTeX-safe) |
| 섹션 트리 (B) | 계획 | buildSectionTree 테스트(깊이/누락/합성없음) |
| 섹션 선택 (B) | 계획 | select 테스트(부모=자식포함, secNo 이벤트) |
| 참조 점프 (B) | 계획 | jump 테스트(scroll+flash, stopPropagation) |
| 볼드→8e | 명시 | 데이터 부재, 인용/참조로 대체 |
| KaTeX/번역/레이아웃 무손상 | 계획 | closest(.katex)·기존10 jsdom·compare 레이아웃 테스트 |
| 1.x 무손상 | 계획 | API/DB 변경 0, blocks=49850 불변, 677 회귀 |

## Risk register
| Risk | Likelihood | Impact | Mitigation |
| ---- | ---------- | ------ | ---------- |
| 참조 vs 식/그림 번호 오인 | 중 | 중 | heading secNo 집합 멤버십만 linkify |
| 번역이 heading 번호 변경 | 저 | 중 | original 기반 파싱(R2) |
| ref 클릭 버블→이중 동작 | 중 | 중 | stopPropagation(R4) + 테스트 |
| TOC가 compare 레이아웃 파손 | 중 | 중 | grid 밖 drawer(R6) + 레이아웃 테스트 |
| enrich가 math/텍스트 손상 | 중 | 고 | closest(.katex) + TreeWalker 1회치환 + 테스트 |
| 8d-2가 client 경계 신뢰 | 저 | 중 | secNo 이벤트(R3), 8d-2 server-side resolve |

## Decision
- [x] **PASS → proceed to code** (revisions R1–R12 반영). frontend-only(Planner split) 유지, 모든 correctness fix accept, backend section 모델은 8d-2 이연(secNo로 coupling 해소).
- [ ] RE-PLAN
