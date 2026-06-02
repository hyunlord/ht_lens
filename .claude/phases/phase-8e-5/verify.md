# Phase 8e-5 — Verify (self)

Scope: 비파괴 image-repair manifest — (1) 검은 배경 PGM 다이어그램 열화 페이지-클립
복구(defect 1, 3건), (2) caption↔image 매핑 교정(defect 2, doc1 page4 3건). DB/스키마
변경 0; 1.x 불변. 마지막 code commit(`e16a61e`) 이후 작성, 추적 트리 clean.

## 5-A. Automated checks
| Check    | Command | Result |
| -------- | ------- | ------ |
| Lint     | `uv run ruff check src tests` | All checks passed! |
| Format   | pre-commit ruff-format (커밋마다) | Passed |
| Type     | `uv run mypy src/` | Success: no issues in **86** source files |
| Test     | `uv run pytest -q` | **822 passed, 8 skipped, 0 failed** (772.87s); 3 snapshots |
| Focused  | `test_image_repair.py`(27) + `test_reflow_api.py`(17, +4 override) | 35 passed |
| CI       | GitHub Actions | pending push |

822 = 8e-4의 800 + 22 신규(18 unit image_repair + 4 integration override). 8 skip = 기존 env-conditional.

## 5-B. Functional checks (live, in-process against `data/ht_lens_v2.db`)
ASGI lifespan + httpx (prod 8086 무영향), `data/extracts_v2/1/overrides.json`(3 image + 3 caption) 적용:

| Check | Evidence |
| ----- | -------- |
| **defect 1** ch1/84/85 복구 | `GET /v2/chunks/1/image` → 200 **image/png**, served == 페이지-클립(27218B 완전) ≠ 열화 원본(5328B). 3건 모두 PDF clip 육안 확인: ch1=완전 DPGM(μ,Σ→z_n→x→W), ch84=LDA(α→z_n→c→x→W→β), ch85=LDA plate(N,L_n,K) |
| 비대상 무변경 | `GET /v2/chunks/30/image` → 200 **image/jpeg**(원본 유지) |
| **defect 2** caption 교정 | reflow: ch53="Figure 28.19: …2d embedding…"(무캡션→부여), ch54="Figure 28.20: (a) GAP…", ch55="Figure 28.20: (b) Simplex FA…" |
| **dedup 무영향**(R6) | page2 image ids `[30]`, page4 `[53,54,55]` 전부 유지, 총 **12** (8e-4와 동일) |
| 좌표 정규화 검증 | doc1 page0 `page.rect=(0,0,576,648)` = page_size 정확 일치; `bbox/1000×page.rect`로 클립 |
| 5-doc 무회귀 | 정상 158개 서빙 경로 불변(override 매칭 chunk만 분기); 4 integration override 테스트 green |
| 1.x/DB 무손상 | diff = `image_repair.py`(신규) + `reflow.py` + 테스트 2; DB/migration/model/1.x 0. manifest는 gitignored 파일(롤백=삭제) |

## 5-C. Regression check (RE-CODE 가드 — 이번엔 RE-CODE 없음)
첫 패스 PASS_CANDIDATE. 신규 코드 경로별 명시 테스트 잠금:

| 신규 코드 경로 (grep) | 잠금 테스트 |
| --------------------- | ----------- |
| `normalized_bbox_to_page_rect` | norm bbox match/pad/inverted/degenerate/out-of-range/malformed (6) |
| `black_bg_fraction`/`is_degraded_candidate` | black/white 분리, 결측 파일 |
| `clip_render_figure` | writes PNG / **rotated skip** / inverted·OOB skip |
| `run_image_backfill` | dry-run 무기록 / apply 검출만 / allowlist 필터 |
| `load/save/match_image_override`/`match_caption_override` | round-trip / scoped / **stale** / no-img |
| `chunk_image` override 분기 | integration: matched→PNG, stale→원본, **traversal 거부**, scoped |
| `get_reflow` caption override | integration: 교정 적용 + **dedup intact**(R6) |

기존 contract 무변경: `/v2` 라우트·1.x 라우트·CLI 불변. 8e-4 dedup·기존 reflow 테스트 green(35 focused / 822 full).

## 5-D. Scoring (100, self-assessment)
| Item       | Score / Max | Evidence |
| ---------- | ----------- | -------- |
| 독창성     |   14 / 15   | bbox 1000-정규화 발견 → 스키마 변경 없이 PDF-clip 복구; 안정증거 manifest(재ingest-safe) |
| 완결성     |   33 / 35   | 두 defect 다 복구+교정+테스트+라이브; doc5 caption 패턴은 의도적 defer(Planner 승인) → summary 기록 |
| 안정성     |   28 / 30   | 822 passed/0 fail, mypy 86 clean; 비파괴(DB 0)·rotation/stale/traversal 가드; −2 CI pending |
| 확장성     |   19 / 20   | 순수 crop math + dry-run/apply backfill + manifest는 신규 doc·ingest 통합에 재사용 가능 |
| **Total**  | **94 / 100**|          |

## 5-E. Self verdict
- [ ] PASS_CANDIDATE (≥95)
- [x] **BELOW THRESHOLD (94) → cross-verify로** — 기능·테스트 완비, ≥95 갭은 CI(pending) + doc5 caption defer(범위 결정). cross-verify Round 1로 진행.
- [ ] FAIL → RE-CODE
- [ ] FAIL → RE-PLAN
