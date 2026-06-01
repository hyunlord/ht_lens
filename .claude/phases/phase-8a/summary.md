# Phase 8a — Summary

## Status
**ESCALATE_TO_PLANNER** (WORKFLOW Stage 6: cross-verify Round 2 DOWNGRADE → push 보류, Planner 결정).
Codex가 명시적으로 "another RE-CODE 권장 안 함" → 추가 자동 수리 루프 불필요. PASS 여부는 Planner의 잔존 리스크 수용 판단.

## Score
- Self (v2): **90 / 100** (12 + 33 + 28 + 17)
- Codex R1: **REJECT** (~77-80) — same-filename collision로 1.x 삭제 위험(핵심), text_level raw ValueError, runner/CLI 미테스트
- Codex R2: **DOWNGRADE** (~86) — R1 concrete blocker 전부 fix+테스트 확인, 잔존은 구조적
- 양측 합의: 새 concrete 결함 없음. 사실상 PASS 후보, 점수만 90 vs 86.

## What was built
ht_lens 2.0 데이터 토대 (MinerU + chunk schema + ingest), 1.x 무손상 병행.

- **extract_mineru/runner.py**: MinerU를 CPU subprocess 외부 도구로 호출 (torch/paddle 코어 의존 0). env(HT_LENS_MINERU_BIN)/PATH 바이너리 탐색, 출력 경로 glob 탐색, exit/timeout/output 견고성 (MineruError).
- **ingest_mineru/content_list.py**: typed dataclass 파서. type 매핑(text+level→heading, equation/image/chart→image/table), chrome 필터(page_number/header/footer/page_footnote), 명시적 malformed 처리(page_idx·text_level→ContentListError, bbox→[]), unknown 보존.
- **ingest_mineru/pipeline.py**: content_list → Document(extractor='mineru') + Chunk + figure 복사(data/extracts_v2/<doc>/images/), rollback+orphan cleanup. **존재 lookup이 extractor='mineru' 스코프** → 1.x pymupdf 동명 문서 절대 미접촉.
- **db**: Chunk 모델(item-level, page_idx plain int, pages FK 없음) + Document.extractor/markdown_path. alembic **0005 additive-only** (chunks CREATE + documents 2컬럼 ADD, 1.x ALTER/DROP 0).
- **cli**: extract-mineru, ingest-mineru.
- 8b 연기: chunk_translations, chunk_embeddings (blast radius 최소화, debate §1.1).

## Evidence
- ruff check/format clean, mypy strict clean(75 files)
- **619 passed**, 1 skipped (baseline 576 + 43 new). full regression 576 영역 무변경.
- 실 E2E: doc7 990-1000 content_list → chunks=103 images=30 (text 57/heading 16/image 15/equation 15)
- additive-only: test_migration_0005_additive_only (1.x 7테이블 DDL byte-identical)
- 1.x 무손상: delta=0 + 동명충돌 공존 테스트(R1 핵심 fix)

## Deviations from plan
- 마스터플랜 '별도 DB 파일' → 8a plan에서 동일 DB additive로 정제(사용자 승인 + additive-only guardrail 테스트).
- chunk_translations/chunk_embeddings: plan은 8a 생성 검토했으나 debate §1.1 수용으로 8b 연기.
- Page 행: plan 초안 "page_idx 메타 생성" → debate §2.1 수용으로 8a는 Page 미생성(non-null 위반 회피), chunks.page_idx는 plain int.

## Known issues / debt (Planner 판단용)
1. **extract-mineru CLI 단위 테스트 없음** (ingest-mineru는 3건). run_mineru 하위 11 단위로 위험 완화. Codex "reject 사유 아님".
2. **overwrite 시 옛 managed image dir orphan** — DB 무손상엔 무관, 재-ingest 잦아지기 전 정리 권장.
3. **timeout 분기 단위 미테스트** (nonzero/no-output/missing은 커버).
4. **chrome 오분류 1건** (실 doc7 footer 1줄 본문 잔존, MinerU 라벨 한계, 103 중 1).
5. **절대 img_path / basename-only 복사** — 이식성/충돌 리스크, 8c 서빙 설계 시 상대화 검토.
6. **bbox 좌표계 미정합** (verbatim px 저장) — 8c 좌우비교 시 정합.
7. coverage/CI는 push 후 확정 (로컬 --no-cov는 프로젝트 표준).

## Recommended next (Planner)
1. **PASS 판단**: R1 concrete blocker 전부 해소 + Codex "RE-CODE 불필요" + 619 green + 1.x 무손상 3중 증명. 잔존(1~7)은 구조적/8c·8b 영역. Phase 6i 선례(R2 DOWNGRADE→Planner PASS)와 동형.
   - PASS면 push + CI 확인 → Phase 8b.
2. 또는 **micro-fix 지시**(Planner 직접): extract-mineru CLI 테스트 1건 + overwrite orphan cleanup. 둘 다 <30분, 8b 착수 전 끼워넣기 가능.
3. **RE-PLAN 불필요** (양측 합의).

Push 상태: **HELD** (cross-verify Round 2 DOWNGRADE). Planner 지시 대기.
