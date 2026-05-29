# Phase 8a — Verify (self) — v2 (post RE-CODE)

마지막 code commit: `e7720f5 fix(phase-8a): extractor-scoped collision + text_level guard + runner/CLI tests`.
`git status` = 코드 무변경 (워크플로 summary.md stub만 untracked). 작성일 2026-05-30.
RE-CODE = verify-cross R1 REJECT 대응 (testing + 2 코드 fix).

## 5-A. Automated checks

| Check    | Command                                              | Result |
| -------- | ---------------------------------------------------- | ------ |
| Lint     | `uv run ruff check .`                                | All checks passed |
| Format   | `uv run ruff format --check .`                       | 172 files already formatted |
| Type     | `uv run mypy src`                                    | Success: no issues found in 75 source files |
| Test     | `uv run pytest -m "not llm and not slow" -q --no-cov`| 619 passed, 1 skipped, 7 deselected in 528.81s |
| Coverage | n/a — `make test-fast`/프로젝트 표준이 `--no-cov`. cov suite는 `-m slow`로 분리(WORKFLOW와의 차이는 6i부터 누적된 documented 정책). | n/a |
| CI       | push 후 GitHub Actions 확정.                          | pending push |

테스트 회계: baseline **576** → v1 **603** (+27) → v2 **619** (+16 RE-CODE) = +43 total.
+16 = 11 `test_mineru_runner` + 3 `test_cli_mineru` + 1 non-int text_level + 1 same-filename coexistence.

## 5-B. DoD 검증 (ROADMAP Phase 8a)
| DoD | Evidence |
| --- | --- |
| doc7 챕터 MinerU → chunk ingest | 실 E2E `doc_id=1 chunks=103 images=30` + `test_ingest_creates_chunks` (fixture, type 분포 lock) + `test_cli_mineru` (CLI 경로). |
| bbox/page/type/latex/caption 보존 | `test_ingest_preserves_structure` + `test_content_list_parser` 18건. |
| figure 분리 + 경로 | `test_ingest_copies_figures_to_managed_dir` (4 copy, img_path 실파일) + 실 E2E 30 figures. |
| 1.x DB 무손상 (병행) | `test_migration_0005_additive_only` (DDL diff) + `test_1x_data_untouched` (delta=0) + **`test_same_filename_1x_and_mineru_coexist`** (R1 핵심 fix) + full regression 576 무변경. |

## 5-C. verify-cross R1 지적 → 처리
| R1 지적 | 처리 | Evidence |
| --- | --- | --- |
| **same-filename collision로 1.x 삭제 위험 (REJECT 핵심)** | **fix**: 존재 lookup을 `extractor='mineru'` 스코프로. MinerU ingest(overwrite 포함)가 1.x pymupdf 행 절대 미접촉. | `test_same_filename_1x_and_mineru_coexist`: 동명 pymupdf+mineru 공존, overwrite는 mineru만 교체, 1.x 유지. |
| int(text_level) raw ValueError 누출 | **fix**: ContentListError로 wrap. | `test_non_int_text_level_rejects`. |
| runner discovery/실패 분기 미테스트 (§5.4) | **fix**: 11 단위 테스트. | `test_mineru_runner` (resolve env/PATH/missing, _discover glob/sanitized/nested/missing, run_mineru nonzero/no-output/cpu-env/missing-pdf). |
| CLI 미테스트 | **fix**: 3 테스트. | `test_cli_mineru` (happy/already-ingested→exit2/overwrite/dir-arg). |
| coverage --no-cov 정책 | **acknowledge**: 프로젝트 `make test-fast` 표준. 코드 fix 아님. | — |
| 절대 img_path 이식성 (확장성) | **defer**: 1.x bg_image_path도 절대경로(일관). 상대화는 8c 서빙 설계 시. summary에 명시. | — |
| doc7 E2E 비재현(외부 sandbox) | **acknowledge**: fixture 기반 `test_ingest_*`가 재현 증거. E2E는 보조. | — |

## 5-D. Regression check (RE-CODE — CLAUDE.md 필수)
RE-CODE 새 코드 경로 ↔ 잠금 테스트:
| RE-CODE 변경 | 잠금 테스트 (grep 확인) |
| --- | --- |
| `pipeline.py` lookup `Document.extractor=='mineru'` 스코프 | `test_same_filename_1x_and_mineru_coexist` (grep `extractor` in test) |
| `content_list.py` `level_int` try/except → ContentListError | `test_non_int_text_level_rejects` (grep `text_level`) |
| (신규 테스트 파일) `test_mineru_runner.py` | 11건 — `resolve_mineru_bin`/`_discover_outputs`/`run_mineru` grep로 등장 |
| (신규 테스트 파일) `test_cli_mineru.py` | 3건 — `ingest-mineru` CLI |

R1 fix 영역 회귀: R1에서 손댄 lookup/parser가 기존 ingest 동작 깨지 않음 — `test_ingest_creates_chunks`/`test_ingest_preserves_structure`/`test_1x_data_untouched` 전부 green (10 chunk, type 분포, 1.x delta=0 유지). full regression 619 green, 기존 603 영역 회귀 0.
새 함수/필드 grep: `extractor` (pipeline+test), `level_int` (parser), `resolve_mineru_bin`/`_discover_outputs`/`run_mineru` (runner+test) — 모두 테스트 파일에 등장.

## 5-E. 잔존 한계 (정직)
1. **timeout 분기 단위 미테스트**: `run_mineru` timeout은 nonzero/no-output/missing은 커버하나 실제 TimeoutExpired 경로는 미커버(flaky 회피). 코드 경로는 존재.
2. **chrome 오분류 1건**: 실 doc7서 footer 1건 본문 잔존(MinerU 라벨 한계). 103 중 1.
3. **bbox 좌표계/img_path 이식성**: 8c로 연기 (summary 명시).

## 5-F. Scoring (100, self-assessment)
| Item | Score / Max | Evidence |
| --- | --- | --- |
| 독창성 | 12 / 15 | subprocess 디커플링 + typed 파서 + additive-only diff + extractor-스코프 공존. 견고, 비-신규. |
| 완결성 | 33 / 35 | DoD 4/4 + 43 테스트(파서/ingest/schema/runner/CLI/공존) + 실 E2E + full regression. 차감: timeout 분기 미커버. |
| 안정성 | 28 / 30 | mypy strict+ruff clean, additive 이중증명, **1.x 무손상이 동명충돌까지 테스트로 잠김(R1 핵심 fix)**, rollback/parser malformed 전부 도메인에러. 차감: timeout. |
| 확장성 | 17 / 20 | chunk schema 8b 수용, parser 단일 버전경계, runner 설정형, extractor 공존이 8e cutover 안전. 차감: 절대 img_path(8c 상대화), translation/embedding 테이블 8b 연기. |
| **Total** | **90 / 100** | |

## 5-G. Self verdict
- [ ] PASS_CANDIDATE (≥95)
- [x] **submit to cross-verify Round 2 (최종, CLAUDE.md cap)** (self 90 < 95, 정직). R1 REJECT의 모든 concrete 지적(동명충돌/text_level/runner/CLI) fix+테스트 완료. 잔존은 timeout 단위테스트·img_path 이식성(8c)으로 구조적. R2가 새 concrete 결함 없이 REJECT면 Planner escalate.
- [ ] FAIL → RE-PLAN
