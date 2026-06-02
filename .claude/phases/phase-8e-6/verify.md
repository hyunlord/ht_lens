# Phase 8e-6 — Verify (self)

Scope: F2 = **읽기 전용 `detect-repairs` audit CLI** + 검출기(열화 이미지 / caption
오배치). 신규 doc(book2 F3)의 repair 발견을 자동화하되 **적용은 사람 게이트**(draft seed →
`repair-images`가 유일 overrides writer). GATE 2 승인 설계(seed-중심, C′, 분리 CLI, 2차
manifest 없음) 그대로. **0 DB/schema/migration, ingest 무수정, 1.x 불변.** 마지막 code
commit(`50ba280`) 이후 작성, 추적 트리 clean.

## 5-A. Automated checks
| Check    | Command | Result |
| -------- | ------- | ------ |
| Lint     | `uv run ruff check src tests` | All checks passed! |
| Format   | `uv run ruff format --check .` | 205 files already formatted |
| Type     | `uv run mypy src/` | Success: no issues in **86** source files |
| Test     | `uv run pytest -q` | **844 passed, 8 skipped, 0 failed** (577s); 3 snapshots |
| Focused  | image_repair(34) + repair_cli(6) | 40 passed |
| CI       | GitHub Actions | pending push |

844 = F1의 836 + 8 신규(5 detector unit + 3 detect-repairs CLI).

## 5-B. Functional checks
### 설계 적합 (GATE 2 승인 4개)
| 결정 | 구현 |
| ---- | ---- |
| #1 caption report-only(자동 할당 X) | `detect_caption_mispairs` = 페이지+이미지 목록+caption 리포트만; seed의 captions는 사람이 편집 |
| #2 좌표 C′(migration 0) | `clip_render_figure` origin.pdf `page.rect`; draft seed에 `origin_pdf{path,sha256}` 기록 |
| #3 분리 read-only CLI | `detect-repairs`(ingest 무수정); ingest 원자성 무관 |
| #4 2차 manifest 폐기 | detect-repairs는 draft `repair_seeds/<doc>.detected.json` + 미리보기만; `repair-images --apply`가 유일 overrides writer |

### 라이브 (doc1, in-process/CLI)
| Check | Evidence |
| ----- | -------- |
| 열화 재검출 | `detect-repairs --doc-id 1` → degraded=**3**(기존 ch1/84/85), 미리보기 `repair_preview/`(collision-free `p<page>_o<order>_`) |
| caption 오배치 재검출 | caption-mispair pages=**[4]** (ch53 무캡션 + 54/55 캡션) |
| 적용 0(read-only) | overrides.json 미작성; 서빙 무영향 |
| origin.pdf 없음 | markdown_path None/no --pdf → **exit≠0 "source PDF not found"**(loud) |
| skip 보고 | invalid bbox/rotated → draft `_skipped`에 reason 명시(은폐 없음) |
| caption FP 0 | 전부-캡션 multi-panel / single-image / nested-dedup → 후보 0 |

### 회귀 (8e-5/F1 불변)
| Check | Evidence |
| ----- | -------- |
| doc1 manifest | `/v2/chunks/1/image` → **image/png**(8e-5 fixed clip 그대로) |
| doc5 manifest | reflow ch1947 caption = "(a) Parallel design"(F1 그대로) |
| seed lock | `test_repair_seeds.py` doc1(3+3)/doc5(8 caption) 유효 |
| 정상 이미지 | 서빙 경로 무변경(detect-repairs는 별도 read-only) |
| 1.x DB | mtime 2026-05-28 불변; schema 0 |

## 5-C. Regression check (신규 코드 경로 → 테스트)
| 신규 경로 (grep) | 잠금 테스트 |
| ---------------- | ----------- |
| `detect_degraded_images` | `test_detect_degraded_images`(black>0.6, malformed bbox_valid=False, missing skip) |
| `detect_caption_mispairs` | flag captionless-coexist / no-FP all-captioned / single-image / nested-exclude |
| `detect-repairs` CLI | missing-pdf exit, report(degraded+mispair), draft-not-served |
| 미리보기 collision-free | `p<page>_o<order>_` (order_idx 유일) — CLI 테스트서 검증 |

기존 contract 무변경: `/v2`·1.x·기존 CLI(`repair-images` 등) 불변. F2는 **순수 추가**(read-only CLI + 검출기).

## 5-D. Scoring (100, self-assessment)
| Item       | Score / Max | Evidence |
| ---------- | ----------- | -------- |
| 독창성     |   13 / 15   | report-only audit(자동 할당 위험 회피) + C′ provenance(origin_pdf sha) + seed-중심 단일 writer |
| 완결성     |   33 / 35   | 4 설계 결정 전부 구현 + doc1 재검출 라이브 + 회귀; book2 실측은 F3에서(설계상 자동 적용) |
| 안정성     |   28 / 30   | 844/0, mypy 86; 0 DB/ingest/1.x; loud-fail·skip 보고·FP 0; −2 CI pending |
| 확장성     |   19 / 20   | book2 등 신규 doc에 detect-repairs 재사용; 검출기 순수; 단일 manifest lifecycle |
| **Total**  | **93 / 100**|          |

## 5-E. Self verdict
- [x] **PASS_CANDIDATE 후보(93) → cross-verify로** — 설계(GATE 2 승인) 충실 구현, 회귀 0, 0 DB/ingest. ≥95 갭 = pre-push CI + book2 실측(F3). cross-verify Round 1 진행.
- [ ] FAIL → RE-CODE
- [ ] FAIL → RE-PLAN
