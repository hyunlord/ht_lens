# Phase 8c — Summary (Reflow Viewer)

## Status
**ESCALATE_TO_PLANNER** — cross-verify Round 2 = DOWNGRADE, 2-round cap 도달. CLAUDE.md "Round 2 이후엔 호출하지 마라. summary.md에 양측 의견 명시하고 Planner에게 escalate" 적용. Push 보류.

## Score
- Self (verify.md v2): **88 / 100**
- Cross R1 (f8472d2): **DOWNGRADE** (4 concrete coverage gap) → RE-CODE(테스트-only) → verify v2
- Cross R2 (e19085b, 최종/cap): **DOWNGRADE ~84 / 100**

## What was built
chunk(8a) + translation(8b)를 단일 reflow 읽기 뷰로 렌더 + 좌우 비교 토글. 1.x와 완전 공존(`/v2` + `reflow.html` 신규, `/documents` + `viewer.html` 무수정).

- `GET /v2/documents/{id}/reflow` — order_idx 정렬 chunk + translation 조인. `status=='translated'`만 surface(실패 row는 content 위장 금지, challenge §5). bbox 4-num 또는 null(two-tier sync).
- `GET /v2/chunks/{id}/image` — MinerU figure(.png/.jpg/.jpeg). traversal 거부, 누락 404.
- `GET /v2/documents/{id}/page/{idx}/image` — 좌측 비교 페인용 원문-페이지 render-cache(Page row 미생성, `data/extracts_v2/<doc>/pages/page_<idx>.png`). 누락 404.
- `render_doc_pages()` — PDF→페이지 캐시 렌더(8e 마이그레이션이 재사용). PDF 부재 시 FileNotFoundError.
- `reflow.html` + `css/reflow.css` + `js/reflow.js`(단일 모듈) — heading 강조 / KaTeX(6i `applyMath` 재사용) / figure inline + 캡션(KO+EN) / table fallback. 클릭 시 page-level sync(active chunk + 좌측 페이지 hl + scrollIntoView).
- throwaway prototype 제거(decision D): `routers/prototype.py` + `prototype_reflow.html`.

## Files changed (6efd7c1 challenge → HEAD, src+tests)
```
 src/ht_lens/api/app.py                       |   4 +--
 src/ht_lens/api/routers/prototype.py         | 213 ---------  (제거)
 src/ht_lens/api/routers/reflow.py            | 208 +++++++++  (신규)
 src/ht_lens/api/static/css/reflow.css        |  96 ++++++++   (신규)
 src/ht_lens/api/static/js/reflow.js          | 178 +++++++++  (신규)
 src/ht_lens/api/static/prototype_reflow.html | 218 ---------  (제거)
 src/ht_lens/api/static/reflow.html           |  28 ++++++    (신규)
 tests/integration/test_reflow_api.py         | 236 +++++++++  (신규, 12 tests)
 tests/integration/test_reflow_viewer_js.py   | 199 +++++++++  (신규, 7 tests)
 9 files changed, 947 insertions(+), 433 deletions(-)
```

## Automated evidence (verify.md v2 기준, 실측)
- ruff check / ruff format --check: clean
- mypy src: Success, no issues (79 files)
- pytest -m "not llm and not slow" --no-cov: **674 passed, 1 skipped** (655 → 674, +19: 12 API + 7 jsdom)
- 1.x prod data/ht_lens.db(alembic 0004) 불변, 8c는 dev DB(data/ht_lens_v2.db, 0006)
- Playwright E2E(수동, dev DB doc7 103 chunk): 16 headings / 57 paragraphs / 15 figures / 87 KaTeX / 15 display, console error 0(favicon만), result_v2.html 품질 재현

## 양측 의견 (escalate 핵심)

### Worker (self) — 88, submit-to-R2
R1의 4개 concrete gap 전부 테스트로 폐쇄(2f456ad, **production 코드 무변경**). DoD 3/3 충족 + 실 E2E. 잔존은 8e(실 qwen/render-cache CLI 와이어)·후속(bbox pixel sync).

### Critic (Codex R2) — DOWNGRADE ~84
> "Round 1's concrete coverage gaps were fixed cleanly, and I do not see a RE-CODE regression. The remaining concerns are evidence/process gaps."

