# Phase 8e-6 — Summary (F2: repair-manifest ingest 통합 → detect-repairs audit)

## Status
**Self 94 → escalated to Planner (GATE 3)** — R2 = final cross-verify; R2 verdict
DOWNGRADE → 정책상 자율 merge 금지. 기능/robustness 완료, 테스트 잠금.

## Score
- Self: **94 / 100** (v3, post-R2)
- Cross-verdict: R1 **DOWNGRADE 88-90** → RE-CODE → R2 **DOWNGRADE 91-92**
  ("the R1 fixes are mostly real, and this should not be rejected") → 잔여 RE-CODE.

## What was built (읽기 전용 audit, 0 DB/schema/ingest 변경)
GATE 2 승인 설계대로 — book2(F3) 등 신규 doc의 repair 발견을 자동화하되 적용은 사람 게이트:
1. **검출기**(`image_repair.py`): `detect_degraded_images`(검은 배경 >0.6, order_idx 식별) +
   `detect_caption_mispairs`(다중-이미지 페이지 captionless+captioned 공존 = doc1/doc5 시그니처;
   **report-only, 자동 할당 없음**; nested dedup-drop 제외).
2. **`detect-repairs` CLI**: doc audit → 열화 후보 미리보기(`repair_preview/`, `p<page>_o<order>_`
   collision-free) + caption-mispair 리포트 → DRAFT seed(gitignored `<extracts>/<doc>/`;
   origin_pdf path+sha provenance). **overrides 미작성** — `repair-images`가 유일 writer.
3. **좌표 C′**: origin.pdf `page.rect`(migration 0). **식별 통일**: detect 미리보기 + apply
   fixed PNG 모두 `p<page>_o<order>_<stem>` → same-page dup basename 양 경로 무충돌.

## Files changed (vs main, +661 / -22)
```
 src/ht_lens/image_repair.py          | 149 +  (detectors + order_idx 식별 + apply 통일)
 src/ht_lens/cli.py                   | 156 +  (detect-repairs CLI, repair-images order_idx)
 tests/unit/test_image_repair.py      | 132 +  (detectors, dup-identity, caption FP, apply)
 tests/integration/test_repair_cli.py | 246 +  (detect-repairs: missing-pdf/report/not-served/dup-preview/default-out/skipped)
```
**0** DB / migration / model / ingest / 기존 CLI 동작 / 1.x 변경.

## Verification evidence
- ruff/format/mypy(86) clean · `pytest -q`: **850 passed, 8 skipped, 0 failed**.
- 라이브: detect-repairs doc1 → degraded=3 + caption-mispair=[4]; doc5 → [109,223,257,339]
  재탐지; docs 2/3/4/5 degraded **FP 0**; doc3 2 미리뷰 후보(게이트 가치). doc1 manifest
  재생성(p<page>_o<order>_) → ch1 라이브 200 image/png. 1.x mtime 2026-05-28 불변.

## Cross-verify 잔여 (R1+R2 모두 해소)
- R1: order 충돌(detect)→order_idx 식별; repo 오염→gitignored 기본 draft; skip 증거 부족→page/order/bbox; doc5 증거 없음→라이브 재탐지. 전부 테스트/라이브.
- R2: apply-path basename 충돌→`p<page>_o<order>_` 통일(doc1 재생성); _skipped 테스트(rotated); docstring; caption prose-FP/scope 테스트. 전부 착지.

## Deviations from plan
- 원 plan의 "ingest 통합" → GATE 2 승인으로 **분리 read-only `detect-repairs` CLI**(ingest atomic 보존).
- 2차 manifest(`overrides.candidates.json`) 폐기 → draft seed + `repair-images` 단일 writer.
- caption: "탐지+제안" → **report-only**(자동 할당 배제).
- 좌표: migration 0008 불요(C′).

## Known issues / debt
- **CI green**: push 후 확정(self −1).
- **book2 실측**: F3에서(설계상 detect-repairs 자동 적용 흐름).
- **allowlist = basename-set**: same-page 동일 basename(=동일 content hash)은 한 fixed로 수렴(정상);
  진짜 구별 필요 시 향후 order-keyed allowlist. (실데이터 basename은 content-unique.)
- **caption 검출 = 구조적**(captionless 공존), prose 파싱 아님 → FP 0(테스트), 단 후보는 사람 검토.

## Planner decision needed (GATE 3 escalation)
R2 DOWNGRADE → 자율 merge 금지(정책). R1+R2 **기능/robustness** gap 전부 해소·테스트 잠금
(특히 apply-path 식별 통일). 94↔95 갭 = pre-push CI + book2 실측(F3) + allowlist 문서화 한계(기능
결함 아님). Codex도 "should not be rejected." **권고: main merge 승인** → CI green → prod 8086
재시작. 승인 시 F3(GATE 4)로.

## Recommended next
- 승인 시: merge + CI green + prod 재시작(코드만; 기존 doc1/doc5 manifest 디스크 상주).
- F3(book2 full 1370p): GATE 4(PDF 경로/디스크/sglang 확인) 후 추출 → detect-repairs 자동 흐름.
