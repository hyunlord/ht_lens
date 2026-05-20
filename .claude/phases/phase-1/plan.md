# Phase 1 — Plan

## Goal
`python -m ht_lens.extract <pdf> -o <out>` CLI를 만들어, PDF 한 권을 페이지별 200dpi PNG + 정규화된 block JSON으로 분해한다. 한/영/혼재 sample 3종에 대해 snapshot 기반 회귀 테스트가 통과한다.

## Scope

**In**
- PyMuPDF 격리 wrapper (`extract/_fitz.py`)
- 페이지 렌더러 (200dpi PNG, zero-padded 4자리 파일명)
- Text block 추출 + paragraph grouping
- Header 판정 (font-size 휴리스틱)
- Reading order (1~3컬럼 자동 감지)
- Image block 추출 (bbox만; 픽셀 저장은 옵션)
- 언어 감지 (langdetect → `en|ko|mixed|unknown`)
- `doc_meta.json` 생성 (filename / num_pages / lang_guess / sha256 / extracted_at / extractor_version)
- CLI: `python -m ht_lens.extract`, `ht-lens extract` 양쪽 동작
- Snapshot test (3 fixture, 정규화 함수 포함)
- Unit test (grouping, reading order, language, normalization)

**Out** (다음 phase로)
- 캡션/각주 분리 — Phase 6에서 보강 (현재는 paragraph로 흡수)
- 표(table) 인식 — Phase 6 (block.type=`text`로 흡수)
- OCR (스캔본) — 미지원, plan에 명시
- DB ingest — Phase 2
- 번역/LLM — Phase 2
- inline image vs floating figure 구분 — Phase 1에서는 figure만 추출

## Approach

### 1. PyMuPDF 격리 (`extract/_fitz.py`)

PyMuPDF의 타입 스텁은 약하므로 fitz import는 이 파일에 **유일하게** 허용된다. 외부에는 다음 typed 인터페이스만 노출:

```python
@dataclass(frozen=True)
class RawSpan:
    text: str
    bbox: tuple[float, float, float, float]
    font: str
    size: float
    flags: int  # bold/italic 비트마스크

@dataclass(frozen=True)
class RawLine:
    bbox: tuple[float, float, float, float]
    spans: tuple[RawSpan, ...]
    direction: tuple[float, float]  # writing direction unit vector

@dataclass(frozen=True)
class RawBlock:
    bbox: tuple[float, float, float, float]
    block_type: Literal["text", "image"]
    lines: tuple[RawLine, ...]  # type="image"면 빈 tuple

@dataclass(frozen=True)
class RawPage:
    page_num: int        # 1-indexed
    width: float         # points
    height: float        # points
    rotation: int        # 0/90/180/270
    blocks: tuple[RawBlock, ...]  # PyMuPDF sort=True 순서 그대로

@contextmanager
def open_pdf(path: Path) -> Iterator["FitzDoc"]:
    """Context manager — 페이지 처리 중 예외에도 close 보장."""

def render_png(doc: FitzDoc, page_idx: int, dpi: int) -> bytes: ...
def iter_pages(doc: FitzDoc) -> Iterator[RawPage]: ...
```

`FitzDoc`은 opaque newtype. 내부에선 `cast(fitz.Document, ...)`로 좁힘.
`# type: ignore`는 이 파일에서만 허용.

**Baseline source**: `page.get_text("dict", sort=True)`로 PyMuPDF 자체 정렬 결과를 받는다. Phase 1에서는 이 정렬을 **신뢰**하고, 컬럼 휴리스틱은 fallback으로만 적용 (§3 참조).

### 2. Block grouping (`extract/blocks.py`)

PyMuPDF block 단위에서는 한 paragraph가 여러 block으로 쪼개지거나 한 block에 여러 paragraph가 섞이는 경우가 흔하다. `RawLine` 단위로 다음 휴리스틱:

- **Paragraph 묶기 기준** (단일 RawBlock 안에서 line-by-line):
  - y-gap ≤ `0.5 * median_line_height` → 같은 paragraph
  - y-gap > `1.2 * median_line_height` → paragraph 분리
  - font-size 차이 > 20% → 분리
- **Header 판정**:
  - font-size ≥ `1.4 * page_median_font_size` AND 라인 수 ≤ 2 → `type="header"`
  - 그 외 텍스트는 `type="text"`
- **빈 block** (`text=""` and `type="text"`) → 폐기
- **Image block**: `type="image"`, text="", bbox 유지
- **Line bbox**가 없는 경우 (rotation 등): span bbox union으로 대체

