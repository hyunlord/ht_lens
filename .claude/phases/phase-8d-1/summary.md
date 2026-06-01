# Phase 8d-1 — Summary (마크다운 인라인 보존 + 섹션 트리/선택/참조점프)

## Status
**ESCALATE_TO_PLANNER** — cross-verify Round 2 = DOWNGRADE(~85), 2-round cap 도달. CLAUDE.md "Round 2 이후엔 호출하지 마라. summary.md에 양측 의견 명시하고 Planner에게 escalate" 적용. **Push 보류.** (R2는 새 production 결함·RE-CODE 회귀 없음 → Worker 권고는 PASS; 아래 양측 의견.)

## Score
- Self (verify v2): **88 / 100**
- Cross R1 (`4f1d1de`): **DOWNGRADE ~79** (실 결함 2 + gap 3) → RE-CODE → verify v2
- Cross R2 (`4393758`, 최종/cap): **DOWNGRADE ~85** (새 결함 없음, evidence/infra gap)

## What was built (frontend-only: JS/HTML/CSS, API/DB/LLM 변경 0)
- **A. 인라인 스타일링** (`js/utils/enrich_inline.js`): KaTeX-safe DOM-only(TreeWalker+DocumentFragment) 스타일러. 숫자 포함 인용 `[BJ05]`만(=`[KO]` 제외), 실 heading 섹션번호 집합에 속한 참조 `28.3.5`만 링크(식 `28.116`/그림 `28.22` plain).
- **B. 섹션 트리/선택/점프** (`js/sections.js`): heading **원문** 기반 secNo(번역 무관), 합성노드 없는 중첩 트리, 부모=자식 포함 선택→`sectionselect`(secNo 탑재, 8d-2 server resolve), 참조 클릭 capture-phase stopPropagation 점프, textContent-only TOC drawer(compare grid 밖, fixed).
- `reflow.js`/`reflow.html`/`reflow.css` 통합. 신규 의존성 0(marked/DOMPurify는 chunk 미사용).

## Files changed (8c tip `9c67ce4` → HEAD, src+tests)
```
 src/.../css/reflow.css            |  36 ++  (인용/참조/flash/section-selected/TOC drawer)
 src/.../js/reflow.js              |  43 ++  (sectionNums·enrich·data-sec·TOC·wireRefJump·toggle)
 src/.../js/sections.js            | 168 ++  (신규: parse/tree/compute/select/jump/wire/renderToc)
 src/.../js/utils/enrich_inline.js |  87 ++  (신규: enrichInline)
 src/.../reflow.html               |   3 ++  (TOC toggle + nav drawer)
 tests/.../test_reflow_enrich_js.py    | 147 ++  (5)
 tests/.../test_reflow_load_js.py      | 132 ++  (1, load 통합 — RE-CODE)
 tests/.../test_reflow_sections_js.py  | 266 ++  (9)
 8 files, +882
```

## 양측 의견 (escalate 핵심)

### Worker (self) — 88, submit-to-R2
R1 실 결함 2개(order_idx 계약 불일치, heading 자기참조) fix + load() 통합 테스트로 잠금. CI-equiv coverage(692, 75%) 실행. A+B DoD 충족, 15 신규 테스트, 1.x 무손상.

### Critic (Codex R2) — DOWNGRADE ~85
> "The RE-CODE fixes the concrete Round 1 defects, and I do not find a new production regression requiring another RE-CODE. … I do not see an untested new production path from RE-CODE."

남은 감점 사유 — **production 결함 아님**:
1. **jsdom 테스트 CI 이식성** (R2 신규): `_find_jsdom()`가 host 경로(`~/github/WorldFork/.../jsdom`, `/usr/lib/...`) 의존, repo에 `package.json`/npm 설치 단계 없음 → clean CI 러너에서 **skip** 가능 → "JS 안전망이 local-only". **단** 이는 **pre-existing**(8c `test_reflow_viewer_js.py`가 동일 `_find_jsdom` 패턴으로 이미 push됨) + **cross-cutting**(모든 jsdom 테스트) + 이 branch는 **CI 미발생**(main/PR만, 8e cutover까지).
2. **시각/브라우저 realism 얕음**: jsdom은 구조 검증(픽셀·헤더겹침·모바일 아님). frontend phase의 본질적 잔여 — verify가 수동으로 인정.
- 점수: 완결성 30/35, 안정성 26/30(jsdom CI), 확장성 17/20, 독창성 12/15 → **85**.

### Worker 평가 (R2 응답)
2건 모두 **사실**. 단 #1은 pre-existing·cross-cutting·이 branch CI 무관, #2는 본질적 수동. 새 결함·RE-CODE 회귀 **0**(Codex 명시). 8b(R2 실 결함)와 **다르고**, 8a/8c(R2 DOWNGRADE=process)와 **동형**.

## Deviations from plan
- backend `sections[]` canonical 모델 → 8d-2 이연(secNo 이벤트로 coupling 회피). challenge에서 결정.
- 볼드 미구현: 데이터 부재(has_bold=0) → 8e MinerU 재추출. 인용/참조 스타일링으로 대체(Planner 확정).
- order_idx: API 미노출 → 응답순서 신뢰(RE-CODE, R1).

## Evidence index
- plan `c3d9781` / debate `ef37254`(Codex) / challenge `5cfa3ba`(PASS R1–R12)
- feat `951999f` / test `c4b2250` / **RE-CODE** fix `4807705` + test `08e54be`
- verify v2 `5884903`(self 88) / verify-cross R1 `4f1d1de`(79) / **R2 `4393758`(85, cap)**
- 실측: ruff/format(184)/mypy(79) clean, **692 passed coverage 75%**, jsdom 25/25, 1.x blocks=49850 불변, 신규 에셋 8086 라이브 200.

## Known issues / debt
1. **jsdom CI provisioning** (R2): clean CI 러너에 jsdom 미설치 → JS 테스트 skip 위험. **8e cutover 전 필수**(main CI 작동 시점) — `package.json`+npm/jsdom 설치 단계. **repo 전역**(8c 포함), 8d-1 단독 아님.
2. 시각 자연스러움/픽셀 = 수동(사용자 8086 eval).
3. chat/핀/RAG/섹션질문/figure/neighbor = 8d-2(하이브리드 context, 짧은chunk 재번역 locked).
4. backend section 모델 = 8d-2. 진짜 볼드/cross-doc 참조 = 8e/8d-2.
5. load() 에러 경로 `innerHTML` sink = pre-existing(8c), 8d-1 무변경(Codex 재제기 안 함).

## Recommended next (Planner 결정)
- **Worker 권고: PASS** (8a/8c 선례 — R2 DOWNGRADE이나 새 production 결함·RE-CODE 회귀 0; R1 실 결함 2개는 fix+잠금 확인). → push → 8d-1 완료.
  - 단 **jsdom CI provisioning을 8e cutover 전 필수 부채로 등록**(repo 전역, 8c 포함). main CI가 JS 안전망을 실행하려면 npm/jsdom 설치 필요.
- **대안: micro-fix** — jsdom CI 단계(`package.json`+npm) 추가. 단 이는 **cross-cutting 인프라**(ci.yml + repo 전역, 8d-1 범위 초과)라 별도 작업/8e prep로 분리 권장.
- **RE-PLAN/RE-CODE: 불필요** (Codex: 새 production 회귀 없음).

## Push 정책
**보류** — R2 DOWNGRADE, Planner escalate(CLAUDE.md Stage 6). Planner 결정(PASS→push / micro-fix) 후 진행.