R2가 새로 든 5건 — **모두 evidence/process gap, 코드 결함 아님**:
1. **Coverage 미실행**: verify는 `--no-cov`, pyproject는 pytest-cov 기본 → coverage 수치 부재.
2. **doc7/토글 수동 evidence만**: Playwright 스크립트/스크린샷/fixture가 repo에 미커밋. jsdom은 `syncToChunk`만 in-suite 잠금 — radio 토글 핸들러(`reflow.js:170-173`)·click 경로(`:157`)는 직접 미검증.
3. **Regression-check 표 미준수**: verify.md:31-32가 서술문. CLAUDE.md는 RE-CODE 변경별 "새 함수/state/handler → 잠금 단위 테스트" **표** 요구. 내용은 대부분 있으나 audit 형식이 빠짐.
4. **UI fallback 핸들러 미테스트**: `reflow.js:44-50`(이미지 실패→`.fig-missing`), `:112-114`(원문 페이지 render 누락→라벨 변경). 대응 API 404는 테스트됨, 가시적 viewer fallback 경로는 미테스트.
5. **정확도 nit**: verify.md:14 "13 test_reflow_api" — 실제 **12** (총 19, 20 아님). 확인: `grep -c` = 12 + 7.

### Worker 평가 (R2에 대한 응답)
5건 모두 **사실 확인**(특히 #4 미테스트 코드 경로 2곳, #5 카운트 1 오차는 실측 일치). Codex와 **동의**: 새 production 결함 0, RE-CODE 회귀 0. 8b(R2가 exit-code 실 결함)와 **다르고**, 6i(cache 오판)·8a(R2 DOWNGRADE=process)와 **동형**.

## Deviations from plan
- page-level sync (bbox pixel sync 아님) — challenge.md:16, Planner 승인된 DoD 예외(ROADMAP.md:231 "chunk bbox sync"의 다운그레이드).
- 번역 mock `[KO]` — 실 qwen은 8e.
- throwaway prototype 제거(decision D, plan 명시).

## Recommended next (Planner 결정)
**Worker 권고: micro-fix** (단, Planner 결정 사항). 근거: 5건이 concrete하고 **전부 test-only/문서 수정** → production 코드 무변경 → R3 cross-verify 불필요(8b 해소 메커니즘과 동일: verify v3 → push). 묶음(추정 ~30분):
- (a) jsdom 2건: 이미지 onerror→`.fig-missing`; 페이지 render 오류→라벨 변경.
- (b) jsdom 1건: radio 토글→`layout.dataset.mode`.
- (c) verify 5-D를 CLAUDE.md 요구 표 형식으로 재작성(변경→새 경로→잠금 테스트).
- (d) 카운트 정정(13→12, 총 19).
- (e) 8c 파일 coverage 1회 실측(--no-cov 제거).
→ verify v3 → push.

**대안: PASS** (8a 선례) — 결함·회귀 0이므로 방어 가능. 단 미테스트 코드 경로 2곳 + 비표준 regression 섹션이 영구 기록에 남음.

**RE-PLAN: 불필요** (설계/스코프 이슈 없음).

## Evidence index
- plan: `.claude/phases/phase-8c/plan.md`
- debate: `.claude/phases/phase-8c/debate.md` (Codex)
- challenge: `.claude/phases/phase-8c/challenge.md` (PASS, 8 revisions)
- verify: `.claude/phases/phase-8c/verify.md` (v2, self 88)
- verify-cross R1: `f8472d2` (DOWNGRADE, 4 gap)
- verify-cross R2: `.claude/phases/phase-8c/verify-cross.md` @ `e19085b` (DOWNGRADE ~84, 최종/cap)

## Known issues / debt
1. UI fallback 핸들러 2곳 in-suite 미테스트(reflow.js:44-50, 112-114) — micro-fix 후보.
2. Playwright 수동 E2E (in-suite fixture 없음, 6i 선례).
3. bbox pixel sync 미구현(page-level only, Planner 승인) — per-page scale 후속.
4. render-cache 운영 채움 CLI 미와이어(`render_doc_pages` 함수+테스트는 존재) — 8e.
5. 번역 mock — 실 qwen 8e.

## Push 정책
**보류** — Round 2 DOWNGRADE, Planner escalate. CLAUDE.md Stage 6 / WORKFLOW.md 준수. Planner 결정(PASS / micro-fix) 후 진행.
