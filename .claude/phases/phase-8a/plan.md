# Phase 8a — Plan: MinerU 추출 + Chunk Schema + Ingest

## Goal
MinerU `content_list.json`을 item-level chunk로 ingest하는 2.0 데이터 토대를 만든다 (추출 파이프라인 + chunk schema + figure 분리), 1.x DB 무손상.

## Scope
**In**:
- MinerU 추출 래퍼 (CPU, subprocess) — sandbox 검증 명령 인계
- chunk schema (item-level: type/text_level/bbox/page_idx/content/text_format/img_path/caption)
- content_list.json → chunks ingest (chrome 필터 + type 매핑 + latex/caption 보존)
- figure/chart 이미지 분리 저장 + 경로 기록
- CLI 2개 (`extract-mineru`, `ingest-mineru`)
- doc 7 한 챕터(990–1000) E2E 검증

**Out** (후속 phase):
- 번역 (8b) · embeddings (8b) · reflow viewer (8c) · chat/핀/RAG (8d) · 7 docs 전체 마이그레이션 (8e)
- GPU vision (사용자 제외) · 좌표계 정합(bbox px↔pt, 8c sync 시)

## Approach

### 1) MinerU 추출 래퍼 — `src/ht_lens/extract_mineru/runner.py`
MinerU를 **subprocess 외부 도구**로 호출 (라이브러리 의존 추가 X). ht_lens 코어는 torch/paddle 무의존 유지.
- 명령: `mineru -p <pdf> -o <out> -b pipeline -l <lang>` + `CUDA_VISIBLE_DEVICES=""` (CPU, Blackwell GPU abort 우회 — 검증됨)
- 바이너리 경로: env `HT_LENS_MINERU_BIN` (기본값 `~/mineru_test/venv/bin/mineru`, 후속 설치 표준화는 별도)
- 출력: `<out>/<stem>/auto/<stem>_content_list.json` + `images/`
- 반환: `MineruResult(content_list_path, images_dir, markdown_path, page_count)`

### 2) chunk schema — `src/ht_lens/db/models.py` 추가 (1.x 모델 보존)
```python
class Chunk(Base):
    __tablename__ = "chunks"
    id: int PK
    doc_id: FK(documents.id)
    page_idx: int            # MinerU page_idx (0-based)
    order_idx: int           # content_list 내 순서 (reflow 순서)
    type: str                # text|heading|equation|image|chart|table
    text_level: int | None   # heading depth (MinerU text_level), 본문은 None
    bbox_json: str           # [x0,y0,x1,y1] (MinerU 좌표계 — px scale, 정합은 8c)
    content: str             # 본문 텍스트 | latex($$..$$) | "" (image)
    text_format: str | None  # 'latex' (equation)
    img_path: str | None     # figure/chart 상대경로
    caption: str | None      # image_caption[0] 원문
class ChunkTranslation(Base):       # 8a는 schema만, 8b가 채움
    chunk_id PK FK, translated_text, caption_translated, model, status, cache_key, updated_at
class ChunkEmbedding(Base):         # 8a는 schema만, 8b가 채움
    chunk_id PK FK, model, dim, vector BLOB, source_hash, updated_at
```
Document/Page는 **재사용** (extractor-agnostic). `documents`에 `extractor` 컬럼 추가 (default `'pymupdf'`, MinerU ingest는 `'mineru'`).

### 3) ingest — `src/ht_lens/ingest_mineru/pipeline.py`
content_list.json 파싱 → Chunk rows. **type 매핑 + chrome 필터** (핵심):

| MinerU type | text_level | → chunk type | content | 비고 |
| --- | --- | --- | --- | --- |
| text | None | `text` | text | 본문 문단 |
| text | 2,3,… | `heading` | text | 섹션 제목 (text_level 보존) |
| equation | — | `equation` | text (latex) | text_format='latex' |
| image | — | `image` | "" | img_path + caption(image_caption[0]) |
| chart | — | `image` | content | img_path + caption(chart_caption[0]) |
| table | — | `table` | text (html/latex) | (현 샘플엔 없음, MinerU 방출 가능) |
| page_number / header / footer / page_footnote | — | **필터(skip)** | — | running chrome — reflow 제외 |

