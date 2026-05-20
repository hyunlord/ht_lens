# Phase 2a — Challenge

## Debate responses

### 1. Over-engineering

- **WAL / `synchronous=NORMAL` PRAGMA premature** — **accept**. Phase 2a serial CLI에는 불필요. plan revise: `foreign_keys=ON`만 남기고 WAL/synchronous는 Phase 2b/3에서 부하 측정 후 결정. `foreign_keys=ON`은 cascade test 정합성에 필수이므로 유지.
- **`ht-lens db migrate` 편의 명령 + runtime schema gate** — **partial accept**.
  - `ht-lens db migrate` 명령 제거 (Codex 지적대로 minimal). 사용자에게 `uv run alembic upgrade head` 안내로 충분.
  - runtime schema gate (`SchemaVersionMismatch` raise)는 **유지**. 이유: 사용자가 migrate 안 하고 ingest 호출 시 IntegrityError 같은 모호한 에러보다 "run: uv run alembic upgrade head" 명확한 메시지가 UX/디버깅에 명백히 우월. 코드 증분도 작음 (`current_schema_version()` 헬퍼 + ingest 시작 시 1줄 check).
- **`LLMClient`에 `chat()` + `health_check()`까지** — **reject**. prompt "사전 결정사항 (논쟁 금지)"의 `LLMClient interface (고정)` 섹션에 `translate`, `chat`, `health_check` 3 메서드 명시. prompt-fixed.

### 2. Hidden assumptions

- **PK strategy 명시 누락 / Phase 1 block id `p1_b001` 충돌** — **partial accept**. prompt 스키마 모두 `id: Mapped[int] = mapped_column(primary_key=True)` 형태로 surrogate PK이고 Phase 1 block id는 `block_local_id`(string) 컬럼에 저장. plan에 이미 명시했으나 강조 부족 → revise에서 "PK 전략: 모든 테이블 surrogate int. Phase 1 식별자(`p1_b001`)는 `block_local_id`에 보존, 글로벌 unique 가정 없음" 추가.
- **`translations(block_id PK)`가 Phase 2b 캐시키 / Phase 6 멀티모델과 충돌** — **partial accept (큰 우려)**. Codex 지적은 정확. 그러나 prompt의 "DB schema (고정, plan에서 변경 금지)"가 `translations    (block_id PK, translated_text, model, ...)`을 명시. Phase 2a에서 스키마 변경은 prompt 위반.
  - **방침**: prompt 스키마 그대로 적재. Phase 2b 캐시는 ORM 외부에서 (e.g. `text+src+tgt+model` 해시를 별도 키로 메모이즈하거나 새 cache 테이블 추가) 처리할 여지를 남김. ROADMAP의 Phase 6 "block 단위 재번역", "모델 빠른 토글"이 schema migration 한 번 더 들어가는 게 정답. → known debt로 summary.md에 명시.
  - Planner에게 escalate: Phase 2b plan 작성 시 이 결정 재검토.
- **`PageDoc` 재사용이 ingest integrity를 자동 보장하지 않음** — **accept**. plan revise: ingest pipeline에 다음 명시적 검증 추가:
  - `doc_meta.num_pages == len(discovered page_*.json)`
  - page_num 시퀀스가 1..N contiguous
  - 각 page에 대응 `pages/page_{N:04d}.png` 존재
  - 위반 시 `IngestError` raise, exit 2.
- **`--src` / `--tgt` semantics 정의 누락** — **accept**. plan revise:
  - `--tgt` default = `ko`.
  - `--src` default = `DocMeta.lang_guess`가 `"en"` 또는 `"ko"`면 그 값. `"mixed"`/`"unknown"`이면 `--src` 미지정 시 exit 2 + 메시지 ("source language ambiguous; pass --src explicitly"). sample_mixed.pdf는 `--src en` 또는 `--src ko` 명시로 ingest. (Phase 2b 번역 단계에서 추가 정교화 가능.)
- **`rotation` / `render.*` 폐기 가정** — **reject (이미 plan에 포함됨)**. plan File-level changes의 `Page` 모델에 `rotation`, `render_dpi`, `pixel_width`, `pixel_height` 명시. `scale`은 `pixel_width / width`로 도출 가능해 normalization 차원에서 의도적으로 제외 (DB 정규화 원칙). Codex 오독.

### 3. Edge cases

