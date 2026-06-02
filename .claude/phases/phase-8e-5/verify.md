# Phase 8e-5 — Verify (self) — v2 (post cross-verify R1 RE-CODE)

Scope: 비파괴 image-repair manifest — (1) 검은 배경 PGM 다이어그램 열화 페이지-클립
복구(defect 1, 3건), (2) caption↔image 매핑 교정(defect 2, doc1 page4 3건). DB/스키마
변경 0; 1.x 불변.

Round history: v1 self 94(`e96e88a`) → **Codex R1 DOWNGRADE ~86-88** (4 gaps) →
RE-CODE(`dfd1251` 하드닝, `e91afc9` CLI+seed+tests) → v2. HEAD = verify v2 직전
`e91afc9`; 추적 트리 clean. (`ruff format --check .` = 203 files ok.)

## R1 findings → resolution
| R1 issue | Resolution | Lock |
| -------- | ---------- | ---- |
| §4#1 repair 자산 gitignored·재생성 경로 없음 | `ht-lens repair-images` CLI + 커밋된 `repair_seeds/doc1.json`(3 image allowlist + 3 caption) → git에서 결정적 재생성 | `test_build_and_save_overrides_apply_and_dry_run`, CLI dry-run/apply 라이브 |
| §4#2 `fixed_basename` 절대/traversal로 root 탈출 | `is_safe_basename` — load_overrides가 unsafe 드롭 + chunk_image 서빙 가드(이중) | `test_is_safe_basename`, `test_load_overrides_drops_malformed_and_unsafe`, `test_image_override_absolute_fixed_basename_rejected`(integration) |
| §4#3 malformed manifest가 서빙 깨뜨림 | load_overrides가 non-dict raw + non-dict item 가드 → 절대 raise 안 함 | `test_load_overrides_drops_malformed_and_unsafe`, `test_load_overrides_non_dict_root_is_empty` |
| §4#4 같은 basename fixed PNG 충돌 | `fixed_basename = p<page>_<stem>.png` (page별 유일) | `test_backfill_same_basename_distinct_pages_no_collision` |
| §1 format `--check` 미실행 | `uv run ruff format --check .` 실행 | 203 files ok |

## 5-A. Automated checks
| Check    | Command | Result |
| -------- | ------- | ------ |
| Lint     | `uv run ruff check src tests` | All checks passed! |
| Format   | `uv run ruff format --check .` | 203 files already formatted |
| Type     | `uv run mypy src/` | Success: no issues in **86** source files |
| Test     | `uv run pytest -q` | **828 passed, 8 skipped, 0 failed** (579.84s); 3 snapshots |
| Focused  | `test_image_repair.py`(29) + `test_reflow_api.py`(18) | 47 passed |
| CI       | GitHub Actions | pending push |

828 = v1의 822 + 6 신규 R1 테스트. `pytest -q`는 `-m "not llm and not slow"`의 상위집합(더 광범위).

## 5-B. Functional checks (live, in-process against `data/ht_lens_v2.db`)
`data/extracts_v2/1/overrides.json`(3 image + 3 caption, **CLI로 재생성** = `repair-images --doc-id 1 --seed repair_seeds/doc1.json --apply`):

| Check | Evidence |
| ----- | -------- |
| **defect 1** ch1/84/85 복구 | `/v2/chunks/1/image` → 200 image/png, **27218B** 완전 클립(`p0000_…png`) ≠ 열화 5328B. 3건 PDF clip 육안 확인(완전 DPGM/LDA 다이어그램) |
| 비대상 무변경 | `/v2/chunks/30/image` → 200 image/jpeg(원본) |
| **defect 2** caption | ch53="Figure 28.19: …2d embedding…", ch54="Figure 28.20: (a) GAP…", ch55="Figure 28.20: (b) Simplex FA…" |
| **dedup 무영향**(R6) | page2 `[30]`, page4 `[53,54,55]` 유지, 총 12 |
| CLI 재생성 | `repair-images --dry-run` detected=3/captions=3; `--apply` written=3 → `p<page>_<stem>.png` |
| 5-doc 무회귀 | 정상 158 서빙 불변; 6 integration override 테스트 green |
| 1.x/DB 무손상 | diff = `image_repair.py`/`reflow.py`/`cli.py` + 테스트 + 커밋 seed; DB/migration/model/1.x 0 |

## 5-C. Regression check (RE-CODE 가드)
RE-CODE(`dfd1251`/`e91afc9`) 신규/변경 코드 경로 → 명시 테스트 잠금:

| 신규/변경 경로 (grep) | 잠금 테스트 |
| --------------------- | ----------- |
| `is_safe_basename` | `test_is_safe_basename` + load/serve 통합 |
| `load_overrides` (non-dict raw/item + unsafe drop) | `test_load_overrides_drops_malformed_and_unsafe`, `test_load_overrides_non_dict_root_is_empty` |
| `run_image_backfill` fixed_basename `p<page>_` | `test_backfill_same_basename_distinct_pages_no_collision` (+ apply 테스트 갱신) |
| `build_and_save_overrides` | `test_build_and_save_overrides_apply_and_dry_run` |
| `chunk_image` is_safe 가드 | `test_image_override_absolute_fixed_basename_rejected` |
| `repair-images` CLI | 라이브 dry-run/apply (재생성 doc1 결정적) |

R1-fix 영역 회귀 재확인: 기존 override 서빙·dedup·caption 테스트 green(47 focused / 828 full). public contract(`/v2`·1.x·CLI 기존 커맨드) 무변경. 8e-4 dedup green.

## 5-D. Scoring (100, self-assessment)
| Item       | Score / Max | Evidence |
| ---------- | ----------- | -------- |
| 독창성     |   14 / 15   | bbox 1000-정규화 발견 → 스키마 변경 0; 안정증거 manifest; 소스 PDF clip |
| 완결성     |   33 / 35   | 두 defect 복구+교정+CLI 재생성+테스트; doc5 caption 패턴 의도적 defer(Planner) → roadmap follow-up |
| 안정성     |   29 / 30   | 828 passed/0 fail, mypy 86; malformed/unsafe/collision 가드+테스트, 비파괴; −1 CI pending |
| 확장성     |   19 / 20   | CLI+seed 재사용(신규 doc·ingest 통합); 순수 crop math; manifest 확장형 |
| **Total**  | **95 / 100**|          |

## 5-E. Self verdict
- [x] **PASS_CANDIDATE (≥95)** — R1 4건 전부 해소+테스트 잠금, 재생성 경로 durable. cross-verify Round 2(final)로 진행.
- [ ] FAIL → RE-CODE
- [ ] FAIL → RE-PLAN
