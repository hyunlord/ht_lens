# Phase 1 — Challenge

## Debate responses

### 1. Over-engineering

- **`_fitz.py` wrapper가 과하다** — **reject**. 근거: phase prompt가 "PyMuPDF + mypy strict 격리 정책"을 명시적으로 요구. `# type: ignore` 산재를 막는 단일 경계는 ROADMAP 후속 phase까지 유지될 자산이라 비용 정당. 단 `open_pdf`/`close` 페어는 context manager로 단순화함(아래 §3 partial 참조).
- **`doc_meta.json`의 sha256/extracted_at/version이 과하다** — **reject**. 근거: phase prompt가 "doc_meta.json 스키마 (고정)"으로 못 박은 영역이라 plan 단계에서 축소 권한 없음. `save_images`만 **partial**로 수용하여 기본 False로 묶고 Phase 1 검증에서 제외.
- **컬럼 클러스터링이 너무 욕심이다** — **accept**. plan.md §3 갱신: PyMuPDF `get_text("dict", sort=True)` 출력을 baseline으로 신뢰하고, 멀티컬럼 신호(y가 두 번 이상 뒤로 가는 경우)가 명백할 때만 휴리스틱 fallback. ROADMAP의 "80% 목표"와 합치.
- **`models.py`의 pydantic이 시기상조다** — **partial**. 근거: pydantic은 Phase 0 dep에 이미 존재. 무거운 검증 대신 `BaseModel`의 `model_dump_json`만 사용 (직렬화 일관성 확보). 도메인 검증 로직은 Phase 2~3로 미룸. 외부 의존성 변동 없음.

### 2. Hidden assumptions

- **`RawBlock`이 line을 노출하지 않아 y-gap 계산 불가** — **accept**. plan.md §1 갱신: `RawLine`(bbox+spans+direction) 계층 추가, `RawBlock.lines: tuple[RawLine, ...]`로 변경. §2 grouping도 line-by-line으로 명시.
- **좌표 단위가 미정의** — **accept**. plan.md §6.5 신설: page JSON에 `rotation`, `render.{dpi,pixel_width,pixel_height,scale}`, `unit:"pt"` 추가. prompt-fixed 필드는 그대로 보존(추가만).
- **langdetect의 한/영 혼재 분류가 brittle** — **partial**. 페이지 < 50자는 unknown, 페이지별 majority + 페이지간 disagreement 30% 이상이면 mixed로 단순화 유지. Phase 1은 "그럴듯한 가이드" 수준이면 충분하고, 정밀화는 별도 phase에서. `tests/unit/test_language.py`에 한/영 short text edge case 추가.
- **PyMuPDF API 안정성 가정** — **partial**. `pyproject.toml`에서 `pymupdf>=1.24,<1.26`로 lower/upper bound 고정. CI에서 동일 버전 강제.
- **fixture 3종의 대표성 부족** — **accept**. `tests/fixtures/README.md`에 각 sample의 출처/페이지 수/예상 컬럼/언어 명시. 부족한 케이스(회전, 스캔본)는 합성 PDF로 별도 테스트.

### 3. Edge cases

- **회전 페이지 / 비표준 CropBox** — **accept**. `RawPage.rotation` 노출, JSON에 기록. `render_page_png`는 PyMuPDF 기본대로 rotation을 반영한 픽셀을 그대로 저장 (bbox는 PDF 원본 좌표 + rotation 메타데이터 함께 → viewer가 보정). `test_rotated_page.py`로 검증.
- **multi-column 휴리스틱이 들여쓰기/사이드바를 컬럼으로 오인** — **accept**. §3에서 baseline을 PyMuPDF로 옮긴 것이 1차 완화. 또 `test_reading_order_indented_bullets_do_not_create_columns` 추가.
- **이미지-온리 페이지가 통합 테스트에서 실패** — **accept**. assertion을 "모든 페이지 ≥1 block" → "문서 전체에 ≥1 block & 모든 페이지 JSON 존재"로 완화. 또 `test_scanned_page_writes_empty_blocks_json` 추가.
- **CJK ToUnicode / 세로쓰기 / ruby** — **partial**. Phase 1에서 적극 대응하지 않는다고 명시. `RawLine.direction`을 노출해 두어 Phase 6에서 사용 가능. plan.md "Out" 섹션에 명시.
- **부분 출력 실패 정책** — **accept**. pipeline §6 갱신: atomic temp-rename으로 페이지별 corruption 없음 보장. 실패 시 부분 출력은 그대로 두고 사용자가 `--overwrite`로 재시도. context manager로 fitz close 보장.

### 4. Alternative approaches

- **`get_text("dict", sort=True)` 직접 활용** — **accept**. plan §1/§3 갱신.
- **per-page 좌표 메타 저장** — **accept**. plan §6.5.
- **fixture-driven 검증으로 클러스터링 적용** — **accept**. plan §3.
- **pdfplumber/layoutparser는 Phase 1 dep 아님** — **accept** (추가 안 함).

### 5. Missing tests

다음 테스트는 모두 plan에 반영 (accept):

