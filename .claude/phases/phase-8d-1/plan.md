# Phase 8d-1 — Plan (마크다운 인라인 보존 + 섹션 트리/선택/참조점프)

## Goal
reflow 읽기 뷰에 인용/섹션참조 인라인 스타일링(A)과 섹션 트리·선택·참조점프(B)를 추가한다 — **순수 frontend, LLM 없음**. (chat/핀/RAG/섹션질문 = 8d-2.)

## 배경 (8c eval + Stage 0 실측)
사용자가 8c reflow(doc7 실 qwen)를 읽고 3개 요청: 섹션 단위 선택, 볼드/링크/참조 보존, (chat). Planner가 8d를 8d-1(A+B)/8d-2(C)로 분할 확정. Stage 0 발견이 plan 가정을 바꿈:
- **볼드 부재**: MinerU가 볼드 제거 (has_bold=0, 103/103). 보존할 볼드가 데이터에 없음 → **인용[BJ05](21곳)+섹션참조(28.3.5)만 스타일링** (Planner 확정). 진짜 볼드는 8e 재추출.
- **text_level 평탄**: heading 16개 전부 text_level=2. 섹션 트리는 text_level이 아니라 **heading content의 점표기 섹션번호 깊이**(28.4 > 28.4.2 > 28.4.2.1)로 구성.
- **참조 vs 식번호**: 점표기 숫자는 섹션(28.3.5)·식((28.116))·그림(28.22)이 섞임 → **실제 heading 섹션번호 집합에 있는 것만 linkify** (28.116은 heading 아님 → 무시). 자연 disambiguation.

## Scope
**In (8d-1)**
- A. 인용 `[BJ05]`·섹션참조 `28.3.5` 인라인 스타일링 (KaTeX-safe, DOM-only).
- B. heading 점표기 → 섹션 트리(목차) UI + 섹션 점프(참조 클릭) + 섹션 선택(범위 하이라이트 + 선택 상태/이벤트).
- frontend만: `reflow.js` + 신규 `js/utils/enrich_inline.js`, `js/sections.js` + `reflow.css` + `reflow.html`. **API/DB/LLM 변경 0** (트리는 기존 `/v2/reflow` 응답에서 client-side 파생).

**Out (→8d-2, 결정 locked)**
- chat(문단/섹션 질문), 핀, RAG, figure 채팅, neighbor 재번역. 섹션질문 context=**하이브리드**, neighbor 재번역=**짧은/저문맥 chunk만** (Planner 확정, 8d-2에서 구현).
- 진짜 볼드 (8e MinerU 재추출). 영어 fallback 6곳 (8e math 강건화).

## Approach
### A — 인라인 스타일러 (KaTeX-safe, 의존성 0)
- 신규 `enrichInline(el, sectionNums)` (순수 함수, export):
  - `applyMath(el)` **이후** 호출 → `.katex`/`pre`/`code` 하위 텍스트노드는 skip (math/코드 미손상).
  - 남은 텍스트노드만 walk, 정규식 매칭 substring을 `splitText`로 분리해 `<span>`/`<a>`로 감쌈 (**innerHTML 미사용 → XSS 무관**, marked/DOMPurify 불요).
  - 인용: `\[[A-Za-z][A-Za-z.'-]*(?:\+)?\d{0,4}[a-z]?\]` 류 (BJ05, CDS02, Kha+10, Hot36) → `<span class="rf-cite">`.
  - 섹션참조: `\d+(?:\.\d+)+` 중 **sectionNums 집합에 속한 것만** → `<a class="rf-ref" data-sec="…">` (B 점프와 연계). 집합 외(식/그림 번호)는 무시.
- **marked 미적용 (chunk)**: chunk에 marked 쓰면 LaTeX `$x_n$`의 `_`/`*`를 markdown으로 오인 + 보존할 볼드 없음 → 인라인 스타일러가 안전·충분. marked/DOMPurify(이미 vendored)는 8d-2 chat 메시지 렌더용.

### B — 섹션 트리 / 점프 / 선택 (client-side)
- `parseSectionNo(text)` → heading 선두 점표기 추출("28.4.2 Multinomial PCA"→"28.4.2"), 깊이=세그먼트 수.
- `buildSectionTree(chunks)` → heading chunk들로 중첩 트리. 부재 중간노드(이 챕터는 28.3.5부터 시작, 28.3 heading 없음)는 **공통 prefix 그룹화로 graceful**(합성 라벨 또는 관측 최상위에서 시작), 누락에 안 깨짐.
- 목차 UI: `reflow.html`에 `<nav id="toc">`, `renderToc(tree)`가 중첩 `<ul>` 렌더. 노드 클릭 → 해당 heading chunk로 `scrollIntoView` + flash 하이라이트.
- 섹션 선택: 목차 노드의 "선택" 어포던스 → 그 섹션 heading부터 **다음 동급/상위 섹션 직전까지** chunk에 `.section-selected` 부여 + `CustomEvent('sectionselect', {detail:{secNo, chunkIds}})` 발행(8d-2 chat가 소비). 문단(chunk) 클릭 선택과 **시각·상태 구분**.
- 참조 점프: `.rf-ref` 클릭 → `data-sec`로 heading chunk 찾아 scroll+flash (A와 동일 타깃).