- 원본 `content_list.json` + `.md` 경로를 documents에 보관 (감사/재처리) — `markdown_path` 컬럼.
- figure 이미지: `<out>/images/*` → `data/extracts_v2/<doc_id>/images/` 복사, chunk.img_path = 상대경로.
- Document/Page 생성: MinerU는 page 단위 render PNG를 별도로 안 주므로 8a에선 Page를 **content_list page_idx 집합으로 생성**(width/height/bg_image_path는 middle.json 또는 origin.pdf에서; 좌측 PDF render는 8c에서 보강 — 8a는 page_idx 메타만).

### 4) 병행 DB 전략 — **plan 결정 항목 (사용자 ask)**
- **(가) 동일 DB + additive 테이블 [worker 권장]**: `ht_lens.db`에 alembic 0005로 chunks/chunk_translations/chunk_embeddings CREATE + `documents.extractor` ADD. 1.x blocks/translations 무수정(무손상=순수 additive). 단일 alembic 체인·단일 엔진. 롤백=새 테이블 drop.
- (나) 별도 DB 파일 `ht_lens_v2.db`: 완전 격리, 단 별도 alembic 체인/엔진 분기 필요 (`HT_LENS_DB_URL` 스위치는 존재하나 schema-version 가드·이중 체인 복잡). 마스터플랜 §3 초안 lean.
- 권장 (가): 단일 alembic 체인 유지(프로젝트 규율), Document/Page 재사용, additive=무손상. 마스터플랜의 "별도 파일" lean을 **구현 단순성 근거로 (가)로 정제** 제안 — 사용자 확정 필요.

### 5) CLI — `src/ht_lens/cli.py` 추가 (Typer)
- `ht-lens extract-mineru <pdf> [-o <out>] [--lang en]` → MinerU subprocess, 출력 경로 print
- `ht-lens ingest-mineru <out_dir> --filename <f> [--src en --tgt ko]` → content_list → chunks, doc_id print

## File-level changes
| Path | Action | Note |
| ---- | ------ | ---- |
| `src/ht_lens/extract_mineru/__init__.py` | new | 패키지 |
| `src/ht_lens/extract_mineru/runner.py` | new | MinerU subprocess 래퍼 |
| `src/ht_lens/ingest_mineru/__init__.py` | new | 패키지 |
| `src/ht_lens/ingest_mineru/content_list.py` | new | content_list 파서 (순수 함수, type 매핑/chrome 필터) |
| `src/ht_lens/ingest_mineru/pipeline.py` | new | 파서 → Chunk rows + figure 복사 |
| `src/ht_lens/db/models.py` | edit | Chunk/ChunkTranslation/ChunkEmbedding 추가 + Document.extractor/markdown_path |
| `src/ht_lens/db/migrations/versions/0005_*.py` | new | additive: chunks/chunk_translations/chunk_embeddings + documents.extractor/markdown_path |
| `src/ht_lens/db/session.py` | edit | ALEMBIC_HEAD "0004"→"0005" |
| `src/ht_lens/cli.py` | edit | extract-mineru, ingest-mineru 명령 |
| `tests/unit/test_content_list_parser.py` | new | type 매핑/chrome 필터/latex/caption 보존 |
| `tests/integration/test_mineru_ingest.py` | new | content_list → chunks E2E (sandbox fixture) |
| `tests/integration/test_chunk_schema.py` | new | 모델/마이그레이션 round-trip + 1.x 무손상 |

## Dependencies (new)
| Package | Why |
| ------- | --- |
| (없음 — 코어) | MinerU는 subprocess 외부 도구. ht_lens 코어에 torch/paddle 미추가 (의존 격리, lean 유지) |

