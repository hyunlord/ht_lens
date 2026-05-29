# Phase 8a — Verify (self)

마지막 code commit: `bf241e6 test(phase-8a)` (이후 `7e8b4b7`은 .gitignore chore, 코드 무관).
`git status` = 코드 무변경 (워크플로 stub 3개만 untracked). 작성일 2026-05-30.

## 5-A. Automated checks

| Check    | Command                                              | Result |
| -------- | ---------------------------------------------------- | ------ |
| Lint     | `uv run ruff check .`                                | All checks passed |
| Format   | `uv run ruff format --check .`                       | 170 files already formatted |
| Type     | `uv run mypy src`                                    | Success: no issues found in 75 source files |
| Test     | `uv run pytest -m "not llm and not slow" -q --no-cov`| 603 passed, 1 skipped, 7 deselected in 507.71s |
| Coverage | n/a (cov suite는 `-m slow`, 프로젝트 정책상 deferred)  | n/a |
| CI       | push 후 GitHub Actions 확정. 로컬 동등 명령 위 4행.    | pending push |

테스트 회계: baseline **576** → **603** = **+27** = (17 `test_content_list_parser`) + (7 `test_mineru_ingest`) + (3 `test_chunk_schema`).

## 5-B. DoD 검증 (ROADMAP Phase 8a)

| DoD | Evidence |
| --- | --- |
| doc 7 한 챕터 MinerU 추출 → chunk DB ingest 성공 | **실측 E2E**: `ht-lens ingest-mineru <real doc7 990-1000 content_list> --filename book2_ch28.pdf` → `doc_id=1 chunks=103 images=30`. type 분포: text 57 / heading 16 / image 15 / equation 15. |
| chunk가 bbox/page/type/latex/caption 보존 | `test_ingest_preserves_structure`: equation `text_format=latex` + content `$$..$$`, bbox_json verbatim `[149.0,150.0,520.0,200.0]`, heading `text_level=2`, image caption "…Simplex FA…", page_idx {0,1,2}. parser unit 17건. |
| figure 이미지 분리 + 경로 저장 | `test_ingest_copies_figures_to_managed_dir`: 4 이미지 → `<dest>/<doc>/images/`, 모든 `img_path`가 실파일. 실 E2E: 30 figures 복사. |
| 1.x DB 무손상 (병행) | (1) `test_migration_0005_additive_only`: 0004 vs 0005 schema diff — 1.x 7테이블 DDL byte-identical, 추가=chunks+documents 2컬럼뿐, drop 0. (2) `test_1x_data_untouched_by_mineru_ingest`: 1.x doc+block+translation seed 후 MinerU ingest → blocks/translations/pages delta=0, 레거시 translation "안녕" 유지, extractor='pymupdf'. (3) full regression 576건 전부 green(무변경). |

## 5-C. 사용자 guardrail (additive-only) 검증
- `0005_chunks_v2.py upgrade()`: `op.add_column('documents',…)`×2 + `op.create_table('chunks')` + `op.create_index`. **기존 1.x 테이블 대상 `alter_column`/`drop_*` 0건** (소스 + `test_migration_0005_additive_only` schema diff 이중 증명).
- 실측: 0004→documents에 extractor 없음 → 0005→extractor/markdown_path 추가, blocks/translations DDL 불변.

## 5-D. 신규 코드 경로 → 테스트 잠금
| 신규 경로 | 잠금 |
| --- | --- |
| `parse_content_list` (type/chrome/malformed/unknown) | `test_content_list_parser` 17 |
| `ingest_mineru_output` (Document+Chunk+figure+rollback) | `test_mineru_ingest` 7 |
| migration 0005 | `test_migration_0005_additive_only`, `test_alembic_head_is_0005` |
| `Chunk` 모델 | `test_chunk_round_trip` |
| `resolve_mineru_bin` / runner | E2E smoke (실 MinerU 1회) |
| CLI 2 명령 | 실 E2E ingest |

## 5-E. 알려진 한계 (정직)
1. **runner subprocess 분기 단위 테스트 부재**: timeout/nonzero-exit/output-discovery 경로(Codex §5.4)는 단위 미커버, 실 MinerU E2E 1회만.
2. **CLI 단위 테스트 부재**: extract-mineru/ingest-mineru는 E2E로만 확인.
3. **chrome 오분류 1건**: 실 doc7서 footer "December 10, 2025"가 본문 chunk 1건 잔존 (MinerU 오라벨, Codex §3.3 예측대로). 103 중 1, 8a 허용.
4. **bbox 좌표계 미정합**: verbatim 저장만(px). 정합은 8c.

## 5-F. Scoring (100, self-assessment)
| Item | Score / Max | Evidence |
| --- | --- | --- |
| 독창성 | 12 / 15 | MinerU subprocess 디커플링(코어 의존 무증가) + typed 파서 버전경계 + additive-only diff 테스트. 견고하나 비-신규. |
| 완결성 | 31 / 35 | 8a DoD 4건 전부 충족 + 27 테스트 + 실 E2E(103 chunk) + full regression. 차감: runner subprocess 분기 + CLI 단위 테스트 미작성(§5.4 일부 미이행). |
| 안정성 | 27 / 30 | mypy strict + ruff clean, additive 이중 증명, rollback+orphan cleanup 테스트, hermetic, 1.x 무손상 3중 증명. 차감: subprocess 실패경로 미잠금. |
| 확장성 | 18 / 20 | chunk schema가 8b 바로 수용, parser 단일 버전경계, runner env 설정형. 차감: chunk_translations/embeddings 의도적 연기. |
| **Total** | **88 / 100** | |

## 5-G. Self verdict
- [ ] PASS_CANDIDATE (≥95)
- [x] **submit to cross-verify** (self 88 < 95, 정직). DoD 완전 충족이나 runner/CLI 단위 테스트 갭 실재 → cross-verify Round 1로 보강 여부 판단. RE-CODE 후보: runner path-discovery + missing-binary/nonzero 단위 테스트(Codex §5.4).
- [ ] FAIL → RE-PLAN
