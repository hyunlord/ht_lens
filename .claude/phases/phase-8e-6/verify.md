# Phase 8e-6 — Verify (self) — v3 (post cross-verify R2)

Scope: F2 = 읽기 전용 `detect-repairs` audit CLI + 검출기(열화 / caption 오배치). 신규
doc repair 발견 자동화, 적용은 사람 게이트(draft seed → `repair-images`가 유일 overrides
writer). **0 DB/schema/migration, ingest 무수정, 1.x 불변.**

Round: v1 93(`f23b2d9`) → R1 DOWNGRADE 88-90 → RE-CODE(`84732b3`) → v2 95(`8ca80a7`) →
**R2 DOWNGRADE 91-92** ("should not be rejected") → RE-CODE(`d6fc78a` + doc1 manifest
재생성). R2 = 최종 cross-verify(cap=2). HEAD `d6fc78a`; 추적 트리 clean.

## R2 findings → resolution
| R2 issue | Resolution | Lock |
| -------- | ---------- | ---- |
| §4#1 apply 경로(run_image_backfill)가 basename만 → same-page dup 충돌 | `run_image_backfill`/`build_and_save_overrides`에 order_idx; fixed PNG = `p<page>_o<order>_<stem>`(preview와 동일 식별). doc1 manifest 재생성 | `test_backfill_same_basename_distinct_pages_no_collision` + apply 테스트(`p0000_o0000_`) |
| §4#3 `_skipped` 테스트 없음 | rotated 페이지 degraded → `_skipped`에 page/order/bbox/reason | `test_detect_repairs_skipped_records_identity_on_rotated_page` |
| §4#3 CLI docstring stale(repair_seeds 기본) | help/docstring을 gitignored extracts 기본으로 수정 | (코드) |
| §4#4 caption prose-FP/text-chunk 테스트 미착 | 구조적 검출(prose 무관) prose-FP 0 + image-chunk-only scope 테스트 | `test_detect_caption_mispairs_prose_parens_no_fp`, `..._is_image_chunk_only` |

## 5-A. Automated checks
| Check    | Command | Result |
| -------- | ------- | ------ |
| Lint     | `uv run ruff check src tests` | All checks passed! |
| Format   | `uv run ruff format --check .` | clean |
| Type     | `uv run mypy src/` | Success: no issues in **86** source files |
| Test     | `uv run pytest -q` | **850 passed, 8 skipped, 0 failed** (747s); 3 snapshots |
| Focused  | image_repair(38) + repair_cli(10) + reflow_api | 58+ passed |
| CI       | GitHub Actions | pending push |

850 = v2의 847 + 3 신규 R2 테스트.

## 5-B. Functional checks
### 식별 통일 (R2 §4#1) — detect와 apply 모두 page+order
미리보기 `p<page>_o<order>_<stem>` + fixed PNG `p<page>_o<order>_<stem>` 동일 식별 →
same-page 동일 basename 형제가 양 경로 어디서도 충돌/덮어쓰기 없음.

### 라이브 (detect-repairs, R1에서 수집)
| doc | degraded | caption-mispair pages |
| --- | -------- | --------------------- |
| 1 | 3 | [4] | 2/3/4 | 0 | (3=2 미리뷰 후보) | 5 | 0 | [109,223,257,339] = F1 정확 재탐지 |
degraded FP 0(doc1만). doc1 manifest **재생성**(p<page>_o<order>_) → 라이브 ch1 = 200 image/png.

### 설계 적합 (GATE 2 승인 4개) — #1 caption report-only / #2 C′(migration 0) / #3 분리 read-only CLI / #4 단일 writer. 전부 유지.

### 회귀 (8e-5/F1 불변)
doc1 ch1=image/png(재생성 clip), doc5 ch1947="(a) Parallel design"; `test_repair_seeds` doc1/doc5 유효; 1.x mtime 2026-05-28 불변; schema 0.

## 5-C. Regression check (RE-CODE 가드)
| 신규/변경 경로 (grep) | 잠금 테스트 |
| --------------------- | ----------- |
| `run_image_backfill`/`build_and_save_overrides` order_idx + `p<page>_o<order>_` | apply/dup-page/build 테스트(8e-5 갱신) |
| `_skipped` page/order/bbox | `test_detect_repairs_skipped_records_identity_on_rotated_page` |
| `detect_caption_mispairs` prose/scope | prose-FP + image-chunk-only |
| `DegradedCandidate.order_idx`/detect 식별 | 동일-basename 식별 단위 + 미리보기 CLI |

기존 contract 무변경(`/v2`·1.x·기존 CLI 동작). 8e-5/F1 manifest·서빙 불변(doc1 재생성은 동일 내용·새 파일명). 58+ focused / 850 full green.

## 5-D. Scoring (100, self-assessment — 정직)
| Item       | Score / Max | Evidence |
| ---------- | ----------- | -------- |
| 독창성     |   14 / 15   | report-only audit + page+order 통일 식별 + C′ provenance + 단일 writer |
| 완결성     |   33 / 35   | 4 설계 + doc5 재탐지 + FP 0 + R2 잔여(apply/skip/docstring/caption-FP) 전부 착지; book2 실측은 F3 |
| 안정성     |   29 / 30   | 850/0, mypy 86; detect+apply 식별 통일, _skipped 테스트, 0 DB/ingest/1.x; −1 CI pending |
| 확장성     |   18 / 20   | book2 대규모 dup-basename 안전(양 경로); allowlist는 여전히 basename-set(동일-content 가정, 문서화) |
| **Total**  | **94 / 100**|          |

## 5-E. Self verdict
- [ ] PASS_CANDIDATE (≥95)
- [x] **BELOW THRESHOLD (94) → escalate to Planner (GATE 3).** R1+R2 기능/robustness gap 전부 해소+테스트 잠금(apply-path 식별 통일 포함). ≥95 잔여 = pre-push CI + book2 실측(F3) + allowlist basename-set(동일-content 가정). cross-verify cap(R2 final)·R2-DOWNGRADE 정책상 자율 merge 안 함 — GATE 3에서 Planner 승인.
- [ ] FAIL → RE-CODE (Codex R2: "should not be rejected")
- [ ] FAIL → RE-PLAN