- **Filename 기반 overwrite 위험 (같은 이름 다른 PDF)** — **accept**. plan revise:
  - `--overwrite`: 기존 doc(filename 기준) 발견 시, 기존 행에서 도출할 sha256은 없음(스키마에 컬럼 없음). 따라서 `doc_meta.json`만 비교 가능. 첫 ingest 시 in-memory sha256 기록 안 됨.
  - 정책: `--overwrite` 사용 시 filename 매칭만 한다는 점을 **CLI help 텍스트와 stderr 진입 메시지에 경고**로 명시 ("WARNING: --overwrite matches by filename only; if you have two different PDFs with the same name, this will destroy data"). sha256 비교는 향후 마이그레이션으로 컬럼 추가 시 enable. Phase 6 known debt.
- **Corrupt extract dirs (missing JSON, stale JSON, mismatched num_pages, missing PNG)** — **accept**. 위 §2의 추가 검증으로 cover. test_ingest_pipeline에 manifest mismatch fixture(임의 page json 제거 + 임의 stale json 추가) 케이스 추가.
- **빈 텍스트 image block** — **accept**. test assertion 수정:
  - "첫 block의 `original_text` 비어있지 않음" → "**첫 text-type block**의 `original_text` 비어있지 않음" (image block은 빈 텍스트 허용).
  - 신규 test `test_ingest_accepts_empty_text_image_blocks` 추가.
- **Overwrite rollback 미증명** — **accept**. transaction 경계 명확화:
  - `ingest_extract_dir` 전체를 단일 transaction. `--overwrite` delete + 신규 insert 모두 같은 transaction 안. 도중 실패 시 rollback → 기존 doc survive.
  - 신규 test `test_overwrite_rollback_preserves_existing_document_on_failure` 추가: 정상 ingest 후 tamper된 extract dir로 `--overwrite` 시도 → 기존 행 그대로.

### 4. Alternative approaches

- **Surrogate int PK + `source_block_id` 별도** — **이미 채택됨** (prompt 스키마와 plan 모두). 강조 부족했던 점은 plan revise에서 보완.
- **`translations` 키 재설계** — 위 §2 같은 이유로 **reject (prompt 고정)**. 단 Phase 6/2b plan에서 재검토 필요 known debt.
- **`rotation`/`pixel_*` persist** — **이미 채택됨**.
- **`db migrate` 명령 + runtime gate를 thin wrapper로** — partial accept. `ht-lens db migrate` 제거, runtime gate 유지 (위 §1 참조).

### 5. Missing tests

모두 **accept**. plan revise에서 다음 5 테스트를 Test strategy 섹션에 추가:

1. `test_ingest_rejects_or_disambiguates_duplicate_filenames_with_different_sha256` — 동일 filename, 다른 sha256 추출 산출물 → overwrite 없이는 거부, overwrite 시 stderr 경고.
2. `test_ingest_detects_manifest_mismatch` — `doc_meta.num_pages` 불일치 또는 page json 갭 → exit 2 + 구체 메시지.
3. `test_ingest_accepts_empty_text_image_blocks` — image type + `text=""` 정상 적재.
4. `test_overwrite_rollback_preserves_existing_document_on_failure` — 위 §3.
5. `test_ht_lens_console_script_ingest` — `subprocess.run(["ht-lens", "ingest", ...])` (Phase 1의 `test_module_cli.py` 패턴과 일관). `python -m ht_lens.ingest`는 별도 케이스. `db migrate` 명령은 제거했으므로 test도 없음.

## Plan revisions (after debate)

1. **§ Approach.1 PRAGMA**: WAL/synchronous 제거. `foreign_keys=ON`만 유지.
2. **§ Approach.6 Alembic 적용 정책**: `ht-lens db migrate` 편의 명령 **제거**. 사용자 가이드는 `uv run alembic upgrade head` 안내. runtime schema gate (`SchemaVersionMismatch` raise + exit 3)는 유지.
3. **§ Approach.3 재진입성 → 추가**: `--overwrite` 시 stderr 경고 ("WARNING: --overwrite matches by filename only"). sha256 컬럼은 Phase 6 known debt.
4. **§ Approach.4 Phase 1 page JSON 스키마 변동 대비 → 강화**: ingest pipeline에 명시적 검증 추가
   - `doc_meta.num_pages == len(page_*.json)`
   - page_num 1..N contiguous
   - 각 `pages/page_{N:04d}.png` 존재
   - 위반 시 `IngestError`(exit 2)
5. **§ Approach 새 항목 8 — `--src`/`--tgt` 처리**:
   - `--tgt` default `ko`.
   - `--src` default = `DocMeta.lang_guess` (en/ko에 한해). mixed/unknown인데 명시 안 했으면 exit 2.
