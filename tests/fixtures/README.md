# Test fixtures

Phase 1 sample PDFs. Each is the canonical fixture for the language indicated by the suffix.

| File                | Pages | Expected `lang_guess` | Notes |
| ------------------- | ----- | --------------------- | ----- |
| `sample_en.pdf`     | 8     | `en`                  | Open-Sora 2.0 technical paper excerpt. Single column body + figures + multi-column references at the end. |
| `sample_ko.pdf`     | 52    | `ko`                  | 한국어 단행본/문서 발췌. 단일 컬럼이 다수. |
| `sample_mixed.pdf`  | 6     | `mixed`               | 영문(Open-Sora 1~3p) + 한국어 위키 발췌(4~6p). Page 4는 URL 인코딩 비중이 커서 단독으로는 미검출, page 5는 텍스트 < 50자라 `unknown`. Document-level 집계로 mixed가 잡힌다. |

PDF 자체의 reading-order/CJK ToUnicode/회전 동작은 Phase 1 알고리즘의 80% 목표 범위 안에서만 보장한다.
회전 / 암호화 / 스캔본 / 깨진 PDF 케이스는 합성 PDF를 사용해 별도 검증한다 (`tests/integration/test_cli_errors.py`, `test_rotated_page.py`).