### 3. Reading order (`extract/reading_order.py`)

**Phase 1 baseline은 PyMuPDF `sort=True`의 출력을 그대로 사용한다.** 도메인 휴리스틱은 다음 조건일 때만 fallback:

1. PyMuPDF 결과에 y가 뒤로 가는 곳이 1회라도 있으면 fallback 진입 (cover 페이지의 회전 마진 텍스트, PyMuPDF 정렬 오류 등).
2. fallback 절차:
   - bbox width > `0.7 * page_width` block을 spanning header로 분리하여 최상단 y0 순으로 먼저 배치
   - 나머지 body는 `(y0, x0)` 정렬

**원래 plan에는 1~3 컬럼 자동 감지(x-clustering)가 있었지만 RE-CODE에서 제거했다.** 이유: 단일-block 마진(arXiv 세로 스탬프 등)을 별개 컬럼으로 잘못 잡아 cover 페이지 순서를 더 망가뜨림. 진짜 멀티컬럼 본문 fixture가 없는 상태에서는 단순 y0 정렬이 ROADMAP "80% 목표"에 더 부합. 진짜 2-컬럼 본문 정렬은 fixture가 들어오는 Phase 6에서 재검토. 합성 unit test는 동일 입력에 대해 두 알고리즘 모두 동일한 출력을 내므로 보존.

### 4. Page renderer (`extract/render.py`)

```python
def render_page_png(doc: FitzDoc, page_idx: int, out_path: Path, dpi: int = 200) -> None
```

PyMuPDF의 `page.get_pixmap(dpi=dpi).tobytes("png")` 결과를 atomic write (tempfile → rename).

### 5. Language detection (`extract/language.py`)

- 페이지별로 전체 텍스트를 모아 langdetect 호출
- 문서 전체: 페이지별 lang의 다수결
- 페이지마다 다른 lang이 30% 이상이면 `"mixed"`
- 텍스트 < 50자: `"unknown"`
- langdetect는 결정적이지 않으므로 `DetectorFactory.seed = 0` 고정

### 6. Pipeline (`extract/pipeline.py`)

```python
def extract_pdf(pdf_path: Path, out_dir: Path, *, dpi: int = 200, save_images: bool = False, overwrite: bool = False) -> ExtractResult
```

흐름:
1. `out_dir` 존재 + 비어있지 않음 + `overwrite=False` → `OutputDirNotEmptyError` (exit 2).
   `overwrite=True`이면 `out_dir/{pages,images,doc_meta.json}`만 정밀 삭제 (외부 파일 보호).
2. `out_dir`/`pages`/`images` 디렉토리 생성 (없으면)
3. fitz 열기 (`open_pdf` context manager) → for each page (1-indexed):
   a. `render_page_png` → `pages/page_NNNN.png`
   b. `iter_pages` 결과로 grouping → reading order → block 리스트
   c. block id를 `p{N}_b{ORDER:03d}` 형식으로 부여
   d. bbox 소수점 1자리 round
   e. `pages/page_NNNN.json` 저장 (atomic write)
   f. image block의 픽셀 추출은 `save_images=True`일 때만 (기본 False)
4. 문서 단위 lang 집계
5. `doc_meta.json` 저장 (sha256은 streaming hash, ISO 8601 UTC, version은 `ht_lens.__version__`)

**부분 실패 정책**: 페이지 처리 중 예외 발생 시 context manager가 닫고, 부분 출력은 그대로 둔다 (사용자는 `--overwrite`로 재시도). 모든 페이지 PNG/JSON 저장은 atomic temp-rename이라 corruption은 없다.

### 6.5. Per-page JSON 스키마 확장 (prompt-fixed 베이스 + 좌표 메타)

prompt에 명시된 스키마는 다음 필드를 가진다:
```
page_num, width, height, blocks[]
```

debate §2(coordinate unit)와 §3(rotation)을 수용해 다음 필드를 **추가**한다 (제거는 없음):

```json
{
  "page_num": 1,
  "width": 612.0,            // PDF points (변경 없음)
  "height": 792.0,           // PDF points
  "rotation": 0,             // [추가] 0/90/180/270 — viewer가 회전 보정에 사용
  "render": {                // [추가] 200dpi PNG 좌표계 정보
    "dpi": 200,
    "pixel_width": 1700,
    "pixel_height": 2200,
    "scale": 2.777           // = dpi / 72
  },
  "unit": "pt",              // [추가] bbox 단위 명시 (항상 "pt")
  "blocks": [...]            // 변경 없음
}
```