## File-level changes
| Path | Action | Note |
| ---- | ------ | ---- |
| `src/ht_lens/api/static/js/utils/enrich_inline.js` | 신규 | `enrichInline(el, sectionNums)` 순수 export, KaTeX-safe DOM-only |
| `src/ht_lens/api/static/js/sections.js` | 신규 | `parseSectionNo`/`buildSectionTree`/`renderToc`/`jumpToSection`/`selectSection` export |
| `src/ht_lens/api/static/js/reflow.js` | 수정 | load()에서 sectionNums 산출→chunk별 enrichInline, 트리 빌드→renderToc; ref-click 위임 |
| `src/ht_lens/api/static/reflow.html` | 수정 | `<nav id="toc">` 컨테이너 추가 |
| `src/ht_lens/api/static/css/reflow.css` | 수정 | `.rf-cite`/`.rf-ref`/`#toc`/`.section-selected`/flash |
| `tests/integration/test_reflow_enrich_js.py` | 신규 | jsdom: 인용/참조 스타일, 식번호 비linkify, KaTeX-safe |
| `tests/integration/test_reflow_sections_js.py` | 신규 | jsdom: 트리 구성(깊이/누락), 점프 scroll, 섹션 선택 범위+이벤트, 목차 렌더 |

## Dependencies (new)
| Package | Why |
| ------- | --- |
| (없음) | marked/DOMPurify는 이미 vendored(chunk엔 미사용). 신규 의존성 0. |

## Test strategy
- jsdom 서브프로세스(8c `_PRELUDE`/`_run` 패턴 재사용): `enrichInline`·`buildSectionTree`·`jumpToSection`·`selectSection`를 export해 in-suite 단위 잠금.
- A: `[BJ05]`→`.rf-cite`; 섹션참조 `28.3.5`(집합 내)→`.rf-ref[data-sec]`; `28.116`(집합 외)→비linkify; `$x_n$` 내부·`.katex` 미손상; 한국어 문장 보존.
- B: heading 목록→트리(28.4>28.4.2>28.4.2.1, 누락 28.3 graceful); 참조 클릭→scrollIntoView 호출+flash; 섹션 선택→범위 chunk `.section-selected`+`sectionselect` 이벤트 detail; `renderToc`→중첩 `<ul>` DOM.
- 회귀: 기존 reflow jsdom(10) green 유지; 전체 `pytest -m "not llm and not slow"` 677→677+신규.
- ruff/format/mypy clean (신규 .py 테스트만; JS는 비대상).

## DoD mapping (8d-1 = 사용자 A+B 목표의 frontend 부분)
| DoD item | How to satisfy | Evidence plan |
| -------- | -------------- | ------------- |
| 인용/섹션참조 스타일 보임 (A) | enrichInline 인용/참조 wrap | test_reflow_enrich_js + 사용자 시각(8086) |
| 섹션 트리 표시 (B) | buildSectionTree+renderToc | test_reflow_sections_js(트리) + 시각 |
| 섹션 선택 (B) | selectSection 범위 하이라이트+이벤트 | test_reflow_sections_js(선택) |
| 참조 28.3.5 클릭→점프 (B) | .rf-ref→jumpToSection scroll+flash | test_reflow_sections_js(점프) |
| 볼드는 데이터 부재→8e | 정직 기재(스코프 외), 인용/참조로 대체 | plan/summary 명시 |
| KaTeX/번역 무손상 | enrich는 applyMath 후·텍스트노드만 | test(KaTeX-safe) + 기존 10 jsdom green |
| 1.x 무손상 | API/DB 변경 0, frontend만 | data/ht_lens.db blocks=49850 불변 + 677 회귀 |

## 위험 / 완화
- 섹션참조 vs 식/그림 번호 오인 → **heading 섹션번호 집합 멤버십**으로만 linkify (28.116 무시).
- 누락 중간 섹션(28.3 없음) → prefix 그룹화 graceful, 단위테스트로 잠금.
- 인라인 스타일러가 math/한글 손상 → applyMath 후 텍스트노드만·`.katex` skip, KaTeX-safe 테스트.
- 단일 JS 모듈 비대 → enrich/sections 모듈 분리(8d-2 chat 모듈 분리 토대).
- 섹션 선택 UI와 문단 클릭(syncToChunk) 충돌 → 시각·상태·이벤트 분리(섹션=`sectionselect`, 문단=기존 click).
