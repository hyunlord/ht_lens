# Phase 8e-5 — Summary (Image 서빙 품질 정리: 페이지-크롭 + caption 매핑)

## Status
**Self 93 → escalated to Planner** (R2 = final cross-verify; R2 verdict DOWNGRADE
→ per push policy, no autonomous push). 기능/robustness 완료, 테스트 잠금.

## Score
- Self: **93 / 100** (v3, post-R2)
- Cross-verdict: R1 **DOWNGRADE ~86-88** → RE-CODE → R2 **DOWNGRADE 90-92**
  ("I would not reject it; R1's main defects were genuinely fixed") → 소규모 RE-CODE로 잔여 해소.

## What was built (둘 다 비파괴, DB/스키마 변경 0)
1. **검은 배경 PGM 다이어그램 열화 복구 (defect 1, 3건 — doc1)**: MinerU가 벡터 다이어그램을
   노드 blob만 캡처(화살표·라벨·타원 손실). 소스 PDF에서 figure 영역을 직접 clip-render
   (`bbox/1000 × page.rect`, 300dpi, rotation 가드)하여 완전한 다이어그램으로 교체 서빙.
   ch1(Fig 28.17 DPGM), ch84(28.23a), ch85(28.23b).
2. **caption↔image 매핑 교정 (defect 2, doc1 page4 3건)**: 다중-이미지 페이지에서 MinerU가
   "Figure 28.19" 캡션을 엉뚱한 이미지에 페어링. ch53→Fig28.19(2d embedding), ch54→Fig28.20(a)
   GAP, ch55→Fig28.20(b) Simplex FA로 재할당(이미지 파일 불변, caption만).
3. **메커니즘**: `Chunk.bbox_json`가 1000×1000 정규화임을 발견(검증: page.rect=page_size)
   → **스키마 마이그레이션 불필요**. 교정은 per-doc `overrides.json` manifest(안정 증거
   page_idx+basename+bbox로 키, 재ingest-safe). `ht-lens repair-images` CLI + 커밋된
   `repair_seeds/doc1.json`로 **git에서 결정적 재생성** 가능.

## Files changed (vs main, +1314 / -2)
```
 src/ht_lens/image_repair.py          | 403 +  (manifest/crop/detect/clip/backfill/CLI orch)
 src/ht_lens/api/routers/reflow.py    |  39 +  (chunk_image 이미지 override, get_reflow caption override)
 src/ht_lens/cli.py                   |  93 +  (repair-images CLI)
 repair_seeds/doc1.json               |  44 +  (커밋된 reviewed 재생성 seed)
 tests/unit/test_image_repair.py      | 365 +  (30)
 tests/integration/test_reflow_api.py | 219 +  (override 서빙 6)
 tests/integration/test_repair_cli.py | 153 +  (CLI 3)
```
**0** DB / migration / model / 1.x / 기존 CLI 커맨드 변경.

## Verification evidence
- `ruff check src tests` clean · `ruff format --check .` 203 ok · `mypy src/` 86 clean.
- `pytest -q`: **832 passed, 8 skipped, 0 failed**.
- Live(in-process): ch1 /image=완전 PNG 클립(27KB↔열화 5KB), ch53/54/55 caption 교정, dedup
  page2=[30]/page4=[53,54,55]/총12; CLI dry-run/apply 재생성 결정적; captions-only seed=written 0.

## Deviations from plan
- **스키마: 후보 A(migration 0008) 대신 B′(bbox÷1000, 스키마 0)** — Stage 0의 1000-정규화 발견으로
  challenge에서 채택(더 단순·비파괴). plan에 명시된 deviation.
- **복구 = cached PNG 크롭이 아니라 소스 PDF clip-render** — challenge R3(고품질·결정적).
- **defect 2 범위 = doc1 page4만** (Planner 결정) — doc5 다중-이미지 패턴은 defer.

## Cross-verify 잔여 (R1+R2 모두 해소)
- R1: durable 재생성 경로 없음→CLI+seed; fixed_basename traversal→is_safe_basename;
  malformed manifest→guard; 파일명 충돌→p<page>_ 접두. 전부 테스트.
- R2: malformed bbox 타입 crash(계약 위반)→`_valid_bbox`+방어; allowlist None 퇴행→reviewed-only
  강제; CLI 미테스트→CliRunner 3; seed parse 예외→clean exit. 전부 테스트.

## Known issues / debt
- **CI green**: push 후 확정(self-score −2).
- **Coverage %** 별도 미보고(기존 게이트만).
- **seed schema 검증 느슨**: 필수 키 정도만 — 향후 강화 여지.
- **doc5 caption 패턴 (follow-up)**: doc5 다중-이미지/서브패널 페이지에 동종 misattribution
  가능성(미확정, 육안 audit 필요). ROADMAP follow-up. 동일 manifest 경로로 교정 가능.
- **doc1 origin.pdf 위치**: `~/mineru_test/...`(repo 밖) — 재생성은 그 PDF + DB 필요. 산출 클립은
  `data/extracts_v2/1/images_fixed/`(다른 2.0 자산과 동일하게 gitignored, prod 호스트엔 상주).

## Planner decision needed (escalation)
R2 DOWNGRADE → push 보류(정책). R1+R2 **기능/robustness** gap 전부 해소·테스트 잠금; 93↔95 갭은
**pre-push CI + coverage% 미보고 + seed schema 느슨**(기능 결함 아님). Codex도 "would not reject."
**권고: main merge 승인**(잔여는 CI green으로 해소). 승인 시:
`PR/merge → GitHub CI → prod 8086(pid 1599295) 재시작(이미 상주한 overrides.json/images_fixed 서빙)`.

## Recommended next
- 승인 시: merge + CI green + prod 재시작(코드만 갱신; manifest는 이미 디스크 상주).
- Follow-up: doc5 caption audit; book2 full 1370p; pixel-perfect bbox overlay; repair manifest의
  ingest 통합(신규 doc 자동 커버).
