# Phase 8e-5 — Verify (self) — v3 (post cross-verify R2)

Scope: 비파괴 image-repair manifest — (1) 검은 배경 PGM 다이어그램 열화 페이지-클립
복구(defect 1, 3건), (2) caption↔image 매핑 교정(defect 2, doc1 page4 3건). DB/스키마
변경 0; 1.x 불변.

Round history: v1 94(`e96e88a`) → **R1 DOWNGRADE ~86-88** → RE-CODE(durable CLI+seed,
manifest 하드닝) → v2 95(`333200c`) → **R2 DOWNGRADE 90-92** ("would not reject it;
R1 defects genuinely fixed") → 소규모 RE-CODE(`6755b15`/`9fd68bb`). R2 = 최종 cross-verify
(cap=2). HEAD `9fd68bb`; 추적 트리 clean. `ruff format --check .` = 203 ok.

## R2 findings → resolution
| R2 issue | Resolution | Lock |
| -------- | ---------- | ---- |
| §4#2 malformed bbox 타입이 서빙 crash (계약 위반) | `_valid_bbox` load drop + `_bbox_close` 방어 → `"bbox":"oops"` 무해 | `test_load_overrides_drops_non_numeric_bbox` |
| §4#3 빈/부재 allowlist → None → "전부 복구" 퇴행 | CLI 항상 concrete set(빈=복구 0); reviewed-only 강제 | `test_repair_cli_captions_only_seed_repairs_no_images` |
| §4#1 repair-images CLI 자동 테스트 없음 | CliRunner 테스트(wiring/dry-run/apply/allowlist) | `test_repair_cli_*` (3) |
| §4#4 seed parse 무제어 예외 | try/except → clean exit 2 | `test_repair_cli_invalid_seed_exits_2` |

## 5-A. Automated checks
| Check    | Command | Result |
| -------- | ------- | ------ |
| Lint     | `uv run ruff check src tests` | All checks passed! |
| Format   | `uv run ruff format --check .` | 203 files already formatted |
| Type     | `uv run mypy src/` | Success: no issues in **86** source files |
| Test     | `uv run pytest -q` | **832 passed, 8 skipped, 0 failed** (578.38s); 3 snapshots |
| Focused  | image_repair(30) + reflow_api(19) + repair_cli(3) | 52 passed |
| CI       | GitHub Actions | pending push |

832 = v2의 828 + 4 신규 R2 테스트.

## 5-B. Functional checks (live, in-process)
| Check | Evidence |
| ----- | -------- |
| defect 1 ch1/84/85 | `/v2/chunks/1/image` → 200 image/png, 27218B 완전 클립(`p0000_…`); 3건 육안 완전 다이어그램 |
| 비대상 무변경 | `/v2/chunks/30/image` → image/jpeg 원본 |
| defect 2 caption | ch53=Fig28.19, ch54=Fig28.20(a), ch55=Fig28.20(b) |
| dedup 무영향 | page2 `[30]`, page4 `[53,54,55]`, 총 12 |
| CLI 재생성 | `repair-images --doc-id 1 --seed repair_seeds/doc1.json --apply` → written=3, captions=3 (결정적) |
| reviewed-only | captions-only seed → written=0 (미리뷰 dark image 미복구) |
| malformed manifest | non-dict/unsafe-basename/non-numeric-bbox 전부 drop, serving 무crash |
| 1.x/DB 무손상 | diff = image_repair/reflow/cli + 테스트 + 커밋 seed; DB/migration 0 |

## 5-C. Regression check (RE-CODE 가드)
R1+R2 신규/변경 경로 전부 명시 테스트 잠금:

| 경로 (grep) | 잠금 테스트 |
| ----------- | ----------- |
| `_valid_bbox`/`_bbox_close` 방어 | `test_load_overrides_drops_non_numeric_bbox` |
| `is_safe_basename`/load drop | `test_is_safe_basename`, `test_load_overrides_drops_malformed_and_unsafe`, abs-path integration |
| `run_image_backfill` `p<page>_` | `test_backfill_same_basename_distinct_pages_no_collision` |
| `build_and_save_overrides` | `test_build_and_save_overrides_apply_and_dry_run` |
| `repair-images` CLI(allowlist/dry-run/error) | `test_repair_cli_*` (3) |
| `chunk_image`/`get_reflow` override | reflow_api override 6 (matched/stale/scoped/abs/caption×dedup) |

R1/R2-fix 영역 회귀 재확인: 52 focused / 832 full green. public contract(`/v2`·1.x·기존 CLI) 무변경. 8e-4 dedup green.

## 5-D. Scoring (100, self-assessment — 정직, R2-aligned)
| Item       | Score / Max | Evidence |
| ---------- | ----------- | -------- |
| 독창성     |   14 / 15   | 1000-정규화 발견(스키마 0); 안정증거 manifest; 소스 PDF clip |
| 완결성     |   33 / 35   | 두 defect 복구+교정+CLI 재생성+테스트; doc5 caption defer(Planner) → follow-up |
| 안정성     |   28 / 30   | 832/0; malformed bbox crash 수정(계약 준수)·reviewed-only 강제·CLI 테스트; −2 CI pending + coverage% 미보고 |
| 확장성     |   18 / 20   | CLI+seed 재사용; 순수 crop math; −2 seed schema 검증 느슨(향후 강화) |
| **Total**  | **93 / 100**|          |

## 5-E. Self verdict
- [ ] PASS_CANDIDATE (≥95)
- [x] **BELOW THRESHOLD (93) → escalate to Planner.** R1+R2 *기능/robustness* gap 전부 해소+테스트 잠금(특히 R2 malformed-bbox 계약 위반 버그 수정). ≥95 잔여 갭 = pre-push CI + coverage% 미보고 + seed schema 느슨(향후). cross-verify cap(R2 final)·R2-DOWNGRADE push 정책상 자체 ≥95 미인증·자율 push 안 함 — Planner가 merge 결정.
- [ ] FAIL → RE-CODE (Codex R2: "would not reject it")
- [ ] FAIL → RE-PLAN