- `test_fixture_pdfs_exist_and_are_nonempty` ✅
- `test_page_json_records_coordinate_space_and_render_scale` ✅
- `test_rotated_page_bbox_matches_rendered_png_dimensions` ✅ (합성 회전 PDF 사용)
- `test_reading_order_indented_bullets_do_not_create_columns` ✅
- `test_reading_order_spanning_header_then_two_columns` ✅
- `test_scanned_page_writes_empty_blocks_json` ✅ (합성 image-only PDF)
- `test_cli_rejects_existing_non_empty_out_dir_without_overwrite` ✅
- `test_cli_overwrite_replaces_previous_output` ✅
- `test_encrypted_pdf_exit_code_2` ✅
- `test_corrupted_pdf_exit_code_3` ✅
- `test_pipeline_closes_document_on_page_failure` — **partial**: `_fitz.open_pdf`를 context manager로 만든 결과 코드 경로 자체에서 close 보장. 대신 `test_open_pdf_close_on_exception` 추가 (context block 안에서 예외를 던지고 doc.is_closed 확인).
- 사람-검토용 artifact (`docs/phases/phase-1/samples.md`) ✅ — `test_human_review.py`가 생성.

총 12개 중 11개 직접 accept + 1개 partial. Reject 0개.

## Plan revisions (after debate)

`.claude/phases/phase-1/plan.md`에 적용된 구체적 변경:

1. **§1 `_fitz.py`**: `RawLine` 추가, `RawBlock.lines`로 교체, `open_pdf`를 context manager로, `rotation` 노출, baseline source를 `get_text("dict", sort=True)`로 명시.
2. **§2 `blocks.py`**: grouping 단위를 line-by-line으로 명확화.
3. **§3 `reading_order.py`**: PyMuPDF sort=True를 baseline으로, 멀티컬럼 휴리스틱은 fallback. 클러스터링 키를 x0 → 중심 x로 변경, gap threshold를 0.05 → 0.10으로 완화.
4. **§6 `pipeline.py`**: context manager 기반, `overwrite=False` 시 비어있지 않은 dir에 `OutputDirNotEmptyError(exit 2)`, atomic write 명시.
5. **§6.5 신설**: page JSON에 `rotation`, `render.{dpi,pixel_width,pixel_height,scale}`, `unit:"pt"` 추가.
6. **Test strategy**: 위 12개 테스트 모두 반영. `tests/integration/test_cli_errors.py`, `test_rotated_page.py`, `test_human_review.py` 신규 추가.
7. **File-level changes**: 위 신규 테스트 파일 + `docs/phases/phase-1/samples.md` (generated) 항목 추가.

`save_images` 옵션은 그대로 유지하되 기본 False, 검증 범위에서 제외. `pymupdf` 버전은 `>=1.24,<1.26` 핀.

## DoD checklist

| DoD item | Status | Evidence (plan) |
| -------- | ------ | --------------- |
| 3종 sample PDF block JSON이 합리적 | planned | `tests/integration/test_extract_pipeline.py` + `test_human_review.py`가 생성하는 `docs/phases/phase-1/samples.md` |
| snapshot test 통과 | planned | `tests/integration/test_extract_snapshot.py` + `normalize.py` (bbox round 1자리, 비결정 필드 redact) |
| extract 의존성 = pymupdf / pillow / langdetect | planned | `pyproject.toml` dep 목록 + verify.md grep evidence |
| mypy strict 0, ruff clean | enforced | `make lint`가 매 커밋 후 통과, CI에서 강제 |
| CLI `python -m ht_lens.extract` 동작 | planned | `extract/__main__.py` + verify.md 5-B의 3 sample 실행 결과 |
| 한/영 폰트 인식 | mitigated | langdetect mixed 판정 + sample_ko/sample_mixed 통합 테스트 + `test_language.py` |
| 멀티컬럼 reading order | mitigated | PyMuPDF sort=True baseline + 휴리스틱 fallback + 2개 reading_order edge-case 테스트 |
| 캡션/각주 분리 | deferred | Phase 6 (현재는 paragraph로 흡수, plan "Out"에 명시) |

## Risk register

| Risk | Likelihood | Impact | Mitigation |
| ---- | ---------- | ------ | ---------- |
| PyMuPDF sort=True가 sample_mixed에서 다컬럼을 잘못 정렬 | M | M | fallback 휴리스틱 + snapshot으로 회귀 잡기 |
| 한글 ToUnicode 누락 PDF에서 텍스트가 깨짐 | L-M | M | fixture가 그런 PDF가 아니면 Phase 1 통과 가능, README에 한계 명시 |
| langdetect가 mixed sample을 잘못 분류 | M | L | 30% disagreement 임계로 비교적 robust, snapshot으로 회귀 잡기 |
| 합성 회전/encrypted/scanned PDF 생성이 PyMuPDF 버전에 종속 | L | L | 버전 핀 + 생성 실패 시 테스트 skip + 명확한 메시지 |
| `samples.md`가 매 run마다 diff (시간/sha) | M | L | normalize 적용해서 결정적으로 생성 |
| save_images=True 사용 시 디스크 폭증 | L | L | 기본 False, Phase 1 검증 범위 외 |

## Decision
- [x] **PASS → proceed to code**
- [ ] RE-PLAN
