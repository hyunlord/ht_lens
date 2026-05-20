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
class RawBlock:
    bbox: tuple[float, float, float, float]
    block_type: Literal["text", "image"]
    spans: tuple[RawSpan, ...]  # type="image"면 빈 tuple

@dataclass(frozen=True)
class RawPage:
    page_num: int  # 1-indexed
    width: float
    height: float
    blocks: tuple[RawBlock, ...]

def open_pdf(path: Path) -> "FitzDoc": ...
def render_png(doc: FitzDoc, page_idx: int, dpi: int) -> bytes: ...
def iter_pages(doc: FitzDoc) -> Iterator[RawPage]: ...
def close(doc: FitzDoc) -> None: ...
```

`FitzDoc`은 opaque newtype (`NewType("FitzDoc", object)`). 내부에선 `cast(fitz.Document, ...)`로 좁힘.
`# type: ignore`는 이 파일에서만 허용. 다른 모듈에서 사용 시 review에서 reject.

### 2. Block grouping (`extract/blocks.py`)

PyMuPDF는 이미 block을 주지만 한 paragraph가 여러 block으로 쪼개지거나 한 block에 여러 paragraph가 섞이는 경우가 흔하다. 다음 휴리스틱:

- **Paragraph 묶기 기준** (단일 RawBlock 안에서 line-by-line):
  - y-gap ≤ `0.5 * median_line_height` → 같은 paragraph
  - y-gap > `1.2 * median_line_height` → paragraph 분리
  - font-size 차이 > 20% → 분리
- **Header 판정**:
  - font-size ≥ `1.4 * page_median_font_size` AND 라인 수 ≤ 2 → `type="header"`
  - 그 외 텍스트는 `type="text"`
- **빈 block** (`text=""` and `type="text"`) → 폐기
- **Image block**: `type="image"`, text="", bbox 유지

### 3. Reading order (`extract/reading_order.py`)

멀티컬럼 인식은 **x 좌표 1D-cluster**:

1. 페이지의 모든 text block의 x0(좌상단 x) 리스트
2. 1D agglomerative clustering (gap threshold = `0.05 * page_width`)
3. 클러스터 개수 = 추정 컬럼 수 (cap=3)
4. **단일 컬럼**: y0 오름차순
5. **N컬럼**: 컬럼 별로 분류 (block의 중심 x로 컬럼 결정) → 컬럼별로 y0 오름차순 → 컬럼 순서(좌→우)대로 이어붙임
6. Header는 컬럼 위에 걸치는 경우 많음 — bbox width > `0.7 * page_width`면 전 컬럼 가로지르는 것으로 보고 최상단으로

이 알고리즘은 80% 목표 (ROADMAP 명시). 실패 케이스는 known issue로 기록.

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
def extract_pdf(pdf_path: Path, out_dir: Path, *, dpi: int = 200, save_images: bool = False) -> ExtractResult
```

흐름:
1. `out_dir`/`pages`/`images` 디렉토리 생성 (없으면)
2. fitz 열기 → for each page (1-indexed):
   a. `render_page_png` → `pages/page_NNNN.png`
   b. `iter_pages` 결과로 grouping → reading order → block 리스트
   c. block id를 `p{N}_b{ORDER:03d}` 형식으로 부여
   d. bbox 소수점 1자리 round
   e. `pages/page_NNNN.json` 저장 (atomic write)
   f. image block의 픽셀 추출은 `save_images=True`일 때만 (기본 False — 디스크 절약, Phase 4 viewer에서 페이지 PNG로 대체 가능)
3. 문서 단위 lang 집계
4. `doc_meta.json` 저장 (sha256은 streaming hash, ISO 8601 UTC, version은 `ht_lens.__version__`)

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
| `tests/integration/test_extract_pipeline.py` | new | 3 fixture × 통합 (page count, lang, block 존재) |
| `tests/integration/test_extract_snapshot.py` | new | syrupy snapshot (정규화된 block 구조) |
| `tests/integration/__snapshots__/` | new (generated) | snapshot baseline |

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
- `test_blocks.py`: synthetic spans로 paragraph 묶기 / header 판정 검증
- `test_reading_order.py`: 1/2/3컬럼 synthetic block 리스트 → 기대 순서
- `test_language.py`: 짧은 텍스트, 한글, 영문, 혼재 케이스
- `test_normalize.py`: bbox round, 비결정 필드 redact

### Integration
- `test_extract_pipeline.py` (3 sample × 5 assertion = 15):
  - num_pages > 0
  - `doc_meta.json` 존재 + lang_guess가 기대 값
  - 모든 페이지 PNG 존재 + PIL로 열 수 있고 dpi-derived size 일치
  - 모든 페이지 JSON 존재 + 최소 1 block (단, mixed의 표지 페이지는 image-only일 수 있어 그건 별도 assertion 안 함)
  - 모든 block id가 `p{N}_b{NNN}` 패턴
- `test_extract_snapshot.py` (3 sample): 정규화된 block 구조를 syrupy로 비교

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