근거: Phase 4 viewer가 PNG 픽셀과 PDF point bbox를 일치시키려면 dpi/rotation을 알아야 한다. prompt 스키마는 필수 필드만 명시했으므로 추가는 호환 가능.

### 7. CLI (`extract/__main__.py`, `cli.py`)

- `src/ht_lens/extract/__main__.py`: `python -m ht_lens.extract <pdf> -o <out>` 진입점
- `src/ht_lens/cli.py`: typer `app` 정의, `extract` subcommand
- `pyproject.toml`의 `[project.scripts]` 활성화: `ht-lens = "ht_lens.cli:app"`
- 옵션:
  - `-o, --out PATH` (required)
  - `--dpi INT` (default 200)
  - `--save-images / --no-save-images` (default no)
  - `--overwrite / --no-overwrite` (default no — 기존 out_dir 비어있어야 진행)
- 종료 코드: 0=성공, 2=잘못된 입력(파일 없음/암호화), 3=PDF 파싱 실패

### 8. Error handling

- 입력 파일 없음 / 디렉토리 → typer가 exit 2
- 암호화 PDF: `doc.needs_pass` 체크 → custom `EncryptedPDFError` → exit 2 + stderr 메시지
- 깨진 PDF: `fitz.FileDataError` → `CorruptedPDFError` → exit 3
- 빈 페이지 (block 0개): 정상 처리 (`blocks: []`, JSON은 저장)
- 페이지 단위 예외는 fail-fast (Phase 1은 단순성 우선)

## File-level changes

| Path | Action | Note |
| ---- | ------ | ---- |
| `pyproject.toml` | modify | dep 추가(pymupdf/pillow/langdetect/syrupy), scripts 활성화 |
| `src/ht_lens/__init__.py` | modify | 변경 없음 (version만 노출) |
| `src/ht_lens/extract/__init__.py` | new | 공개 API: `extract_pdf`, `ExtractResult` |
| `src/ht_lens/extract/__main__.py` | new | `python -m ht_lens.extract` 진입 |
| `src/ht_lens/extract/_fitz.py` | new | **유일한 fitz 격리 wrapper** |
| `src/ht_lens/extract/models.py` | new | pydantic schema (Block, Page, DocMeta) |
| `src/ht_lens/extract/blocks.py` | new | paragraph/header grouping |
| `src/ht_lens/extract/reading_order.py` | new | 컬럼 인식 + 순서화 |
| `src/ht_lens/extract/render.py` | new | PNG 렌더 |
| `src/ht_lens/extract/language.py` | new | langdetect wrapper |
| `src/ht_lens/extract/pipeline.py` | new | end-to-end 통합 |
| `src/ht_lens/extract/normalize.py` | new | snapshot용 정규화 함수 (bbox round, redact) |
| `src/ht_lens/cli.py` | new | typer app, `extract` subcommand |
| `src/ht_lens/errors.py` | new | `EncryptedPDFError`, `CorruptedPDFError` |
| `tests/unit/test_blocks.py` | new | paragraph grouping unit |
| `tests/unit/test_reading_order.py` | new | 컬럼 인식 unit |
| `tests/unit/test_language.py` | new | mixed 판정 unit |
| `tests/unit/test_normalize.py` | new | snapshot 정규화 |
| `tests/integration/test_extract_pipeline.py` | new | 3 fixture × 통합 (page count, lang, schema, render scale) |
| `tests/integration/test_extract_snapshot.py` | new | syrupy snapshot (정규화된 block 구조) |
| `tests/integration/test_cli_errors.py` | new | overwrite / encrypted / corrupted / scanned 시나리오 |
| `tests/integration/test_rotated_page.py` | new | 합성 회전 PDF의 bbox↔픽셀 일치 |
| `tests/integration/test_human_review.py` | new | `docs/phases/phase-1/samples.md` 생성 (DoD evidence) |
| `tests/integration/__snapshots__/` | new (generated) | snapshot baseline |
| `docs/phases/phase-1/samples.md` | new (generated) | 사람-검토용 block 트리 dump |

## Dependencies (new)

| Package | Why |
| ------- | --- |
| `pymupdf` (main) | PDF 파싱/렌더링 — ROADMAP 명시 |
| `pillow` (main) | 이미지 추출/검증 — ROADMAP 명시 |
| `langdetect` (main) | 언어 감지 — ROADMAP 명시 |
| `syrupy` (dev) | snapshot 테스트 — prompt 명시 |