6. **§ Approach PK 명시**: 모든 테이블 surrogate int PK. Phase 1 식별자(`p1_b001`)는 `block_local_id`에 보존.
7. **§ Approach 부가결정 새 항목**: `translations.block_id PK`는 prompt 고정. 멀티모델 캐시·재번역은 Phase 6에서 스키마 마이그레이션 (known debt). Phase 2b는 단일 모델 캐시 가정으로 진행.
8. **§ File-level changes**:
   - `src/ht_lens/cli.py` Modify: `ingest` subcommand 추가. `db_migrate` subcommand 제거.
9. **§ Test strategy → Integration에 위 5 신규 테스트 추가**:
   - `test_ingest_rejects_or_disambiguates_duplicate_filenames_with_different_sha256`
   - `test_ingest_detects_manifest_mismatch`
   - `test_ingest_accepts_empty_text_image_blocks`
   - `test_overwrite_rollback_preserves_existing_document_on_failure`
   - `test_ht_lens_console_script_ingest`
10. **§ Test strategy → Unit test_ingest_pipeline 의 첫 block 검사**: "첫 text-type block original_text 비어있지 않음"으로 약화.

plan.md 파일 자체는 별도 commit으로 patch 적용 (`docs(phase-2a): plan revisions from debate`).

## DoD checklist

| DoD item | Status | Evidence plan |
| -------- | ------ | -------- |
| 3종 fixture extract 산출물을 ingest 가능, DB 행 합리적 | planned | `test_ingest_pipeline.py` 3 fixture parametrize + verify.md manual e2e 표 |
| `LLMClient` interface 정의 + `MockLLMClient` unit test 통과 | planned | `src/ht_lens/llm/{client,mock,factory}.py` + `test_llm_mock.py` |
| mypy strict (SQLAlchemy 2.0 typed 포함) | planned | `make check` 0 error. `[[tool.mypy.overrides]]`로 alembic versions만 strict 완화 |
| ruff clean | planned | `make check` 0 issue |
| end-to-end ingest 1회 동작 (CLI exit 0) | planned | `python -m ht_lens.ingest <dir> --db-path <db>` + `ht-lens ingest <dir>` (subprocess test + verify.md manual) |
| Alembic migration 1개 생성, 적용 가능 | planned | `0001_initial_schema.py`. `uv run alembic upgrade head` → sqlite_master에 7+1 테이블 |

## Risk register

| Risk | Likelihood | Impact | Mitigation |
| ---- | ---------- | ------ | ---------- |
| SQLAlchemy 2.0 `Mapped[...]` + mypy strict 충돌 | Medium | Medium | typed Mapped 패턴, public guide 따름, 필요 시 type:ignore 최소화 |
| Alembic async `env.py` 호환 | Medium | Low | 공식 async 패턴 (run_sync) |
| ingest 중 Pydantic ValidationError → 모호한 에러 | Low | Medium | IngestError wrap + page_num 명시 |
| Filename overwrite collision | Medium | High | stderr warning, sha256 컬럼은 Phase 6 추가 known debt |
| translations.block_id PK가 Phase 2b/6 캐시 요구와 충돌 | High | Medium | prompt 고정. Phase 2b는 단일 모델 가정. Phase 6에서 schema migration known debt |
| Corrupt extract dir 처리 누락 | Medium | Medium | manifest mismatch/PNG missing/page json gap 모두 명시적 검증 + test |
| alembic versions 코드가 mypy strict 통과 불가 | Medium | Low | `[[tool.mypy.overrides]]`로 strict 완화 (해당 모듈만) |

## Decision

- [x] **PASS** → proceed to code
- [ ] RE-PLAN

**근거**:
- Codex 비판 14건 중 9건 accept (실제로 plan에 통합), 2건 partial accept (정당화 후 부분 반영), 3건 reject (2건은 prompt-fixed, 1건은 Codex 오독).
- Reject 비율 3/14 = 21%, plan에 명시된 "3개 이상 reject 시 재검토" 임계값 부근이지만 모두 정당한 이유:
  - `translations PK`: prompt 고정사항 (논쟁 금지 영역)
  - `LLMClient` API 표면: prompt 고정사항
  - `rotation/render` 폐기: Codex 오독 (plan에 이미 포함됨)
- 큰 scope 변경 없음. 추가 검증/테스트는 plan에 자연스럽게 통합 가능.
- Plan revisions 10개를 plan.md에 patch 적용 후 Stage 4 진행.