## Test strategy
- **unit** (`test_content_list_parser.py`): sandbox `content_list.json`을 fixture로 복사 → 파서가 text_level=2를 heading으로, equation latex/text_format 보존, image caption 추출, page_number/footer/header/page_footnote 필터, order_idx 부여 검증. MinerU 실행 불필요(고속).
- **integration** (`test_mineru_ingest.py`): fixture content_list → 임시 DB ingest → chunks 행 검증 (type 분포, bbox JSON round-trip, latex 보존, figure img_path 존재, chrome 0건).
- **integration** (`test_chunk_schema.py`): alembic upgrade→ Chunk CRUD round-trip; **1.x 무손상** = 같은 DB에 blocks/translations 행 수 불변, 1.x 테이블 스키마 무변경 (additive만).
- **regression**: 기존 576 그대로 green (extract_mineru/ingest_mineru는 신규 패키지라 기존 import 경로 무영향).
- **E2E (verify 단계)**: `extract-mineru` (이미 sandbox에 추출된 산출물 재사용으로 시간 절약) → `ingest-mineru` → `sqlite3 ... SELECT type, COUNT(*) FROM chunks`.

## DoD mapping
| DoD item (ROADMAP 8a) | How to satisfy | Evidence plan |
| -------- | -------------- | ------------- |
| doc 7 한 챕터 MinerU 추출 → chunk DB ingest 성공 | extract-mineru + ingest-mineru, doc7 990–1000 | `SELECT COUNT(*) FROM chunks WHERE doc_id=<n>` > 0, type 분포 출력 |
| chunk가 bbox/page/type/latex/caption 보존 | 파서 매핑 + 모델 컬럼 | unit + integration assert (latex `$$`, caption, bbox round-trip, page_idx) |
| figure 이미지 분리 + 경로 저장 | pipeline이 images/ 복사 + img_path 기록 | `ls data/extracts_v2/<doc>/images/` + `SELECT img_path FROM chunks WHERE type='image'` |
| 1.x DB 무손상 (병행) | additive 마이그레이션만 | `SELECT COUNT(*) FROM blocks`=49850 불변, 1.x 테이블 스키마 diff 없음 |

## Plan 결정 항목 (✅ 2026-05-30 확정)
1. ✅ **병행 DB**: 동일 DB + additive 테이블 (alembic 0005, 별도 파일 X).
   - **사용자 guardrail**: 0005가 기존 1.x 테이블을 절대 ALTER/DROP 안 하는지 verify에서 확인. 허용 작업 = `CREATE TABLE` 신규 + `documents`에 `ADD COLUMN`(default). blocks/translations/pages/threads/messages/jobs/block_embeddings 무수정.
2. ✅ **모듈 명명**: `extract_mineru` / `ingest_mineru` (도구명, cutover 후에도 유효).
3. ✅ **CLI 명명**: `extract-mineru` / `ingest-mineru`.
4. ✅ **chart 타입**: `image`로 통합, `content` 필드 보존 (정보 손실 0, 후속 재분류 여지).

baseline 회귀: **576 passed** (Phase 6i hot-fix 포함, 2026-05-30 실측).

### verify 필수 검사 (사용자 guardrail 반영)
- alembic 0005 `upgrade()` 본문에 `op.create_table` + `op.add_column('documents', ...)` 만 존재, `op.alter_column`/`op.drop_*`가 기존 1.x 테이블 대상으로 **0건**.
- 마이그레이션 적용 전후 1.x 테이블 스키마 diff = (documents에 컬럼 2개 추가) 외 0.
- `SELECT COUNT(*)`: blocks=49850, translations=44607, block_embeddings=17257 불변.

## 위험 / 완화
- MinerU 출력 스키마 버전 의존 → 파서를 방어적으로(키 부재 graceful), content_list 버전 sandbox 3.2.1 기준 명시.
- bbox 좌표계 (MinerU px scale ≠ PDF pt) → 8a는 verbatim 저장만, 정합은 8c 좌우비교 시.
- Page 메타 (width/height/render PNG) 부재 → 8a는 page_idx 집합만 생성, render PNG는 8c에서 (MinerU origin.pdf 또는 PyMuPDF render 재사용).