이 외 추가 없음. mypy 위해 별도 stub 패키지 도입하지 않고 `_fitz.py` 격리로 처리.

## Test strategy

### Unit
- `test_blocks.py`: synthetic lines로 paragraph 묶기 / header 판정 검증
- `test_reading_order.py`:
  - 1/2/3컬럼 synthetic block 리스트 → 기대 순서
  - `test_reading_order_indented_bullets_do_not_create_columns` — 들여쓰기 bullet은 컬럼이 아님
  - `test_reading_order_spanning_header_then_two_columns` — width>0.7 헤더가 컬럼 위에 옴
- `test_language.py`: 짧은 텍스트, 한글, 영문, 혼재 케이스
- `test_normalize.py`: bbox round, 비결정 필드 redact

### Integration
- `test_extract_pipeline.py` (3 sample 공통):
  - `test_fixture_pdfs_exist_and_are_nonempty` — fixture가 실제 존재 (skip 회피 방지)
  - `num_pages > 0`, `doc_meta.json` 존재, `lang_guess`가 기대 값(en/ko/mixed)
  - 모든 페이지 PNG 존재, PIL로 열기, pixel size가 `render.pixel_width/height`와 일치
  - 모든 페이지 JSON 존재, schema(page_num/width/height/rotation/render/unit/blocks) 모두 채워짐
  - 적어도 한 페이지 이상에 block ≥ 1 (전체-이미지 페이지 허용)
  - 모든 block id가 `p{N}_b{NNN}` 패턴
  - `test_page_json_records_coordinate_space_and_render_scale` — render.dpi/pixel_*/scale 일치 검증
- `test_extract_snapshot.py` (3 sample): 정규화된 block 구조를 syrupy로 비교
- `test_cli_errors.py`:
  - `test_cli_rejects_existing_non_empty_out_dir_without_overwrite` (exit 2)
  - `test_cli_overwrite_replaces_previous_output` (exit 0, 이전 파일 사라짐)
  - `test_encrypted_pdf_exit_code_2` (synthetic encrypted PDF in tmp)
  - `test_corrupted_pdf_exit_code_3` (bytes garbage)
  - `test_scanned_page_writes_empty_blocks_json` (synthetic image-only PDF)
- `test_rotated_page.py`:
  - `test_rotated_page_bbox_matches_rendered_png_dimensions` — fitz로 합성 회전 PDF 생성, render 픽셀 크기 = (page.rect after rotation) × scale 검증
- Human-review artifact:
  - `tests/integration/test_human_review.py`에서 3 sample에 대해 `docs/phases/phase-1/samples.md` 생성 — 페이지별 block 트리(id/type/bbox/text 60자) 덤프. DoD "사람이 봐도 합리적" evidence.

### Snapshot 정규화 (`normalize.py`)
- bbox: 소수점 1자리 round
- doc_meta: `extracted_at`, `src_pdf_sha256` redact (`"<REDACTED>"`)
- doc_meta: `extractor_version`은 redact (Phase 1 version bump 영향 차단)
- block.text는 그대로 (snapshot의 본질)
- 페이지 PNG는 snapshot 대상 아님 (사람이 spot-check)

### Performance
- 측정만, 회귀 임계는 두지 않음. sample 3종 합쳐 30초 이내가 목표.
- 200dpi PNG 한 페이지 ≈ 1.5MB 정도 예상 → 3 fixture × 평균 10페이지 ≈ 50MB 디스크. 정상.

## DoD mapping

| DoD item | How to satisfy | Evidence plan |
| -------- | -------------- | ------------- |
| 3종 sample PDF block JSON이 합리적 | grouping + reading_order + 3 fixture × 통합 테스트 | verify.md 5-B에 페이지별 block count + 첫 page 첫 block text 첫 50자 출력 |
| snapshot test 통과 | syrupy + 정규화 함수 | verify.md 5-A에 `pytest -k snapshot` 결과 |
| extract 의존성 제한 (pymupdf/pillow/langdetect) | pyproject.toml dep 목록 + grep으로 검증 | verify.md 5-A에 dep 목록 |
| mypy strict 0, ruff clean | 매 커밋 후 `make lint`, CI에서도 강제 | verify.md 5-A 표준 |
| CLI `python -m ht_lens.extract <pdf> -o <out>` 동작 | `__main__.py` + typer | verify.md 5-B에 3 sample 실행 결과 |
